"""Sensitivity tables for the workbook: the sponsor IRR on a grid of two inputs, in the Screening Base case.

Two grids, both computed with the Python model (a data table in Excel would need a macro or
iterative recalculation, and LibreOffice does not support it):
- entry multiple (rows) x exit multiple (columns), at the standard senior debt;
- forecast EBITDA versus the screening case, -20% to +20% in every year (rows) x senior debt
  (columns), with price and debt sized on the reported EBITDA (as in the robustness grid).

Each cell holds the IRR and whether the covenants hold, so the workbook can mark breaches. The
tables are static: they do not follow overrides in the workbook.
"""
from dataclasses import dataclass, field

from . import assumpties, config
from .lbo_model import Structuur, bereken_lbo
from .structurering import haalt_covenants

SCENARIO = "screening_base"
MULTIPLE_STAPPEN = (-1.0, -0.5, 0.0, 0.5, 1.0)
EBITDA_STAPPEN = (-0.20, -0.10, 0.0, 0.10, 0.20)
SENIOR_STAPPEN = (-1.0, -0.5, 0.0, 0.5, 1.0)


@dataclass
class Tabel:
	rijen: list  # row values (multiples or EBITDA shifts)
	kolommen: list  # column values (multiples)
	irr: list = field(default_factory=list)  # [row][column] as a fraction; -1 when the sponsor loses everything
	breuk: list = field(default_factory=list)  # [row][column] True when a covenant or the cash test fails


def _irr(model):
	waarde = model.get("LBO_IRR_Exact_Pct")
	try:
		waarde = float(waarde)
	except (TypeError, ValueError):
		return None
	return None if waarde != waarde else waarde / 100


def _breuk(model):
	return not haalt_covenants(model)


def _met_ebitda(rij, deel):
	"""The screening case with the forecast EBITDA (1 + deel) x as high (price and debt unchanged)."""
	if not deel:
		return rij
	nieuw = dict(rij)
	omzet, personeel = float(rij["Omzet_of_Brutomarge"]), float(rij["Personeelskosten"])
	nieuw["LBO_Assumpties"] = {
		**rij["LBO_Assumpties"],
		SCENARIO: assumpties.verschuif_ebitda(rij["LBO_Assumpties"][SCENARIO], omzet, personeel, deel),
	}
	return nieuw


def _vul(tabel, reken):
	for rij_waarde in tabel.rijen:
		irr, breuk = [], []
		for kolom_waarde in tabel.kolommen:
			model = reken(rij_waarde, kolom_waarde)
			irr.append(_irr(model))
			breuk.append(_breuk(model))
		tabel.irr.append(irr)
		tabel.breuk.append(breuk)
	return tabel


def instap_exit(rij):
	"""IRR by entry multiple (rows) and exit multiple (columns)."""
	instap, senior = float(rij["Instap_Multiple"]), float(rij["Senior_Multiple"])
	multiples = [max(instap + stap, 1.0) for stap in MULTIPLE_STAPPEN]
	tabel = Tabel(rijen=multiples, kolommen=list(multiples))
	return _vul(
		tabel,
		lambda entry, exit_: bereken_lbo(rij, SCENARIO, Structuur(entry, exit_, senior, config.LBO_VENDOR_LOAN_PCT_EV)),
	)


def ebitda_senior(rij):
	"""IRR by forecast EBITDA shift (rows) and senior multiple (columns)."""
	instap, senior = float(rij["Instap_Multiple"]), float(rij["Senior_Multiple"])
	tabel = Tabel(rijen=list(EBITDA_STAPPEN), kolommen=[max(senior + stap, 0.0) for stap in SENIOR_STAPPEN])
	varianten = {deel: _met_ebitda(rij, deel) for deel in EBITDA_STAPPEN}
	return _vul(
		tabel,
		lambda deel, multiple: bereken_lbo(
			varianten[deel], SCENARIO, Structuur(instap, instap, multiple, config.LBO_VENDOR_LOAN_PCT_EV)
		),
	)


def analyseer(rij):
	"""Both grids, or None when the screening case has no LBO."""
	model = (rij.get("LBO_Scenarios") or {}).get(SCENARIO) or {}
	if _irr(model) is None:
		return None
	return {"instap_exit": instap_exit(rij), "ebitda_senior": ebitda_senior(rij)}
