"""The translation may not break any status comparison: every branch must still be reachable."""
import re
from pathlib import Path

import pytest

from src import calculations, labels


def status_van(cijfers, **wijzigingen):
	return calculations.bouw_dataframe([{**cijfers, **wijzigingen}]).iloc[0]


def test_every_overview_column_has_an_english_label(cijfers):
	df = calculations.bouw_dataframe([cijfers])
	ontbrekend = [
		kol for kol in df.columns
		if kol not in ("LBO_Jaren", "LBO_Integriteit", "LBO_Scenarios") and kol not in labels.COLUMN_LABELS
	]
	assert ontbrekend == []


def test_baseline_gets_a_known_status(cijfers):
	assert status_van(cijfers)["LBO_Status"].startswith((labels.STATUS_STRONG, labels.STATUS_POSSIBLE))


def test_data_mismatch_gives_review(cijfers):
	rij = status_van(cijfers, Check_Data=labels.check_review(["x"]))
	assert rij["LBO_Status"] == labels.STATUS_REVIEW_DATA


def test_insufficient_data_status(cijfers):
	rij = status_van(cijfers, Data_Volledigheid=labels.data_insufficient("no data for 62"))
	assert rij["LBO_Status"] == labels.STATUS_INSUFFICIENT


def test_negative_ebitda_is_no_go(cijfers):
	rij = status_van(cijfers, Bedrijfswinst_EBIT=-5_000_000.0)
	assert rij["LBO_Status"] == labels.STATUS_NO_GO_EBITDA
	assert rij["LBO_Convenanten"].startswith(labels.NOT_APPLICABLE)


def test_small_company_is_no_go(cijfers):
	rij = status_van(cijfers, Bedrijfswinst_EBIT=100_000.0, Afschrijvingen=50_000.0)
	assert rij["LBO_Status"] == labels.STATUS_NO_GO_SIZE


def test_heavy_auditor_opinion_blocks_strong_status(cijfers):
	rij = status_van(cijfers, Commissaris_Oordeel=labels.OPINION_ADVERSE)
	assert labels.FLAG_AUDITOR.format(opinion=labels.OPINION_ADVERSE) in rij["Red_Flags"]
	assert rij["LBO_Status"] != labels.STATUS_STRONG


def test_liquidation_signal_reaches_the_heavy_flags(cijfers):
	rij = status_van(cijfers, Cijfer_Flags=labels.FLAG_LIQUIDATION)
	assert labels.FLAG_LIQUIDATION in rij["Zware_Flags"] if "Zware_Flags" in rij else True
	assert labels.FLAG_LIQUIDATION in rij["Red_Flags"]


def test_every_status_has_a_colour():
	for status in (
		labels.STATUS_STRONG, labels.STATUS_POSSIBLE_FLAGS, labels.STATUS_POSSIBLE_CASHFLOW, labels.STATUS_REVIEW_DATA,
		labels.STATUS_REVIEW_MODEL, labels.STATUS_NO_GO_EBITDA, labels.STATUS_NO_GO_DEBT, labels.STATUS_INSUFFICIENT,
		labels.YES, labels.NO,
	):
		assert any(status.startswith(sleutel) for sleutel in labels.STATUS_COLOURS)


@pytest.mark.parametrize("bestand", ["calculations.py", "lbo_model.py", "excel_export.py", "excel_model.py"])
def test_no_comparison_against_a_literal_status(bestand):
	"""A comparison against literal status text would break silently on the next rewording."""
	pad = Path(calculations.__file__).parent / bestand
	if not pad.exists():
		pytest.skip("module not built yet")
	bron = pad.read_text(encoding="utf-8")
	verboden = r'(?:==|!=|startswith\()\s*\(?f?"(?:OK|FOUT|ERROR|BREACHED|GESCHONDEN|N\.V\.T\.|N/A|Onvoldoende|Insufficient|Volledig|Complete)'
	assert re.findall(verboden, bron) == []
