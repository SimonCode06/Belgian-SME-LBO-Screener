"""De AI-laag: laat Gemini de tekst van een jaarrekening analyseren en de resultaten toelichten.

Er zijn twee passes. De eerste loopt vóór de berekening: de cijfers uit de NBB-CSV
(zie nbb_csv.py) gaan als gegeven mee en Gemini levert uit de PDF alleen tekst, zoals
normalisatievoorstellen en red flags. Die voorstellen worden niet in de EBITDA verwerkt.
De tweede loopt na de berekening: Gemini licht de uitkomst van het LBO-model toe, zodat
het kwalitatieve oordeel de cijfers kent. De status komt altijd uit het model.

Regelt zelf retries met exponentiële backoff en schakelt over naar het
volgende model in config.MODELLEN bij aanhoudende overbelasting (503/504).
"""
import json
import math
import random
import re
import time

from google.genai import errors, types

from . import config, labels
from .assumpties import AssumptieAntwoord, driver_uitleg
from .tekst_schema import OordeelAntwoord, TekstAntwoord


def parse_json_antwoord(tekst, sleutels):
	"""Haalt een JSON-object met de gevraagde sleutels uit het antwoord, ook met ```json-fences eromheen."""
	if not tekst:
		raise ValueError("Leeg antwoord van het model.")
	schoon = re.sub(r"^```(?:json)?\s*|\s*```$", "", tekst.strip(), flags=re.S)
	data = json.loads(schoon)
	if isinstance(data, list):
		if not data:
			raise ValueError("Lege JSON-lijst teruggekregen.")
		data = data[0]
	if not isinstance(data, dict):
		raise ValueError("Antwoord is geen JSON-object.")
	ontbrekend = [sleutel for sleutel in sleutels if sleutel not in data]
	if ontbrekend:
		raise ValueError(f"Sleutels ontbreken: {', '.join(ontbrekend)}")
	return data


def bouw_pdf_part(client, pdf_pad):
	"""Kleine PDF's inline meesturen, grote via de Files API."""
	pdf_bytes = pdf_pad.read_bytes()
	if len(pdf_bytes) <= config.INLINE_LIMIET_BYTES:
		return types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), None
	geupload = client.files.upload(
		file=str(pdf_pad), config=types.UploadFileConfig(mime_type="application/pdf")
	)
	return geupload, geupload.name


def bouw_prompt(cijfers):
	"""De vaste instructies plus de cijfers uit de CSV als gegeven."""
	# Alleen een vaste lijst: een nieuw berekend veld in de cijfers mag geen nieuwe (betaalde) analyse uitlokken
	gegevens = {
		sleutel: None if isinstance(cijfers.get(sleutel), float) and math.isnan(cijfers[sleutel]) else cijfers.get(sleutel)
		for sleutel in config.TEKST_PROMPT_VELDEN
	}
	return (
		f"{config.SYSTEEM_PROMPT}\n"
		"Figures from the NBB filing (in euro, final):\n"
		f"{json.dumps(gegevens, ensure_ascii=False, indent=2)}\n"
	)


def bouw_oordeel_prompt(rij):
	"""De instructies van de tweede pass plus de resultaten van het model als gegeven."""
	gegevens = {
		veld: None if isinstance(rij[veld], float) and math.isnan(rij[veld]) else rij[veld]
		for veld in config.OORDEEL_VELDEN
	}
	return (
		f"{config.OORDEEL_PROMPT}\n"
		"Results of the LBO model (amounts in euro):\n"
		f"{json.dumps(gegevens, ensure_ascii=False, indent=2, default=str)}\n"
	)


def bouw_assumptie_prompt(driver_pack):
	"""The instructions for the forecast assumptions plus the driver pack as fixed facts."""
	return (
		f"{config.ASSUMPTIE_PROMPT}\n"
		f"Drivers:\n{driver_uitleg()}\n\n"
		"Driver pack (historical ratios per fiscal year, final):\n"
		f"{json.dumps(driver_pack, ensure_ascii=False, indent=2, default=str)}\n"
	)


def _vraag_gemini(client, contents, sleutels, schema=None, temperatuur=0.1):
	"""Probeert elk model in config.MODELLEN af met backoff.

	Met een schema dwingt Gemini de structuur af en wordt het antwoord met Pydantic gevalideerd.
	"""
	generatie_config = types.GenerateContentConfig(
		response_mime_type="application/json", temperature=temperatuur, response_schema=schema
	)
	laatste_fout = None
	for model in config.MODELLEN:
		for poging in range(1, config.MAX_POGINGEN_PER_MODEL + 1):
			try:
				response = client.models.generate_content(
					model=model,
					contents=contents,
					config=generatie_config,
				)
				if schema is not None:
					data = schema.model_validate_json(response.text).model_dump()
				else:
					data = parse_json_antwoord(response.text, sleutels)
				data["Gebruikt_Model"] = model
				return data

			except errors.APIError as fout:
				laatste_fout = fout
				code = getattr(fout, "code", None)

				if code == 404:
					print(f"   ... {model} niet beschikbaar (404), volgend model")
					break
				if code in (401, 403):
					raise RuntimeError(
						f"{labels.API_KEY_REFUSED} ({code}). Check your key/project."
					) from fout
				if code not in config.RETRYABLE_CODES:
					raise

				wacht = min(2**poging, config.MAX_WACHTTIJD_SEC) + random.uniform(0, 2)
				print(
					f"   ... {model} poging {poging}/{config.MAX_POGINGEN_PER_MODEL} "
					f"mislukt ({code}), wacht {wacht:.0f}s"
				)
				time.sleep(wacht)

			except (ValueError, json.JSONDecodeError) as fout:
				laatste_fout = fout
				print(f"   ... {model} gaf ongeldige JSON ({fout}), opnieuw")
				time.sleep(2)

			except Exception as fout:
				laatste_fout = fout
				wacht = min(2**poging, config.MAX_WACHTTIJD_SEC)
				print(f"   ... {model} netwerkfout ({type(fout).__name__}), wacht {wacht}s")
				time.sleep(wacht)

		print(f"   ... overschakelen van {model} naar volgend model")

	raise RuntimeError(f"Alle modellen/pogingen mislukt. Laatste fout: {laatste_fout}")


def analyseer_tekst(client, pdf_pad, cijfers):
	"""Eerste pass: de tekst uit de PDF, vóór de berekening."""
	pdf_deel, upload_naam = bouw_pdf_part(client, pdf_pad)
	try:
		return _vraag_gemini(client, [pdf_deel, bouw_prompt(cijfers)], (), schema=TekstAntwoord)
	finally:
		if upload_naam:
			try:
				client.files.delete(name=upload_naam)
			except Exception:
				pass


def genereer_assumpties(client, pdf_pad, driver_pack):
	"""Forecast assumptions per driver, scenario and year, from the PDF and the driver pack."""
	pdf_deel, upload_naam = bouw_pdf_part(client, pdf_pad)
	try:
		return _vraag_gemini(
			client,
			[pdf_deel, bouw_assumptie_prompt(driver_pack)],
			(),
			schema=AssumptieAntwoord,
			temperatuur=0,
		)
	finally:
		if upload_naam:
			try:
				client.files.delete(name=upload_naam)
			except Exception:
				pass


def schrijf_oordeel(client, rij):
	"""Tweede pass: de toelichting op de resultaten, na de berekening. De PDF is niet meer nodig."""
	return _vraag_gemini(client, [bouw_oordeel_prompt(rij)], (), schema=OordeelAntwoord)
