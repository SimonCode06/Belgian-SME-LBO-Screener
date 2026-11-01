"""Recalculates the company workbook in LibreOffice (headless) and compares it with the Python engine.

The same reconciliation as test_excel_recalc.py, but it runs on Linux, so GitHub Actions checks every
push: per scenario the statements, debt, covenants, IRR and MoIC, the EV-to-equity bridge, the value
creation bridge and the model checks; no cell may show #REF!, #DIV/0!, #VALUE!, #NAME? or #N/A.
Also: the ledger switch flows through and the live covenant cell agrees with the debt capacity.
Skipped when LibreOffice (soffice) is not installed.
"""
import shutil
import subprocess

import openpyxl
import pytest

from src import assumpties, calculations, excel_model, labels
from src.assumpties import AssumptieAntwoord, pack_uit_antwoord
from src.nbb_csv import bouw_meerjaren
from tests.test_assumpties import nagebootste_gemini_respons

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
pytestmark = pytest.mark.skipif(SOFFICE is None, reason="LibreOffice is not installed")
TOLERANTIE_EUR = 1.0
FOUTEN = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "Err:")


def herbereken(paden, map_uit):
	"""One LibreOffice call for all files (start-up is the slow part). Returns the recalculated workbooks."""
	map_uit.mkdir(exist_ok=True)
	subprocess.run(
		[SOFFICE, "--headless", "--norestore", "--calc", "--convert-to", "xlsx", "--outdir", str(map_uit), *map(str, paden)],
		check=True, capture_output=True, timeout=600,
	)
	return [openpyxl.load_workbook(map_uit / pad.name, data_only=True) for pad in paden]


@pytest.fixture(scope="module")
def rij(request):
	from tests.conftest import TEKSTVELDEN, neerlegging
	from src.nbb_csv import bouw_cijfers

	filings = [
		neerlegging(2022, 9_000_000.0, 5_400_000.0, 2_000_000.0),
		neerlegging(2023, 9_500_000.0, 5_700_000.0, 2_100_000.0),
		neerlegging(2024, 10_000_000.0, 6_000_000.0, 2_200_000.0),
	]
	pack = pack_uit_antwoord(AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))
	pack["base"]["prijsgroei"]["waarden"] = [2.5, 2.0, 1.5, 2.0, 2.2]
	pack["downside"]["dso"]["waarden"] = [56.0, 60.0, 62.0, 62.0, 61.0]
	item = {
		"id": "A1", "categorie": "eenmalig", "omschrijving": "One-off cost.", "richting": "+", "bedrag": 100_000.0,
		"bron": "CSV", "bedrag_geverifieerd": True, "pagina": 1, "citaat_status": "verified", "market_level": None,
		"goedgekeurd": True,
	}
	invoer = {
		**bouw_cijfers(filings), **TEKSTVELDEN, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI,
		"LBO_Adjustments": [item],
	}
	return calculations.bouw_dataframe([invoer]).iloc[0], [jaar["Model"] for jaar in bouw_meerjaren(filings)]


@pytest.fixture(scope="module")
def herberekend(rij, tmp_path_factory):
	"""Every scenario, plus the ledger switched off and the live cell at and above the capacity."""
	df_rij, historiek = rij
	map_in = tmp_path_factory.mktemp("lo_in")
	paden, kaarten, gevallen = [], [], []

	def bewaar(naam, wijzig):
		wb, kaart = excel_model.bouw_werkboek(df_rij, historiek)
		wijzig(wb, kaart)
		pad = map_in / f"{naam}.xlsx"
		wb.save(pad)
		paden.append(pad)
		kaarten.append(kaart)
		gevallen.append(naam)

	def kies(scenario):
		return lambda wb, kaart: setattr(wb[labels.TAB_INPUTS][kaart["scenario_cel"]], "value", assumpties.scenario_label(scenario))

	for scenario in assumpties.MODEL_SCENARIOS:
		bewaar(scenario, kies(scenario))

	def ledger_uit(wb, kaart):
		ws = wb[labels.TAB_INPUTS]
		nr = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(row=r, column=1).value or "").startswith("A1 "))
		ws.cell(row=nr, column=6).value = 0

	bewaar("ledger_off", ledger_uit)
	for naam, extra in (("live_at", 0.0), ("live_above", 0.1)):
		def live(wb, kaart, extra=extra):
			kies("screening_stress")(wb, kaart)
			blad, adres = wb.defined_names["Senior_Multiple"].attr_text.split("!")
			wb[blad.strip("'")][adres.replace("$", "")].value = float(df_rij["Debt_Capacity_Multiple"]) + extra
		bewaar(naam, live)

	boeken = herbereken(paden, tmp_path_factory.mktemp("lo_uit"))
	return {naam: (boek, kaart) for naam, boek, kaart in zip(gevallen, boeken, kaarten)}


def _rij(boek, kaart, blad, sleutel):
	ws = boek[kaart["bladen"][blad]]
	return [ws[f"{kolom}{kaart['rijen'][blad][sleutel]}"].value for kolom in kaart["kolommen"]["jaren"]]


def _cel(boek, kaart, blad, sleutel, kolom="C"):
	return boek[kaart["bladen"][blad]][f"{kolom}{kaart['rijen'][blad][sleutel]}"].value


@pytest.mark.parametrize("scenario", assumpties.MODEL_SCENARIOS)
def test_libreoffice_matches_python(herberekend, rij, scenario):
	df_rij, _ = rij
	boek, kaart = herberekend[scenario]
	model = df_rij["LBO_Scenarios"][scenario]
	jaren = model["Jaren"][1:]
	vergelijk = {
		("model", "ebitda"): "EBITDA", ("model", "ni"): "Nettowinst", ("lbo", "w_fcf"): "FCF", ("model", "cash"): "Cash",
		("lbo", "d_senior"): "Senior_Lening", ("lbo", "d_rcf"): "RCF", ("lbo", "d_vendor"): "Vendor_Loan",
		("model", "ta"): "Totaal_Activa", ("model", "tax_calc"): "Belasting", ("lbo", "c_cfads"): "CFADS",
	}
	for (blad, sleutel), veld in vergelijk.items():
		for jaar, (excel, python) in enumerate(zip(_rij(boek, kaart, blad, sleutel), (j[veld] for j in jaren)), start=1):
			assert excel is not None and abs(excel - python) <= TOLERANTIE_EUR, f"{scenario} {sleutel} Y{jaar}"
	for sleutel, veld in (("c_dscr", "DSCR"), ("c_icr", "Rentedekking"), ("c_lev", "Leverage")):
		for jaar, (excel, python) in enumerate(zip(_rij(boek, kaart, "lbo", sleutel), (j[veld] for j in jaren)), start=1):
			assert excel == pytest.approx(python, abs=1e-6), f"{scenario} {sleutel} Y{jaar}"

	assert _cel(boek, kaart, "lbo", "x_irr") * 100 == pytest.approx(model["LBO_IRR_Exact_Pct"], abs=0.01)
	assert _cel(boek, kaart, "lbo", "x_moic") == pytest.approx(model["LBO_MoIC_Exact"], abs=1e-6)
	assert _cel(boek, kaart, "lbo", "x_covenants") == model["LBO_Convenanten"].split(":")[0]
	for sleutel, verwacht in (
		("eq_price_rij", df_rij["Indicatieve_Equity_Value"]),
		("entry_ebitda_rij", df_rij["Genormaliseerde_EBITDA"]),
		("s_equity_rij", model["LBO_Sponsor_Equity_Instap"]),
	):
		assert _cel(boek, kaart, "lbo", sleutel) == pytest.approx(verwacht, abs=TOLERANTIE_EUR), sleutel
	assert abs(_cel(boek, kaart, "lbo", "vc_check")) <= TOLERANTIE_EUR
	doel = model["LBO_Exit_Equity_Jaar5"] + model["LBO_Dividend_Cumulatief"]
	assert _cel(boek, kaart, "lbo", "vc_end") == pytest.approx(doel, abs=TOLERANTIE_EUR)
	assert boek[labels.TAB_SUMMARY][kaart["checks_cel"]].value == labels.CHECK_OK

	fouten = [
		f"{ws.title}!{cel.coordinate}" for ws in boek.worksheets for regel in ws.iter_rows() for cel in regel
		if isinstance(cel.value, str) and cel.value.startswith(FOUTEN)
	]
	assert not fouten, fouten[:5]


def test_ledger_switch_off_lowers_entry_ebitda(herberekend, rij):
	df_rij, _ = rij
	boek, kaart = herberekend["ledger_off"]
	assert _cel(boek, kaart, "lbo", "entry_ebitda_rij") == pytest.approx(df_rij["Genormaliseerde_EBITDA"] - 100_000.0, abs=1)
	assert boek[labels.TAB_SUMMARY][kaart["checks_cel"]].value == labels.CHECK_OK


def test_live_covenant_cell_agrees_with_the_debt_capacity(herberekend):
	for naam, verwacht in (("live_at", labels.YES), ("live_above", labels.NO)):
		boek, kaart = herberekend[naam]
		assert _cel(boek, kaart, "lbo", "dc_live") == verwacht, naam
