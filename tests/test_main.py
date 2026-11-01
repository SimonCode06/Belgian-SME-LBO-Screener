"""The assumption step of main.py, with a simulated Gemini: no API call."""
import json

import pytest

import main as app
from src import config, labels
from tests.test_assumpties import nagebootste_gemini_respons


class NepClient:
	def __init__(self):
		self.aanroepen = 0
		self.models = self
		self.files = self

	def generate_content(self, model, contents, config):
		self.aanroepen += 1

		class Antwoord:
			text = json.dumps(nagebootste_gemini_respons())

		return Antwoord


@pytest.fixture
def pdf(tmp_path, monkeypatch):
	monkeypatch.setattr(config, "CACHE_FOLDER", tmp_path)
	monkeypatch.setattr(config, "SNAPSHOT_FOLDER", tmp_path / "assumpties")
	pad = tmp_path / "Testco.pdf"
	pad.write_bytes(b"%PDF-1.4 test")
	return pad


def test_too_little_history_uses_no_ai(pdf, filings, cijfers):
	client = NepClient()
	cijfers = {**cijfers, "Driver_Aantal_Jaren": config.LBO_MIN_JAREN - 1}
	pack, bron, _, _, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert pack is None
	assert bron == labels.ASSUMPTIONS_FALLBACK_HISTORY
	assert client.aanroepen == 0


def test_ai_proposal_is_cached(pdf, filings, cijfers):
	client = NepClient()
	pack, bron, _, model, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert bron == labels.ASSUMPTIONS_AI and model == config.MODELLEN[0]
	assert pack["base"]["dso"]["waarden"] == [54.0] * 5

	opnieuw, bron, _, _, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert client.aanroepen == 1
	assert opnieuw["base"]["dso"]["waarden"] == [54.0] * 5


@pytest.mark.parametrize(
	"knop, waarde",
	[("ASSUMPTIE_PROMPT", "another prompt"), ("PROMPT_VERSIE", "2099-01-z"), ("SCHEMA_VERSIE", 99)],
)
def test_prompt_and_schema_versions_are_in_the_cache_key(pdf, filings, cijfers, monkeypatch, knop, waarde):
	from src.nbb_csv import bouw_driver_pack

	driver_pack = bouw_driver_pack(filings)
	voor = app.assumptie_cache_pad_voor(pdf, driver_pack)
	monkeypatch.setattr(config, knop, waarde)
	assert app.assumptie_cache_pad_voor(pdf, driver_pack) != voor


def test_package_versions_are_not_in_the_cache_key(pdf, filings, monkeypatch):
	"""A pydantic update changes the JSON schema text; the key must not depend on it."""
	from src.assumpties import AssumptieAntwoord
	from src.nbb_csv import bouw_driver_pack

	driver_pack = bouw_driver_pack(filings)
	voor = app.assumptie_cache_pad_voor(pdf, driver_pack)
	monkeypatch.setattr(AssumptieAntwoord, "model_json_schema", classmethod(lambda cls, **_: {"changed": True}))
	assert app.assumptie_cache_pad_voor(pdf, driver_pack) == voor


@pytest.mark.parametrize("knop, waarde", [("PROMPT_VERSIE", "2099-01-z"), ("SCHEMA_VERSIE", 99)])
def test_versions_are_in_the_text_and_commentary_keys(pdf, cijfers, monkeypatch, knop, waarde):
	voor = app.cache_pad_voor(pdf, cijfers)
	monkeypatch.setattr(config, knop, waarde)
	assert app.cache_pad_voor(pdf, cijfers) != voor


def test_gemini_failure_is_reported_and_labelled(pdf, filings, cijfers, monkeypatch):
	def faalt(*_):
		raise RuntimeError("no model available")

	monkeypatch.setattr(app, "genereer_assumpties", faalt)
	mislukt = []
	pack, bron, _, _, _ = app.haal_assumpties(NepClient(), pdf, filings, cijfers, mislukt)
	assert pack is None and bron == labels.ASSUMPTIONS_FALLBACK_NO_AI
	assert mislukt


# --- Snapshots ----------------------------------------------------------------------------


def snapshot_van(cijfers):
	from src import assumpties

	return assumpties.snapshot_pad(cijfers["Ondernemingsnummer"], cijfers["Boekjaar"])


def test_ai_run_writes_a_snapshot_with_metadata(pdf, filings, cijfers):
	_, _, _, _, info = app.haal_assumpties(NepClient(), pdf, filings, cijfers, [])
	pad = snapshot_van(cijfers)
	assert pad.name == "0123456789_FY2024.json" and info["naam"] == pad.name
	metadata = json.loads(pad.read_text(encoding="utf-8"))["metadata"]
	assert metadata["status"] == "voorstel" and info["status"] == "voorstel"
	assert metadata["gemini_model"] == config.MODELLEN[0]
	assert metadata["prompt_versie"] == config.PROMPT_VERSIE
	assert metadata["pdf_bestand"] == "Testco.pdf" and len(metadata["pdf_sha256"]) == 64
	assert metadata["datum"] == info["datum"]


def test_snapshot_wins_even_when_the_cache_key_changes(pdf, filings, cijfers, monkeypatch):
	client = NepClient()
	eerste, *_ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	monkeypatch.setattr(config, "PROMPT_VERSIE", "2099-01-z")
	tweede, bron, _, model, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert client.aanroepen == 1
	assert tweede == eerste and bron == labels.ASSUMPTIONS_AI and model == config.MODELLEN[0]


def test_snapshot_without_api_key_gives_the_same_ai_case(pdf, filings, cijfers):
	met_sleutel, *_ = app.haal_assumpties(NepClient(), pdf, filings, cijfers, [])
	zonder_sleutel, bron, *_ = app.haal_assumpties(None, pdf, filings, cijfers, [])
	assert zonder_sleutel == met_sleutel and bron == labels.ASSUMPTIONS_AI


def test_snapshot_is_used_without_pdf(pdf, filings, cijfers):
	met_pdf, *_ = app.haal_assumpties(NepClient(), pdf, filings, cijfers, [])
	zonder_pdf, bron, *_ = app.haal_assumpties(None, None, filings, cijfers, [])
	assert zonder_pdf == met_pdf and bron == labels.ASSUMPTIONS_AI


def test_two_runs_give_identical_figures(pdf, filings, cijfers):
	from src.calculations import bouw_dataframe
	from tests.test_regressie import kerncijfers

	uitkomsten = []
	for client in (NepClient(), None):
		pack, bron, driver_pack, _, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
		rij = {**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": bron, "LBO_Driver_Pack": driver_pack}
		uitkomsten.append(json.dumps(kerncijfers(bouw_dataframe([rij]).iloc[0]), sort_keys=True))
	assert uitkomsten[0] == uitkomsten[1]


def test_renew_archives_the_old_snapshot_and_calls_gemini(pdf, filings, cijfers):
	client = NepClient()
	app.haal_assumpties(client, pdf, filings, cijfers, [])
	pad = snapshot_van(cijfers)
	oud = json.loads(pad.read_text(encoding="utf-8"))
	oud["metadata"]["status"] = "goedgekeurd"
	pad.write_text(json.dumps(oud), encoding="utf-8")

	_, _, _, _, info = app.haal_assumpties(client, pdf, filings, cijfers, [], vernieuw=True)
	assert client.aanroepen == 2  # the cache is bypassed too
	archief = [p for p in pad.parent.glob("0123456789_FY2024_*.json")]
	assert len(archief) == 1
	assert json.loads(archief[0].read_text(encoding="utf-8"))["metadata"]["status"] == "goedgekeurd"
	assert info["status"] == "voorstel"


def test_renew_without_gemini_keeps_the_snapshot(pdf, filings, cijfers):
	eerste, *_ = app.haal_assumpties(NepClient(), pdf, filings, cijfers, [])
	tweede, bron, *_ = app.haal_assumpties(None, pdf, filings, cijfers, [], vernieuw=True)
	assert tweede == eerste and bron == labels.ASSUMPTIONS_AI
	assert len(list(snapshot_van(cijfers).parent.glob("*.json"))) == 1


def test_broken_snapshot_is_reported_not_overwritten(pdf, filings, cijfers):
	pad = snapshot_van(cijfers)
	pad.parent.mkdir(parents=True)
	pad.write_text("{broken", encoding="utf-8")
	client = NepClient()
	mislukt = []
	pack, bron, *_ = app.haal_assumpties(client, pdf, filings, cijfers, mislukt)
	assert pack is None and bron == labels.ASSUMPTIONS_FALLBACK_NO_AI
	assert mislukt and client.aanroepen == 0
	assert pad.read_text(encoding="utf-8") == "{broken"


def test_command_line_flag():
	assert app.lees_argumenten([]).vernieuw_assumpties is False
	assert app.lees_argumenten(["--vernieuw-assumpties"]).vernieuw_assumpties is True
	assert app.lees_argumenten(["--ijking"]).ijking is True


# --- End to end: CSV in, Excel and run manifest out ----------------------------------------


def schrijf_neerlegging_csv(pad, neerlegging):
	velden = {
		"Entity number": neerlegging.ondernemingsnummer,
		"Entity name": neerlegging.naam,
		"Accounting period start date": neerlegging.begin.isoformat(),
		"Accounting period end date": neerlegging.einde.isoformat(),
		"Reference number": neerlegging.referentie,
		"Currency": neerlegging.valuta,
		"Model code": neerlegging.model,
		**{code: repr(bedrag) for code, bedrag in neerlegging.codes.items()},
	}
	pad.write_text("\n".join(f'"{k}","{v}"' for k, v in velden.items()), encoding="utf-8-sig")


@pytest.fixture
def mappen(tmp_path, monkeypatch, filings):
	for knop, naam in (
		("INPUT_FOLDER", "input"), ("CACHE_FOLDER", "cache"), ("OUTPUT_FOLDER", "output"), ("SNAPSHOT_FOLDER", "assumpties"),
	):
		monkeypatch.setattr(config, knop, tmp_path / naam)
	monkeypatch.setattr(config, "RUNS_FOLDER", tmp_path / "output" / "runs")
	config.INPUT_FOLDER.mkdir()
	for jaar in filings:
		schrijf_neerlegging_csv(config.INPUT_FOLDER / jaar.bestand, jaar)
	return tmp_path


def test_a_run_writes_the_workbooks_and_a_manifest(mappen):
	import openpyxl

	app.main([])
	manifesten = list(config.RUNS_FOLDER.glob("run_*.json"))
	assert len(manifesten) == 1
	manifest = json.loads(manifesten[0].read_text(encoding="utf-8"))

	for veld in ("manifest", "tijdstip", "git", "versies", "config_sha256", "prompt_versie", "bedrijven", "uitvoer"):
		assert veld in manifest, veld
	assert {"commit", "niet_gecommitte_wijzigingen"} <= set(manifest["git"])
	assert manifest["versies"]["pandas"] and manifest["versies"]["python"]
	assert len(manifest["config_sha256"]) == 64

	bedrijf = manifest["bedrijven"][0]
	assert bedrijf["ondernemingsnummer"] == "0123.456.789" and bedrijf["boekjaar"] == "2024"
	assert sorted(bedrijf["csv"]) == ["Test_JR2022.csv", "Test_JR2023.csv", "Test_JR2024.csv"]
	assert all(len(waarde) == 64 for waarde in bedrijf["csv"].values())
	assert bedrijf["pdf"] is None and bedrijf["snapshot"] == "-"
	for veld in (
		"status", "ai_irr_pct", "screening_irr_pct", "stress_irr_pct", "stress_convenanten", "gemini_model",
		"debt_capacity_x", "max_entry_multiple", "headroom_pct",
	):
		assert veld in bedrijf, veld
	assert bedrijf["screening_irr_pct"] == bedrijf["ai_irr_pct"]  # without AI both are rule-based

	assert len(manifest["uitvoer"]) == 2
	for naam in manifest["uitvoer"]:
		wb = openpyxl.load_workbook(config.OUTPUT_FOLDER / naam)
		teksten = {cel.value for ws in wb.worksheets for rij in ws.iter_rows() for cel in rij if isinstance(cel.value, str)}
		assert manifest["manifest"] in teksten, naam


def test_company_workbook_shows_the_screening_scenarios_and_snapshot(mappen, filings):
	import openpyxl

	from src import assumpties

	app.main([])
	pad = next(p for p in config.OUTPUT_FOLDER.glob("LBO_Model_*.xlsx"))
	wb = openpyxl.load_workbook(pad)
	model = wb[labels.TAB_MODEL]
	keuzelijst = model.data_validations.dataValidation[0].formula1
	for scenario in assumpties.MODEL_SCENARIOS:
		assert assumpties.scenario_label(scenario) in keuzelijst
	samenvatting = {cel.value for rij in wb[labels.TAB_SUMMARY].iter_rows() for cel in rij}
	assert labels.SNAPSHOT_LABEL in samenvatting and labels.SNAPSHOT_STATUS in samenvatting


def test_calibration_file_ranks_by_score(mappen):
	import pandas as pd

	app.main(["--ijking"])
	pad = next(config.OUTPUT_FOLDER.glob("ijking_*.csv"))
	tabel = pd.read_csv(pad, sep=";", decimal=",")
	assert list(tabel["Score"]) == sorted(tabel["Score"], reverse=True)
	for kolom in ("Status", "Debt capacity x", "Max entry x", "Debt Capacity", "Debt Capacity: reason", "Data Quality"):
		assert kolom in tabel.columns, kolom


# --- Linking the PDF ----------------------------------------------------------------------


def test_pdf_per_fiscal_year_picks_the_latest(tmp_path, filings):
	paden = [tmp_path / naam for naam in ("Test_JR2023.pdf", "Test_JR2024.pdf", "Andere.pdf")]
	index = app.pdf_index(paden)
	assert app.zoek_pdf(filings, index).name == "Test_JR2024.pdf"


def test_pdf_name_with_spaces_and_one_pdf_without_year(tmp_path, filings):
	from dataclasses import replace

	bedrijf = [replace(jaar, naam="Aikido Security", bestand=f"AikidoSecurity_JR{jaar.boekjaar}.csv") for jaar in filings]
	index = app.pdf_index([tmp_path / "Aikido Security _ JR2023.pdf", tmp_path / "Aikido Security _ JR2022.pdf"])
	assert app.zoek_pdf(bedrijf, index).name == "Aikido Security _ JR2023.pdf"  # no 2024 PDF: the most recent one
	assert app.zoek_pdf(filings, app.pdf_index([tmp_path / "Testco.pdf"])).name == "Testco.pdf"
	assert app.splits_bestandsnaam("Flanders Food Productions_ JR2025") == ("Flanders Food Productions", "2025")


def test_pdf_year_can_follow_the_csv_file_name(tmp_path, filings):
	"""Broken fiscal year: 'JR2023' in the file names is the filing that ends in 2024."""
	from dataclasses import replace

	bedrijf = filings[:-1] + [replace(filings[-1], bestand="Test_JR2023.csv")]
	index = app.pdf_index([tmp_path / "Test_JR2023.pdf", tmp_path / "Test_JR2022.pdf"])
	assert app.zoek_pdf(bedrijf, index).name == "Test_JR2023.pdf"
