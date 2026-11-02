"""Phase 9.2: python main.py --demo runs the fictitious company end to end, without an API key."""
import hashlib

import openpyxl
import pytest

import main as app
from src import config, demo, labels


def _hashes():
	return {pad: hashlib.sha256(pad.read_bytes()).hexdigest() for pad in demo.DEMO_MAP.rglob("*") if pad.is_file()}


@pytest.fixture
def demo_run(tmp_path, monkeypatch):
	for knop in ("INPUT_FOLDER", "CACHE_FOLDER", "SNAPSHOT_FOLDER", "RUNS_FOLDER"):
		monkeypatch.setattr(config, knop, getattr(config, knop))
	monkeypatch.setattr(config, "OUTPUT_FOLDER", tmp_path)

	def geen_ai():
		raise AssertionError("the demo must not create a Gemini client")

	monkeypatch.setattr(app, "maak_client", geen_ai)
	voor = _hashes()
	app.main(["--demo"])
	return tmp_path / "demo", voor


def test_demo_writes_both_workbooks_without_ai(demo_run):
	map_uit, _ = demo_run
	fiche = next(map_uit.glob("LBO_Model_Demo_Industries_NV_*.xlsx"))
	overzicht = next(map_uit.glob("LBO_Screening_Overview_*.xlsx"))
	wb = openpyxl.load_workbook(fiche)
	assert wb.sheetnames[0] == labels.TAB_SUMMARY and labels.TAB_SENSITIVITIES in wb.sheetnames
	samenvatting = [cel.value for regel in wb[labels.TAB_SUMMARY].iter_rows() for cel in regel if isinstance(cel.value, str)]
	assert any(waarde.startswith(labels.STATUS_POSSIBLE) for waarde in samenvatting)
	assert any("Primary" == waarde for waarde in samenvatting)
	assert any(waarde.startswith("• Revenue grew") for waarde in samenvatting)  # the illustrative thesis
	assert openpyxl.load_workbook(overzicht).worksheets[0].title == labels.TAB_RANKING
	assert len(list((map_uit / "runs").glob("run_*.json"))) == 1


def test_demo_ledger_has_one_approved_item(demo_run):
	map_uit, _ = demo_run
	wb = openpyxl.load_workbook(next(map_uit.glob("LBO_Model_*.xlsx")))
	ws = wb[labels.TAB_INPUTS]
	schakelaars = {
		str(ws.cell(row=r, column=1).value)[:2]: ws.cell(row=r, column=6).value
		for r in range(1, ws.max_row + 1) if str(ws.cell(row=r, column=1).value or "").startswith(("A1 ", "A2 "))
	}
	assert schakelaars == {"A1": 1, "A2": 0}


def test_demo_never_changes_the_example_files(demo_run):
	_, voor = demo_run
	assert _hashes() == voor


def test_demo_enterprise_number_fails_the_belgian_check_digit():
	"""0999.999.999 can never belong to a real company: 97 - (first 8 digits mod 97) must equal the last two."""
	nummer = "0999999999"
	assert 97 - int(nummer[:8]) % 97 != int(nummer[8:])
