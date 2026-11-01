"""Quote check: does the quote Gemini gives as evidence actually appear in the PDF?

Gemini names a page and a short quote for every finding and every assumption. That looks
like evidence, but it is not checked by the model itself. Here Python reads the text of
each PDF page and searches the quote with fuzzy matching (rapidfuzz), on the page named
and the pages next to it. A quote that cannot be found lowers the confidence to 'low' and
adds a soft flag. Nothing else changes: the check never edits a value.
"""
import logging
import re
import unicodedata

from rapidfuzz import fuzz

from . import config, labels

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings on NBB PDFs are noise for a text search

GEVERIFIEERD = "verified"
ANDERE_PAGINA = "verified (other page)"
NIET_GEVONDEN = "not found"
GEEN_CITAAT = "no quote"
NIET_CONTROLEERBAAR = "not checkable"


def normaliseer(tekst):
	"""Lower case, accents and quotes made uniform, all white space reduced to one space."""
	tekst = unicodedata.normalize("NFKD", str(tekst or ""))
	tekst = "".join(teken for teken in tekst if not unicodedata.combining(teken))
	tekst = re.sub(r"[‘’‚‛′`´]", "'", tekst)
	tekst = re.sub(r"[“”„‟″«»]", '"', tekst)
	tekst = re.sub(r"[‐-―]", "-", tekst)
	return re.sub(r"\s+", " ", tekst).strip().casefold()


def pdf_paginas(pad):
	"""The normalised text per page (index 0 = page 1), or None if the PDF has no readable text.

	A scanned PDF has no text layer: then the quotes are 'not checkable', which is no error.
	"""
	if pad is None:
		return None
	try:
		from pypdf import PdfReader

		paginas = [normaliseer(pagina.extract_text() or "") for pagina in PdfReader(str(pad)).pages]
	except Exception:
		return None
	if sum(len(pagina) for pagina in paginas) < config.CITAAT_MIN_TEKST_TEKENS:
		return None
	return paginas


def _score_deel(deel, tekst):
	if len(deel) > len(tekst):
		return fuzz.ratio(deel, tekst)
	return fuzz.partial_ratio(deel, tekst)


def _score(citaat, tekst):
	"""A quote shortened with '...' counts when every part of it is found on the page."""
	delen = [deel.strip(" .,;:\"'") for deel in re.split(r"\.{3}|\u2026", citaat)]
	delen = [deel for deel in delen if len(deel) >= config.CITAAT_MIN_LENGTE] or [citaat]
	return min(_score_deel(deel, tekst) for deel in delen)


def controleer_citaat(citaat, pagina, paginas):
	"""Returns (status, score). pagina is 1-based or None."""
	citaat = normaliseer(citaat).strip("\"' .")
	if not citaat or citaat == normaliseer(config.ASSUMPTIE_BRON_HISTORIEK):
		return GEEN_CITAAT, None
	if paginas is None:
		return NIET_CONTROLEERBAAR, None
	if len(citaat) < config.CITAAT_MIN_LENGTE:
		return GEEN_CITAAT, None

	kandidaten = range(len(paginas))
	if isinstance(pagina, int) and 1 <= pagina <= len(paginas):
		buren = [index for index in (pagina - 2, pagina - 1, pagina) if 0 <= index < len(paginas)]
		beste = max(_score(citaat, paginas[index]) for index in buren)
		if beste >= config.CITAAT_MIN_SCORE:
			return GEVERIFIEERD, beste
		kandidaten = [index for index in kandidaten if index not in buren]
	elders = max((_score(citaat, paginas[index]) for index in kandidaten), default=0)
	if elders >= config.CITAAT_MIN_SCORE:
		return (ANDERE_PAGINA if isinstance(pagina, int) else GEVERIFIEERD), elders
	return NIET_GEVONDEN, elders


BRON_PATROON = re.compile(r"p(?:age|\.)?\s*(\d+)\s*[:,-]?\s*(.*)", re.IGNORECASE | re.S)


def splits_bron(bron):
	"""'p. 12: "new contract signed"' -> (12, 'new contract signed'). Without a page: (None, text)."""
	bron = str(bron or "").strip()
	treffer = BRON_PATROON.match(bron)
	if not treffer:
		return None, bron
	return int(treffer.group(1)), treffer.group(2).strip().strip("\"'“”")


def is_geverifieerd(status):
	return status in (GEVERIFIEERD, ANDERE_PAGINA)


def controleer_assumpties(pack, paginas, scenarios):
	"""Checks the source quote of every AI assumption. Not found: confidence 'low' and a soft flag."""
	regels = []
	for scenario in scenarios:
		for sleutel, voorstel in pack[scenario].items():
			pagina, citaat = splits_bron(voorstel["source"])
			status, _ = controleer_citaat(citaat, pagina, paginas)
			voorstel["citaat_status"] = status
			if status == NIET_GEVONDEN:
				voorstel["confidence"] = "low"
				voorstel["vlaggen"].append(labels.QUOTE_NOT_FOUND)
				regels.append((scenario, sleutel))
	return regels
