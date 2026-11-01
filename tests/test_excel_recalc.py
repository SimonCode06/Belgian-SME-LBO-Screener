"""Recalculates the workbook in real Excel and compares it with the Python engine, per scenario.

Excel is driven through COM, so this test needs Excel on the machine: without it, it is skipped.
"""
import pytest

import dataclasses
import gc

import openpyxl

from src import assumpties, calculations, config, excel_export, excel_model, labels
from src.assumpties import AssumptieAntwoord, pack_uit_antwoord
from src.nbb_csv import bouw_cijfers, bouw_meerjaren
from tests.conftest import TEKSTVELDEN
from tests.test_assumpties import nagebootste_gemini_respons

win32 = pytest.importorskip("win32com.client")
TOLERANTIE_EUR = 1.0
TOLERANTIE_IRR_PP = 0.01


@pytest.fixture(scope="module")
def excel():
	try:
		toepassing = win32.DispatchEx("Excel.Application")
	except Exception:
		pytest.skip("Excel is not available")
	toepassing.Visible = False
	toepassing.DisplayAlerts = False
	yield toepassing
	gc.collect()  # release every sheet reference before Excel closes
	toepassing.Quit()


class Open:
	"""A saved workbook opened in Excel, with reading by row key."""

	def __init__(self, excel, pad, kaart):
		self.excel = excel
		self.kaart = kaart
		self.wb = excel.Workbooks.Open(str(pad))
		self.model = self.wb.Worksheets(labels.TAB_MODEL)
		self.lbo = self.wb.Worksheets(labels.TAB_LBO)
		self.samenvatting = self.wb.Worksheets(labels.TAB_SUMMARY)

	def reken(self):
		self.excel.CalculateFull()

	def scenario(self, naam):
		self.model.Range(self.kaart["scenario_cel"]).Value = naam
		self.reken()

	def rij(self, blad, sleutel):
		ws = self.model if blad == "model" else self.lbo
		nr = self.kaart["rijen"][blad][sleutel]
		return [ws.Range(f"{kolom}{nr}").Value for kolom in self.kaart["kolommen"]["jaren"]]

	def cel(self, blad, sleutel, kolom="C"):
		ws = self.model if blad == "model" else self.lbo
		return ws.Range(f"{kolom}{self.kaart['rijen'][blad][sleutel]}").Value

	def checks(self):
		return self.samenvatting.Range(self.kaart["checks_cel"]).Value

	def override(self, scenario, driver, jaar, waarde):
		nr = self.kaart["rijen"]["model"][f"ov_{scenario}_{driver}"]
		self.model.Range(f"{self.kaart['kolommen']['jaren'][jaar - 1]}{nr}").Value = waarde

	def sluit(self):
		self.wb.Close(SaveChanges=False)
		self.wb = self.model = self.lbo = self.samenvatting = None


@pytest.fixture
def rij(cijfers):
	pack = pack_uit_antwoord(AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))
	# Year-specific values, so every column has to pick up its own assumption
	pack["base"]["prijsgroei"]["waarden"] = [2.5, 2.0, 1.5, 2.0, 2.2]
	pack["base"]["inkoop_pct"]["waarden"] = [60.5, 60.2, 60.0, 59.8, 59.6]
	pack["downside"]["dso"]["waarden"] = [56.0, 60.0, 62.0, 62.0, 61.0]
	pack["upside"]["capex_pct"]["waarden"] = [0.5, 0.7, 0.9, 0.8, 0.6]
	return pack, cijfers


def bouw(tmp_path, cijfers, pack, filings, naam="model.xlsx"):
	df = calculations.bouw_dataframe(
		[{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI}]
	)
	rij = df.iloc[0]
	historiek = [jaar["Model"] for jaar in bouw_meerjaren(filings)]
	wb, kaart = excel_model.bouw_werkboek(rij, historiek)
	pad = tmp_path / naam
	wb.save(pad)
	return rij, pad, kaart


def vergelijk_scenario(open_wb, rij, scenario):
	model = rij["LBO_Scenarios"][scenario]
	jaren = model["Jaren"][1:]
	open_wb.scenario(assumpties.scenario_label(scenario))

	vergelijkingen = {
		("model", "ebitda"): [jaar["EBITDA"] for jaar in jaren],
		("model", "ni"): [jaar["Nettowinst"] for jaar in jaren],
		("lbo", "w_fcf"): [jaar["FCF"] for jaar in jaren],
		("model", "cash"): [jaar["Cash"] for jaar in jaren],
		("lbo", "d_senior"): [jaar["Senior_Lening"] for jaar in jaren],
		("lbo", "d_rcf"): [jaar["RCF"] for jaar in jaren],
		("lbo", "d_vendor"): [jaar["Vendor_Loan"] for jaar in jaren],
		("lbo", "w_sweep"): [jaar["Cash_Sweep"] for jaar in jaren],
		("model", "ta"): [jaar["Totaal_Activa"] for jaar in jaren],
		("model", "tax_calc"): [jaar["Belasting"] for jaar in jaren],
		("model", "da_total"): [jaar["Afschrijvingen"] for jaar in jaren],
	}
	for (blad, sleutel), verwacht in vergelijkingen.items():
		waarden = open_wb.rij(blad, sleutel)
		for jaar, (excel_waarde, python_waarde) in enumerate(zip(waarden, verwacht), start=1):
			assert abs(excel_waarde - python_waarde) <= TOLERANTIE_EUR, f"{scenario} {sleutel} Y{jaar}"

	assert abs(open_wb.cel("lbo", "x_irr") * 100 - model["LBO_IRR_Exact_Pct"]) <= TOLERANTIE_IRR_PP, scenario
	assert open_wb.cel("lbo", "x_moic") == pytest.approx(model["LBO_MoIC_Exact"], abs=1e-6), scenario
	assert open_wb.cel("lbo", "x_equity") == pytest.approx(model["LBO_Exit_Equity_Jaar5"], abs=TOLERANTIE_EUR), scenario
	assert open_wb.cel("lbo", "x_covenants") == model["LBO_Convenanten"].split(":")[0], scenario
	assert open_wb.checks() == labels.CHECK_OK, scenario


@pytest.mark.parametrize("scenario", assumpties.MODEL_SCENARIOS)
def test_excel_matches_python_per_scenario(excel, tmp_path, rij, filings, scenario):
	pack, cijfers = rij
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	open_wb = Open(excel, pad, kaart)
	try:
		vergelijk_scenario(open_wb, df_rij, scenario)
	finally:
		open_wb.sluit()


def test_excel_matches_python_with_rcf_and_dividend(excel, tmp_path, rij, filings, monkeypatch):
	"""The waterfall branches that a healthy case never reaches."""
	pack, cijfers = rij
	pack["base"]["dso"]["waarden"] = [85.0, 85.0, 70.0, 60.0, 55.0]
	monkeypatch.setattr(config, "LBO_DIVIDEND_PCT", 0.5)
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	assert df_rij["LBO_RCF_Piek"] > 0
	assert df_rij["LBO_Dividend_Cumulatief"] > 0
	open_wb = Open(excel, pad, kaart)
	try:
		vergelijk_scenario(open_wb, df_rij, "base")
	finally:
		open_wb.sluit()


def test_excel_matches_python_with_a_stub(excel, tmp_path, rij, filings, monkeypatch):
	pack, cijfers = rij
	monkeypatch.setattr(config, "LBO_CLOSING_DATUM", "2025-03-31")
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	open_wb = Open(excel, pad, kaart)
	try:
		vergelijk_scenario(open_wb, df_rij, "base")
	finally:
		open_wb.sluit()


def test_the_comparison_itself_detects_a_difference(excel, tmp_path, rij, filings):
	"""Negative control: a changed input in Excel must make the reconciliation fail."""
	pack, cijfers = rij
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	open_wb = Open(excel, pad, kaart)
	try:
		open_wb.lbo.Range("Tax_Rate").Value = config.LBO_TAX_RATE + 0.05
		with pytest.raises(AssertionError):
			vergelijk_scenario(open_wb, df_rij, "base")
	finally:
		open_wb.sluit()


def test_override_flows_through_and_the_balance_still_closes(excel, tmp_path, rij, filings):
	pack, cijfers = rij
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	open_wb = Open(excel, pad, kaart)
	try:
		open_wb.scenario("Base")
		irr_voor = open_wb.cel("lbo", "x_irr")
		ebitda_voor = open_wb.rij("model", "ebitda")
		assert open_wb.samenvatting.Range(kaart["overrides_cel"]).Value == labels.NO

		open_wb.override("base", "inkoop_pct", 3, 0.63)
		open_wb.override("base", "dso", 2, 80)
		open_wb.reken()

		ebitda_na = open_wb.rij("model", "ebitda")
		assert ebitda_na[:2] == pytest.approx(ebitda_voor[:2])
		assert ebitda_na[2] < ebitda_voor[2]
		assert open_wb.cel("lbo", "x_irr") != irr_voor
		assert open_wb.checks() == labels.CHECK_OK
		assert max(open_wb.rij("model", "bs_check")) < 1
		assert open_wb.samenvatting.Range(kaart["overrides_cel"]).Value == labels.YES

		# Another scenario ignores the override of Base
		open_wb.scenario("Upside")
		assert open_wb.cel("lbo", "x_moic") == pytest.approx(df_rij["LBO_Scenarios"]["upside"]["LBO_MoIC_Exact"], abs=1e-6)
	finally:
		open_wb.sluit()


def test_override_matches_python_with_the_same_change(excel, tmp_path, rij, filings):
	"""An override in Excel must give what Python gives with that value as an assumption."""
	pack, cijfers = rij
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)

	aangepast = {s: {d: dict(v) for d, v in drivers.items()} for s, drivers in pack.items()}
	aangepast["base"]["prijsgroei"]["waarden"] = [2.5, 2.0, 3.5, 2.0, 2.2]
	df_rij_2, _, _ = bouw(tmp_path, cijfers, aangepast, filings, "tweede.xlsx")

	open_wb = Open(excel, pad, kaart)
	try:
		open_wb.override("base", "prijsgroei", 3, 0.035)
		vergelijk_scenario(open_wb, df_rij_2, "base")
	finally:
		open_wb.sluit()


def test_formula_coverage_no_hardcoded_forecast(rij, tmp_path, filings):
	"""Every forecast cell of the statements is a formula: no value is pasted in."""
	pack, cijfers = rij
	_, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	ws = openpyxl.load_workbook(pad)[labels.TAB_MODEL]
	rijen = kaart["rijen"]["model"]
	for sleutel in ("rev", "cogs", "pers", "opex", "ebitda", "ta", "tl", "cfo", "cf_end", "tax_calc"):
		for kolom in kaart["kolommen"]["jaren"]:
			waarde = ws[f"{kolom}{rijen[sleutel]}"].value
			assert isinstance(waarde, str) and waarde.startswith("="), f"{sleutel} {kolom}"


def test_fallback_with_little_history_reconciles(excel, tmp_path, filings):
	"""One fiscal year: mechanical drivers, labelled as such, and a single actual column."""
	jaren = filings[-1:]
	cijfers = {**bouw_cijfers(jaren), **TEKSTVELDEN, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_FALLBACK_HISTORY}
	df = calculations.bouw_dataframe([cijfers])
	rij = df.iloc[0]
	assert rij["LBO_Assumptie_Bron"] == labels.ASSUMPTIONS_FALLBACK_HISTORY
	wb, kaart = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(jaren)])
	pad = tmp_path / "fallback.xlsx"
	wb.save(pad)
	open_wb = Open(excel, pad, kaart)
	try:
		for scenario in assumpties.MODEL_SCENARIOS:
			vergelijk_scenario(open_wb, rij, scenario)
		rationale = open_wb.model.Cells(kaart["rijen"]["model"]["ai_base_prijsgroei"], 10).Value
		assert rationale == labels.ASSUMPTIONS_FALLBACK_HISTORY
	finally:
		open_wb.sluit()


def test_missing_fte_data_reconciles(excel, tmp_path, rij, filings):
	pack, cijfers = rij
	for jaar in filings:
		del jaar.codes["9087"]
	cijfers = {**cijfers, "VTE": float("nan")}
	df_rij, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	open_wb = Open(excel, pad, kaart)
	try:
		vergelijk_scenario(open_wb, df_rij, "base")
	finally:
		open_wb.sluit()


def test_gross_margin_schema_reconciles(excel, tmp_path, filings):
	"""A filing without revenue or purchases: the revenue line is the gross margin, COGS is zero."""
	micro = []
	for jaar in filings:
		codes = dict(jaar.codes)
		codes["9900"] = codes["70"] - codes["60"] - codes["61"]
		for code in ("70", "70/76A", "60/66A", "60", "61"):
			del codes[code]
		micro.append(dataclasses.replace(jaar, codes=codes, model="m87-f"))
	cijfers = {**bouw_cijfers(micro), **TEKSTVELDEN}
	assert cijfers["Omzet_Basis"] == labels.BASIS_GROSS_MARGIN
	rij = calculations.bouw_dataframe([cijfers]).iloc[0]
	wb, kaart = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(micro)])
	pad = tmp_path / "micro.xlsx"
	wb.save(pad)
	open_wb = Open(excel, pad, kaart)
	try:
		for scenario in assumpties.MODEL_SCENARIOS:
			vergelijk_scenario(open_wb, rij, scenario)
		assert all(waarde in (0, None) for waarde in open_wb.rij("model", "cogs"))
	finally:
		open_wb.sluit()


def test_company_without_lbo_gets_a_summary_tab_only(tmp_path, cijfers, filings, monkeypatch):
	monkeypatch.setattr(config, "OUTPUT_FOLDER", tmp_path)
	verlies = {**cijfers, "Bedrijfsnaam": "Lossco", "Ondernemingsnummer": "0000.000.000", "Bedrijfswinst_EBIT": -5_000_000.0}
	df = calculations.bouw_dataframe([cijfers, verlies])
	meerjaren = {rij["Ondernemingsnummer"]: bouw_meerjaren(filings) for _, rij in df.iterrows()}
	paden = excel_export.schrijf_per_bedrijf(df, meerjaren)
	excel_export.schrijf_overzicht(df)
	boek = openpyxl.load_workbook(next(pad for pad in paden if "Lossco" in pad.name))
	assert boek.sheetnames == [labels.TAB_SUMMARY]
	assert "No LBO projection possible" in str(boek[labels.TAB_SUMMARY]["A3"].value)
	volledig = openpyxl.load_workbook(next(pad for pad in paden if "Testco" in pad.name))
	assert volledig.sheetnames == [labels.TAB_SUMMARY, labels.TAB_MODEL, labels.TAB_LBO]


def test_workbook_standard(rij, tmp_path, filings):
	pack, cijfers = rij
	_, pad, kaart = bouw(tmp_path, cijfers, pack, filings)
	boek = openpyxl.load_workbook(pad)
	model, lbo = boek[labels.TAB_MODEL], boek[labels.TAB_LBO]
	rijen = kaart["rijen"]["model"]
	eerste = kaart["kolommen"]["jaren"][0]

	assert model.sheet_view.showGridLines is False
	assert model.freeze_panes == "B5"
	assert model[f"{eerste}{rijen['ai_base_prijsgroei']}"].font.color.rgb.endswith("0000FF")
	override = model[f"{eerste}{rijen['ov_base_prijsgroei']}"]
	assert override.value is None
	assert override.fill.fgColor.rgb.endswith("FFF2CC") and override.font.color.rgb.endswith("0000FF")
	assert model[f"{eerste}{rijen['rev']}"].font.color.rgb.endswith("000000")
	assert model[f"{eerste}{rijen['int_exp']}"].font.color.rgb.endswith("006100")
	assert model[f"{eerste}{rijen['rev']}"].number_format == '#,##0,_);(#,##0,);"-"_)'
	assert model[f"{eerste}{rijen['a_prijsgroei']}"].number_format == "0.0%"
	assert 0 < model[f"{eerste}{rijen['ai_base_prijsgroei']}"].value < 1
	assert model["A1"].fill.fgColor.rgb.endswith("1F3864")
	assert "Scenario" in boek.defined_names and len(model.data_validations.dataValidation) == 1
	assert lbo.conditional_formatting and boek.calculation.fullCalcOnLoad
	assert boek.calculation.iterate in (None, False)


def test_ledger_switch_flows_through_excel(excel, tmp_path, rij, filings):
	"""An approved EUR 100k adjustment raises Entry EBITDA in Python and Excel; switching it off in Excel removes it."""
	pack, cijfers = rij
	item = {
		"id": "A1", "categorie": "eenmalig", "omschrijving": "One-off cost.", "richting": "+", "bedrag": 100_000.0,
		"bron": "CSV", "bedrag_geverifieerd": True, "pagina": 1, "citaat_status": "verified", "market_level": None,
		"goedgekeurd": True,
	}
	df = calculations.bouw_dataframe(
		[{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI, "LBO_Adjustments": [item]}]
	)
	df_rij = df.iloc[0]
	historiek = [jaar["Model"] for jaar in bouw_meerjaren(filings)]
	wb, kaart = excel_model.bouw_werkboek(df_rij, historiek)
	pad = tmp_path / "ledger.xlsx"
	wb.save(pad)
	open_wb = Open(excel, pad, kaart)
	try:
		vergelijk_scenario(open_wb, df_rij, "base")
		entry = open_wb.cel("lbo", "entry_ebitda_rij")
		assert entry == pytest.approx(df_rij["Genormaliseerde_EBITDA"], abs=TOLERANTIE_EUR)
		schakelaar = next(
			nr for nr in range(1, 400) if str(open_wb.lbo.Range(f"A{nr}").Value or "").startswith("A1 ")
		)
		open_wb.lbo.Range(f"F{schakelaar}").Value = 0
		open_wb.reken()
		assert open_wb.cel("lbo", "entry_ebitda_rij") == pytest.approx(entry - 100_000.0, abs=TOLERANTIE_EUR)
		assert open_wb.checks() == labels.CHECK_OK
	finally:
		open_wb.sluit()
