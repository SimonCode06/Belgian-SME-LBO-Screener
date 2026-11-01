"""The structured text pass: what Gemini returns from the PDF, and how Python processes it.

Gemini returns building blocks instead of long text: EBITDA adjustment proposals, red flags,
the ownership structure and off-balance-sheet items, each with a page and a quote. Python then
1. takes the amount from the NBB-CSV whenever Gemini names an NBB code that is in the filing
   (design rule 1: an AI amount is a proposal, never a figure), and
2. checks every quote against the PDF (citaten.py).
"""
from typing import Literal

from pydantic import BaseModel, Field

from . import citaten, labels

Confidence = Literal["low", "medium", "high"]
CommissarisOordeel = Literal[
	labels.OPINION_UNQUALIFIED,
	labels.OPINION_QUALIFIED,
	labels.OPINION_DISCLAIMER,
	labels.OPINION_ADVERSE,
	labels.OPINION_NO_AUDITOR,
	labels.OPINION_UNKNOWN,
]


class Normalisatie(BaseModel):
	"""One EBITDA adjustment proposal. richting '+' adds back to EBITDA, '-' deducts."""

	categorie: Literal["bestuurdersvergoeding", "huur_verbonden_partij", "privekosten", "eenmalig", "subsidie", "overig"]
	omschrijving: str = Field(description="One sentence, in English.")
	bedrag_eur: float | None = Field(description="Amount in euro as stated in the PDF, or null.")
	nbb_code: str | None = Field(description="NBB code of the amount, for example 9503, or null.")
	richting: Literal["+", "-"]
	pagina: int | None = Field(description="PDF page number, or null.")
	citaat: str = Field(description="A short literal quote from that page, in the language of the PDF.")
	confidence: Confidence


class RedFlag(BaseModel):
	categorie: Literal[
		"governance", "verbonden_partijen", "going_concern", "juridisch", "klantconcentratie", "personeel", "overig"
	]
	ernst: Literal["hoog", "middel", "laag"]
	omschrijving: str = Field(description="One sentence, in English.")
	pagina: int | None
	citaat: str = Field(description="A short literal quote from that page, in the language of the PDF.")


class Eigendom(BaseModel):
	type: Literal["zelfstandig", "groepsdochter", "pe_backed", "onbekend"]
	moederonderneming: str | None
	ondernemingsnummer_moeder: str | None
	consoliderend: Literal["ja", "nee", "onbekend"] = Field(description="Is the company included in group consolidated accounts?")
	pagina: int | None
	citaat: str


class Buitenbalans(BaseModel):
	omschrijving: str
	bedrag_eur: float | None
	pagina: int | None


class TekstAntwoord(BaseModel):
	ondernemingsnummer: str = Field(description="Enterprise number on the PDF, as 0xxx.xxx.xxx")
	boekjaar: str = Field(description="Year of the end date of the fiscal year on the PDF")
	commissaris_oordeel: CommissarisOordeel
	normalisaties: list[Normalisatie]
	red_flags: list[RedFlag]
	eigendom: Eigendom
	buitenbalans: list[Buitenbalans]


SLEUTELS = tuple(TekstAntwoord.model_fields)


class DDVraag(BaseModel):
	vraag: str = Field(description="One due diligence question, in English.")
	gekoppeld_aan: str = Field(description="The red flag or assumption this question tests, as named in the input.")


class OordeelAntwoord(BaseModel):
	"""The second pass: commentary on the model result, an investment thesis and DD questions."""

	kwalitatief_lbo_oordeel: str = Field(description="Concise commentary on the LBO result, in English.")
	investment_thesis: list[str] = Field(min_length=3, max_length=3, description="Exactly three bullets.")
	dd_vragen: list[DDVraag] = Field(min_length=5, max_length=5, description="Exactly five questions.")


OORDEEL_SLEUTELS = tuple(OordeelAntwoord.model_fields)


def _bedrag_tekst(bedrag):
	return f"EUR {bedrag:,.0f}" if bedrag is not None else ""


def _pagina_tekst(pagina, status):
	stukken = [f"p. {pagina}" if pagina else "", f"quote {status}"]
	return "[" + ", ".join(stuk for stuk in stukken if stuk) + "]"


def verwerk_normalisatie(normalisatie, codes, paginas):
	"""Amount from the CSV if the code is there; otherwise the AI amount, labelled as unverified."""
	regel = dict(normalisatie)
	code = str(regel.get("nbb_code") or "").strip()
	if code and code in codes:
		regel["bedrag_gebruikt"] = float(codes[code])
		regel["bedrag_bron"] = labels.AMOUNT_FROM_CSV.format(code=code)
		regel["bedrag_geverifieerd"] = True
	else:
		regel["bedrag_gebruikt"] = regel.get("bedrag_eur")
		regel["bedrag_bron"] = labels.AMOUNT_AI_UNVERIFIED
		regel["bedrag_geverifieerd"] = False
	regel["citaat_status"], _ = citaten.controleer_citaat(regel["citaat"], regel["pagina"], paginas)
	if regel["citaat_status"] == citaten.NIET_GEVONDEN:
		regel["confidence"] = "low"
	return regel


def _met_citaat(item, paginas):
	regel = dict(item)
	regel["citaat_status"], _ = citaten.controleer_citaat(regel.get("citaat", ""), regel.get("pagina"), paginas)
	return regel


def eigendom_tekst(eigendom):
	"""'Group subsidiary of De Cronos Groep NV (0xxx.xxx.xxx), consolidated: yes [p. 36, quote verified]'."""
	soort = labels.OWNERSHIP_TYPES.get(eigendom["type"], eigendom["type"])
	moeder = eigendom.get("moederonderneming")
	if moeder:
		nummer = eigendom.get("ondernemingsnummer_moeder")
		soort = f"{soort} of {moeder}" + (f" ({nummer})" if nummer else "")
	consolidatie = labels.YES_NO_UNKNOWN.get(eigendom["consoliderend"], eigendom["consoliderend"])
	return f"{soort}, {labels.OWNERSHIP_CONSOLIDATED}: {consolidatie} {_pagina_tekst(eigendom.get('pagina'), eigendom['citaat_status'])}"


def verwerk_tekst(data, codes, paginas):
	"""From a validated Gemini response to the fields of the result row.

	codes: the NBB codes of the most recent filing. paginas: the PDF text per page (citaten.pdf_paginas).
	The readable text columns stay for the overview; the structured lists are kept next to them.
	"""
	antwoord = TekstAntwoord.model_validate({sleutel: data[sleutel] for sleutel in SLEUTELS}).model_dump()
	normalisaties = [verwerk_normalisatie(item, codes, paginas) for item in antwoord["normalisaties"]]
	red_flags = [_met_citaat(item, paginas) for item in antwoord["red_flags"]]
	eigendom = _met_citaat(antwoord["eigendom"], paginas)
	buitenbalans = [dict(item) for item in antwoord["buitenbalans"]]

	def norm_regel(item):
		bedrag = _bedrag_tekst(item["bedrag_gebruikt"])
		bron = f" ({item['bedrag_bron']})" if bedrag else ""
		soort = labels.ADJUSTMENT_TYPES.get(item["categorie"], item["categorie"])
		return f"{soort} ({item['richting']}): {item['omschrijving']} {bedrag}{bron} {_pagina_tekst(item['pagina'], item['citaat_status'])}"

	def flag_regel(item):
		soort = labels.FLAG_CATEGORIES.get(item["categorie"], item["categorie"])
		ernst = labels.SEVERITIES.get(item["ernst"], item["ernst"])
		return f"[{ernst}] {soort}: {item['omschrijving']} {_pagina_tekst(item['pagina'], item['citaat_status'])}"

	def balans_regel(item):
		bedrag = _bedrag_tekst(item["bedrag_eur"])
		pagina = f" (p. {item['pagina']})" if item["pagina"] else ""
		return f"{item['omschrijving']}{': ' + bedrag if bedrag else ''}{pagina}"

	return {
		"Ondernemingsnummer": antwoord["ondernemingsnummer"],
		"Boekjaar": antwoord["boekjaar"],
		"Commissaris_Oordeel": antwoord["commissaris_oordeel"],
		"Normalisatie_Voorstellen": "\n".join(map(norm_regel, normalisaties)) or labels.NONE,
		"Red_Flags": "; ".join(map(flag_regel, red_flags)),
		"Buitenbalans_Verplichtingen": "; ".join(map(balans_regel, buitenbalans)) or labels.NONE,
		"Eigendom": eigendom_tekst(eigendom),
		"AI_Normalisaties": normalisaties,
		"AI_Red_Flags": red_flags,
		"AI_Eigendom": eigendom,
		"AI_Buitenbalans": buitenbalans,
		"Gebruikt_Model": data.get("Gebruikt_Model", "-"),
	}
