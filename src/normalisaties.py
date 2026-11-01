"""The adjustment ledger: EBITDA normalisations that an analyst approves one by one.

Gemini proposes normalisations from the PDF (phase 2). They are written once to
assumpties/<enterprise number>_FY<year>_adjustments.json, every item with goedgekeurd: false.
The analyst reviews that file and sets goedgekeurd to true for the items to keep; the file is
never overwritten afterwards, so the assessment stays deterministic.

Adjusted EBITDA = Reported EBITDA + 66A - 76A + the effect of every approved item with a
verified amount (an amount from the CSV, or one the analyst sets as verified). Director
remuneration only counts against a market level the analyst fills in: the effect is the
remuneration minus that market level. Amounts are annualised like the other results.
"""
import json
import re

from . import config

CATEGORIE_MARKTNIVEAU = "bestuurdersvergoeding"


def ledger_pad(ondernemingsnummer, boekjaar):
	nummer = re.sub(r"\D", "", str(ondernemingsnummer))
	return config.SNAPSHOT_FOLDER / f"{nummer}_FY{boekjaar}_adjustments.json"


def items_uit_ai(normalisaties):
	"""The ledger items from the processed AI proposals (tekst_schema.verwerk_normalisatie)."""
	return [
		{
			"id": f"A{index}",
			"categorie": item["categorie"],
			"omschrijving": item["omschrijving"],
			"richting": item["richting"],
			"bedrag": item.get("bedrag_gebruikt"),
			"bron": item.get("bedrag_bron", ""),
			"bedrag_geverifieerd": bool(item.get("bedrag_geverifieerd")),
			"pagina": item.get("pagina"),
			"citaat_status": item.get("citaat_status", ""),
			"market_level": None,
			"goedgekeurd": False,
		}
		for index, item in enumerate(normalisaties, start=1)
	]


def laad_of_maak(pad, normalisaties, bedrijf):
	"""An existing ledger always wins (it holds the analyst's decisions). Otherwise one is written from the AI items."""
	if pad.exists():
		try:
			return list(json.loads(pad.read_text(encoding="utf-8"))["items"])
		except (OSError, ValueError, KeyError, TypeError) as fout:
			raise ValueError(f"{pad.name}: {fout}") from None
	items = items_uit_ai(normalisaties or [])
	if items:
		pad.parent.mkdir(parents=True, exist_ok=True)
		pad.write_text(
			json.dumps({"bedrijf": bedrijf, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
		)
	return items


def basisbedrag(item):
	"""The amount before sign and annualisation. Director pay: remuneration minus the market level."""
	bedrag = item.get("bedrag")
	if bedrag is None:
		return 0.0
	if item.get("categorie") == CATEGORIE_MARKTNIVEAU:
		markt = item.get("market_level")
		return 0.0 if markt is None else float(bedrag) - float(markt)
	return float(bedrag)


def effect(item, maanden=12):
	"""The EBITDA effect of one item, whether or not it is approved (for display)."""
	if not item.get("bedrag_geverifieerd"):
		return 0.0
	teken = 1.0 if item.get("richting", "+") == "+" else -1.0
	return teken * basisbedrag(item) * 12 / maanden


def totaal(items, maanden=12):
	"""Only approved items with a verified amount count."""
	return sum(effect(item, maanden) for item in items or [] if item.get("goedgekeurd"))
