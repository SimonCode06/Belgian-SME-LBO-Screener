"""LBO Feasibility Analyser — startpunt.

Draai dit bestand (niet de bestanden in src/ rechtstreeks). Het leest elke NBB-CSV
in input_pdfs/ voor de cijfers en laat Gemini de bijhorende PDF analyseren voor de
tekst. Daarna berekent het de LBO-kengetallen met Pandas, laat het Gemini de resultaten
toelichten en schrijft het twee soorten Excel-output naar output/: één overzichtstabel
met alle bedrijven, en één apart bestand per bedrijf.

Zet per bedrijf de CSV's van meerdere boekjaren in input_pdfs/. De PDF wordt aan het
bedrijf gekoppeld via de naam: 'Cloudar.pdf' hoort bij 'Cloudar_JR2025.csv' of bij
de bedrijfsnaam 'Cloudar' in de CSV.
"""
import argparse
import hashlib
import json
import re
import sys
import time

import pandas as pd
from google import genai
from google.genai import types

from src import assumpties, citaten, config, labels, normalisaties
from src.ai_extraction import (
	analyseer_tekst,
	bouw_assumptie_prompt,
	bouw_oordeel_prompt,
	bouw_prompt,
	genereer_assumpties,
	schrijf_oordeel,
)
from src.assumpties import AssumptieAntwoord, pack_uit_antwoord
from src.calculations import bouw_dataframe
from src.excel_export import schrijf_overzicht, schrijf_per_bedrijf
from src.manifest import bouw_manifest, manifest_naam, schrijf_manifest
from src.tekst_schema import OordeelAntwoord, TekstAntwoord, verwerk_tekst
from src.nbb_csv import bouw_cijfers, bouw_driver_pack, bouw_meerjaren, groepeer_per_bedrijf, lees_neerlegging


def naam_sleutel(naam):
	"""Maakt namen vergelijkbaar: 'KDC Projects' en 'kdc_projects' worden hetzelfde."""
	return re.sub(r"[\W_]", "", naam).casefold()


def zoek_pdf(neerleggingen, pdf_per_naam):
	"""Zoekt de PDF van een bedrijf op bedrijfsnaam of op het begin van de CSV-bestandsnaam."""
	namen = {neerlegging.naam for neerlegging in neerleggingen}
	namen |= {re.split(r"_JR\d{4}", neerlegging.bestand)[0] for neerlegging in neerleggingen}
	for naam in namen:
		pdf = pdf_per_naam.get(naam_sleutel(naam))
		if pdf is not None:
			return pdf
	return None


def maak_client():
	"""Zonder sleutel gaat de analyse door: de cijfers hebben Gemini niet nodig."""
	try:
		api_key = config.laad_api_key()
	except RuntimeError as fout:
		print(f"Tekstanalyse overgeslagen: {fout}")
		return None
	return genai.Client(
		api_key=api_key,
		http_options=types.HttpOptions(timeout=config.REQUEST_TIMEOUT_MS),
	)


def geen_tekst(reden):
	return {
		"Normalisatie_Voorstellen": reden,
		"Commissaris_Oordeel": labels.OPINION_UNKNOWN,
		"Buitenbalans_Verplichtingen": reden,
		"Red_Flags": "",
		"Eigendom": labels.OWNERSHIP_TYPES["onbekend"],
		"AI_Normalisaties": [],
		"AI_Red_Flags": [],
		"AI_Eigendom": None,
		"AI_Buitenbalans": [],
		"Kwalitatief_LBO_Oordeel": reden,
		"Gebruikt_Model": "-",
	}


def _versies():
	"""Modellijst, promptversie en schemaversie: bewuste knoppen in config, geen pakketversies."""
	return f"{','.join(config.MODELLEN)}|prompt={config.PROMPT_VERSIE}|schema={config.SCHEMA_VERSIE}".encode("utf-8")


def cache_pad_voor(pdf, cijfers):
	"""De sleutel volgt de inhoud: een andere PDF, prompt, modellijst of andere cijfers geven een nieuwe analyse."""
	inhoud = pdf.read_bytes() + _versies() + bouw_prompt(cijfers).encode("utf-8")
	return config.CACHE_FOLDER / f"tekst_{pdf.stem}_{hashlib.sha256(inhoud).hexdigest()[:16]}.json"


def oordeel_cache_pad_voor(rij):
	"""Andere resultaten, een andere prompt of modellijst geven een nieuwe toelichting."""
	inhoud = _versies() + bouw_oordeel_prompt(rij).encode("utf-8")
	return config.CACHE_FOLDER / f"oordeel_{naam_sleutel(rij['Bedrijfsnaam'])}_{hashlib.sha256(inhoud).hexdigest()[:16]}.json"


def assumptie_cache_pad_voor(pdf, driver_pack):
	"""A different PDF, prompt (version), schema version, model list or driver pack gives new assumptions."""
	inhoud = pdf.read_bytes() + _versies() + bouw_assumptie_prompt(driver_pack).encode("utf-8")
	return config.CACHE_FOLDER / f"assumpties_{pdf.stem}_{hashlib.sha256(inhoud).hexdigest()[:16]}.json"


def lees_assumptie_cache(pad):
	"""A missing, broken or invalid cache file counts as no cache."""
	try:
		data = json.loads(pad.read_text(encoding="utf-8"))
		return AssumptieAntwoord.model_validate(
			{sleutel: waarde for sleutel, waarde in data.items() if sleutel != "Gebruikt_Model"}
		)
	except (OSError, ValueError):
		return None


def _uit_snapshot(pad, driver_pack, mislukt):
	"""The fixed assumption set. A broken snapshot is an error to fix, not a reason to call Gemini."""
	try:
		antwoord, metadata = assumpties.lees_snapshot(pad)
	except ValueError as fout:
		print(f"   -> FOUT in snapshot {pad.name}: {fout}")
		mislukt.append(f"snapshot {pad.name}")
		return None, labels.ASSUMPTIONS_FALLBACK_NO_AI, driver_pack, None, None
	info = assumpties.snapshot_info(pad, metadata)
	info["business_model"] = antwoord.business_model
	print(f"   -> Assumpties uit snapshot: {pad.name} (status: {info['status']})")
	return pack_uit_antwoord(antwoord), labels.ASSUMPTIONS_AI, driver_pack, metadata.get("gemini_model"), info


def haal_assumpties(client, pdf, bedrijf, cijfers, mislukt, vernieuw=False):
	"""AI assumptions if the history allows it. Returns (pack, source label, driver pack, model, snapshot info).

	A snapshot in assumpties/ always wins: the same company and year then always get the same
	assumptions, also without an API key and also after a prompt change. Only with
	vernieuw=True (python main.py --vernieuw-assumpties) does Gemini make a new set; the old
	snapshot is then archived, never deleted.
	"""
	if cijfers["Driver_Aantal_Jaren"] < config.LBO_MIN_JAREN:
		print("   -> Assumpties: te weinig historiek, mechanische drivers")
		return None, labels.ASSUMPTIONS_FALLBACK_HISTORY, None, None, None
	driver_pack = bouw_driver_pack(bedrijf)
	snapshot = assumpties.snapshot_pad(cijfers["Ondernemingsnummer"], cijfers["Boekjaar"])

	if snapshot.exists() and not vernieuw:
		return _uit_snapshot(snapshot, driver_pack, mislukt)
	if pdf is None:
		if snapshot.exists():
			print("   -> Geen PDF om te vernieuwen: bestaande snapshot blijft")
			return _uit_snapshot(snapshot, driver_pack, mislukt)
		return None, labels.ASSUMPTIONS_FALLBACK_NO_AI, driver_pack, None, None

	cache_pad = assumptie_cache_pad_voor(pdf, driver_pack)
	data = None
	if not vernieuw and lees_assumptie_cache(cache_pad) is not None:
		data = json.loads(cache_pad.read_text(encoding="utf-8"))
		print(f"   -> Assumpties uit cache: {pdf.name}")
	if data is None:
		if client is None:
			if snapshot.exists():
				print("   -> Vernieuwen kan niet zonder Gemini: bestaande snapshot blijft")
				return _uit_snapshot(snapshot, driver_pack, mislukt)
			return None, labels.ASSUMPTIONS_FALLBACK_NO_AI, driver_pack, None, None
		try:
			data = genereer_assumpties(client, pdf, driver_pack)
			AssumptieAntwoord.model_validate({k: v for k, v in data.items() if k != "Gebruikt_Model"})
			cache_pad.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
			print(f"   -> Assumpties gegenereerd ({data['Gebruikt_Model']}): {pdf.name}")
		except Exception as fout:
			print(f"   -> FOUT bij de assumpties van {pdf.name}: {fout}")
			mislukt.append(f"assumpties {pdf.name}")
			if snapshot.exists():
				return _uit_snapshot(snapshot, driver_pack, mislukt)
			return None, labels.ASSUMPTIONS_FALLBACK_NO_AI, driver_pack, None, None

	if snapshot.exists():
		archief = assumpties.archiveer_snapshot(snapshot)
		print(f"   -> Oude snapshot gearchiveerd: {archief.name}")
	assumpties.schrijf_snapshot(snapshot, data, pdf, cijfers["Bedrijfsnaam"])
	print(f"   -> Nieuwe snapshot: {snapshot.name}")
	return _uit_snapshot(snapshot, driver_pack, mislukt)


def lees_cache(pad, schema=TekstAntwoord):
	"""Een ontbrekend, kapot of ongeldig cachebestand (ook een oud formaat) telt als geen cache."""
	try:
		data = json.loads(pad.read_text(encoding="utf-8"))
		schema.model_validate({k: v for k, v in data.items() if k != "Gebruikt_Model"})
	except (OSError, ValueError, AttributeError):
		return None
	return data


def koppel_tekst(cijfers, tekst, codes=None, paginas=None):
	"""Controleert of de PDF bij dezelfde neerlegging hoort als de cijfers en verwerkt het antwoord.

	codes: de NBB-codes van de recentste neerlegging, zodat een bedrag met een NBB-code uit de CSV komt.
	paginas: de PDF-tekst per pagina voor de citaatcontrole (None: niet controleerbaar).
	"""
	if "ondernemingsnummer" not in tekst:  # geen Gemini-antwoord, dus niets te controleren
		return tekst

	cijfer_nummer = re.sub(r"\D", "", cijfers["Ondernemingsnummer"])
	pdf_nummer = re.sub(r"\D", "", str(tekst.get("ondernemingsnummer", "")))
	if pdf_nummer != cijfer_nummer:
		return geen_tekst(
			labels.TEXT_WRONG_COMPANY.format(pdf=pdf_nummer or labels.TEXT_UNKNOWN, figures=cijfer_nummer)
		)

	velden = verwerk_tekst(tekst, codes or {}, paginas)
	velden.pop("Ondernemingsnummer")
	pdf_jaar = str(velden.pop("Boekjaar", ""))
	if pdf_jaar != cijfers["Boekjaar"]:
		signaal = labels.TEXT_WRONG_YEAR.format(pdf=pdf_jaar or labels.TEXT_UNKNOWN, figures=cijfers["Boekjaar"])
		velden["Tekst_Signaal"] = signaal  # a data flag in vlaggen.py
	return velden


def voeg_oordelen_toe(df, client, mislukt):
	"""Tweede pass: Gemini licht per bedrijf de uitkomst van het model toe, met these en DD-vragen."""
	toelichtingen, theses, vragen = [], [], []
	for index, rij in df.iterrows():
		toelichtingen.append(rij["Kwalitatief_LBO_Oordeel"])
		theses.append([])
		vragen.append([])
		print(f"[{index + 1}/{len(df)}] Toelichting op de resultaten: {rij['Bedrijfsnaam']}")
		# Wie al een reden heeft (geen PDF, verkeerde PDF, mislukte eerste pass), heeft geen tekst om toe te lichten
		if isinstance(rij["Kwalitatief_LBO_Oordeel"], str) and rij["Kwalitatief_LBO_Oordeel"]:
			print("   -> Overgeslagen: geen tekstanalyse")
			continue

		cache_pad = oordeel_cache_pad_voor(rij)
		oordeel = lees_cache(cache_pad, OordeelAntwoord)
		if oordeel is not None:
			print("   -> Toelichting uit cache")
		elif client is None:
			oordeel = {"kwalitatief_lbo_oordeel": labels.COMMENTARY_NO_GEMINI}
		else:
			try:
				oordeel = schrijf_oordeel(client, rij)
				cache_pad.write_text(json.dumps(oordeel, ensure_ascii=False, indent=2), encoding="utf-8")
				print(f"   -> Toelichting geschreven ({oordeel['Gebruikt_Model']})")
			except Exception as fout:
				print(f"   -> FOUT bij de toelichting van {rij['Bedrijfsnaam']}: {fout}")
				oordeel = {"kwalitatief_lbo_oordeel": labels.COMMENTARY_FAILED}
				mislukt.append(f"toelichting {rij['Bedrijfsnaam']}")
				if labels.API_KEY_REFUSED in str(fout):
					client = None

			if client is not None and index + 1 < len(df):
				time.sleep(config.PAUZE_TUSSEN_PDFS_SEC)

		toelichtingen[-1] = oordeel["kwalitatief_lbo_oordeel"]
		theses[-1] = list(oordeel.get("investment_thesis", []))
		vragen[-1] = list(oordeel.get("dd_vragen", []))

	df["Kwalitatief_LBO_Oordeel"] = toelichtingen
	df["AI_Investment_Thesis"] = pd.Series(theses, index=df.index, dtype=object)
	df["AI_DD_Vragen"] = pd.Series(vragen, index=df.index, dtype=object)


def lees_argumenten(argv=None):
	parser = argparse.ArgumentParser(description="LBO Feasibility Analyser")
	parser.add_argument(
		"--vernieuw-assumpties",
		action="store_true",
		help="Laat Gemini nieuwe assumpties maken; de bestaande snapshots in assumpties/ worden gearchiveerd.",
	)
	return parser.parse_args(argv)


def main(argv=None):
	argumenten = lees_argumenten(argv)
	run_naam = manifest_naam()
	config.INPUT_FOLDER.mkdir(exist_ok=True)
	config.CACHE_FOLDER.mkdir(exist_ok=True)
	config.OUTPUT_FOLDER.mkdir(exist_ok=True)

	bestanden = sorted(config.INPUT_FOLDER.iterdir())
	csv_bestanden = [p for p in bestanden if p.suffix.lower() == ".csv"]
	pdf_per_naam = {naam_sleutel(p.stem): p for p in bestanden if p.suffix.lower() == ".pdf"}
	if not csv_bestanden:
		print(f"Geen CSV-bestanden gevonden in '{config.INPUT_FOLDER}'. Plaats hier NBB-CSV's.")
		return

	neerleggingen, mislukt = [], []
	for pad in csv_bestanden:
		try:
			neerleggingen.append(lees_neerlegging(pad))
		except ValueError as fout:
			print(f"FOUT bij {pad.name}: {fout}")
			mislukt.append(pad.name)

	bedrijven = groepeer_per_bedrijf(neerleggingen)
	gebruikte_pdfs = set()
	client = maak_client() if pdf_per_naam else None

	print(f"Start LBO-analyse voor {len(bedrijven)} bedrijf/bedrijven...")
	resultaten, meerjaren, invoer_per_bedrijf = [], {}, {}

	for i, bedrijf in enumerate(bedrijven, start=1):
		jaren = ", ".join(neerlegging.boekjaar for neerlegging in bedrijf)
		print(f"[{i}/{len(bedrijven)}] {bedrijf[-1].naam}: boekjaren {jaren}")

		cijfers = bouw_cijfers(bedrijf)
		meerjaren[cijfers["Ondernemingsnummer"]] = bouw_meerjaren(bedrijf)
		pdf = zoek_pdf(bedrijf, pdf_per_naam)
		paginas = citaten.pdf_paginas(pdf)  # PDF-tekst per pagina, voor de citaatcontrole

		if pdf is None:
			tekst = geen_tekst(labels.TEXT_NO_PDF)
			print("   -> Geen PDF gevonden, alleen cijfers")
		else:
			gebruikte_pdfs.add(pdf)
			cache_pad = cache_pad_voor(pdf, cijfers)
			tekst = lees_cache(cache_pad)
			if tekst is not None:
				print(f"   -> Tekst uit cache: {pdf.name}")
			elif client is None:
				tekst = geen_tekst(labels.TEXT_NO_GEMINI)
			else:
				try:
					tekst = analyseer_tekst(client, pdf, cijfers)
					cache_pad.write_text(json.dumps(tekst, ensure_ascii=False, indent=2), encoding="utf-8")
					print(f"   -> Tekst geanalyseerd ({tekst['Gebruikt_Model']}): {pdf.name}")
				except Exception as fout:
					print(f"   -> FOUT bij tekstanalyse van {pdf.name}: {fout}")
					tekst = geen_tekst(labels.TEXT_FAILED)
					mislukt.append(pdf.name)
					if labels.API_KEY_REFUSED in str(fout):
						client = None

				if client is not None and i < len(bedrijven):
					time.sleep(config.PAUZE_TUSSEN_PDFS_SEC)

		pack, bron, driver_pack, assumptie_model, snapshot = haal_assumpties(
			client, pdf, bedrijf, cijfers, mislukt, vernieuw=argumenten.vernieuw_assumpties
		)
		invoer_per_bedrijf[cijfers["Ondernemingsnummer"]] = {
			"csv": [config.INPUT_FOLDER / neerlegging.bestand for neerlegging in bedrijf],
			"pdf": pdf,
			"gemini_model": assumptie_model,
		}
		velden = koppel_tekst(cijfers, tekst, bedrijf[-1].codes, paginas)
		try:
			ledger = normalisaties.laad_of_maak(
				normalisaties.ledger_pad(cijfers["Ondernemingsnummer"], cijfers["Boekjaar"]),
				velden.get("AI_Normalisaties"),
				cijfers["Bedrijfsnaam"],
			)
		except ValueError as fout:
			print(f"   -> FOUT in de adjustment ledger: {fout}")
			mislukt.append(f"ledger {cijfers['Bedrijfsnaam']}")
			ledger = []
		if pack is not None:
			citaten.controleer_assumpties(pack, paginas, assumpties.SCENARIOS)
		if assumptie_model:
			velden["Gebruikt_Model"] = assumptie_model
		resultaten.append(
			{
				**cijfers,
				**velden,
				"LBO_Assumpties": pack,
				"LBO_Assumptie_Bron": bron,
				"LBO_Driver_Pack": driver_pack,
				"LBO_Snapshot_Naam": snapshot["naam"] if snapshot else "-",
				"LBO_Snapshot_Datum": snapshot["datum"] if snapshot else "-",
				"LBO_Snapshot_Status": snapshot["status"] if snapshot else "-",
				"AI_Business_Model": snapshot["business_model"] if snapshot else "",
				"LBO_Adjustments": ledger,
			}
		)

	zonder_csv = [p.name for p in pdf_per_naam.values() if p not in gebruikte_pdfs]
	if zonder_csv:
		print(f"\nOvergeslagen, geen CSV gevonden: {', '.join(zonder_csv)}")

	if resultaten:
		df = bouw_dataframe(resultaten)
		voeg_oordelen_toe(df, client, mislukt)
		df["Run_Manifest"] = run_naam  # in the footer of every workbook

		overzicht_pad = schrijf_overzicht(df)
		print(f"\nOverzicht opgeslagen als: {overzicht_pad}")

		per_bedrijf_paden = schrijf_per_bedrijf(df, meerjaren)
		print(f"Aparte bedrijfsfiches opgeslagen ({len(per_bedrijf_paden)}):")
		for pad in per_bedrijf_paden:
			print(f"   - {pad.name}")

		manifest = bouw_manifest(
			run_naam, df, invoer_per_bedrijf, vars(argumenten), [overzicht_pad, *per_bedrijf_paden], mislukt
		)
		print(f"Run-manifest: {schrijf_manifest(manifest)}")
	else:
		print("\nEr konden geen resultaten worden verwerkt.")

	if mislukt:
		print(f"\nMislukt ({len(mislukt)}): {', '.join(mislukt)}  -> los dit op en run het script opnieuw; "
			  "geslaagde tekstanalyses komen uit de cache.")
		sys.exit(1)


if __name__ == "__main__":
	main()
