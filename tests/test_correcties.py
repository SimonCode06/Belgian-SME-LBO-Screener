"""Phase 3: the financial corrections to the bridge, the EBITDA and the model mechanics."""
from dataclasses import replace

import pytest

from src import config, labels
from src.calculations import bouw_dataframe
from src.nbb_csv import bouw_cijfers
from tests.conftest import TEKSTVELDEN


def met_extra_actief(jaar, codes_actief, bedrag, **memo):
	"""A filing with an extra asset in the given sub-codes, financed by equity: every total still closes."""
	codes = dict(jaar.codes)
	for code in codes_actief:
		codes[code] = codes.get(code, 0.0) + bedrag
	for code in ("29/58", "20/58", "10/49", "10/15"):
		codes[code] += bedrag
	codes.update(memo)
	return replace(jaar, codes=codes)


def rij_van(filings):
	return bouw_dataframe([{**bouw_cijfers(filings), **TEKSTVELDEN}]).iloc[0]


# --- 3.1 Intercompany ---------------------------------------------------------------------

GROEP = 1_000_000.0


@pytest.fixture
def met_groepsvordering(filings):
	return filings[:-1] + [met_extra_actief(filings[-1], ("41", "40/41"), GROEP, **{"9291": GROEP})]


def test_group_receivable_in_41_is_cash_like(filings, met_groepsvordering, monkeypatch):
	monkeypatch.setattr(config, "INTERCOMPANY_BEHANDELING", "buiten_waarde")
	oud = rij_van(met_groepsvordering)
	monkeypatch.setattr(config, "INTERCOMPANY_BEHANDELING", "cash_like")
	nieuw = rij_van(met_groepsvordering)

	assert bouw_cijfers(met_groepsvordering)["Check_Data"] == labels.CHECK_OK
	assert nieuw["Intercompany_Cash_Like"] == GROEP and oud["Intercompany_Cash_Like"] == 0.0
	assert nieuw["Indicatieve_Equity_Value"] == pytest.approx(oud["Indicatieve_Equity_Value"] + GROEP)
	goodwill = [rij["LBO_Jaren"][0]["Goodwill"] for rij in (oud, nieuw)]
	assert goodwill[1] == pytest.approx(goodwill[0] + GROEP)
	assert nieuw["LBO_IRR_Exact_Pct"] == pytest.approx(oud["LBO_IRR_Exact_Pct"])
	assert nieuw["LBO_Sponsor_Equity_Instap"] == pytest.approx(oud["LBO_Sponsor_Equity_Instap"])
	# Settled before closing: no longer on the opening balance
	assert nieuw["LBO_Jaren"][0]["Overige_Activa_Niet_Operationeel"] == pytest.approx(0.0)
	assert nieuw["LBO_Balanscheck"] == labels.CHECK_OK


def test_group_receivable_can_stay_operational(met_groepsvordering, monkeypatch):
	monkeypatch.setattr(config, "INTERCOMPANY_BEHANDELING", "operationeel")
	cijfers = bouw_cijfers(met_groepsvordering)
	assert cijfers["Open_Overige_Activa_Niet_Operationeel"] == 0.0
	assert cijfers["Open_Overige_Activa_Operationeel"] >= GROEP
	assert cijfers["Open_Intercompany_Cash_Like"] == 0.0


def test_group_receivable_beyond_41_stays_working_capital(filings):
	"""9291 above what code 41 holds sits in trade receivables (40): that part is operational."""
	reeks = filings[:-1] + [met_extra_actief(filings[-1], ("41", "40/41"), 300_000.0, **{"9291": GROEP})]
	assert bouw_cijfers(reeks)["Open_Intercompany_Cash_Like"] == 300_000.0


def test_director_receivable_gets_no_value_and_stays_a_heavy_flag(filings):
	reeks = filings[:-1] + [met_extra_actief(filings[-1], ("41", "40/41"), 50_000.0, **{"9500": 50_000.0})]
	cijfers = bouw_cijfers(reeks)
	assert cijfers["Open_Intercompany_Cash_Like"] == 0.0
	assert cijfers["Open_Overige_Activa_Niet_Operationeel"] == 50_000.0
	assert "Receivable from directors" in rij_van(reeks)["Red_Flags"]


# --- 3.2 Minimum cash ---------------------------------------------------------------------


def test_minimum_cash_is_one_month_of_cash_opex_plus_a_share_of_purchases(filings):
	rij = rij_van(filings)
	# Testco 2024: personnel 2.2m, other costs 0.2m, purchases 6.0m
	verwacht = (2_200_000 + 200_000) * config.MIN_CASH_MAANDEN_OPEX / 12 + 6_000_000 * config.MIN_CASH_PCT_INKOOP
	assert rij["Minimum_Cash_Behoefte"] == pytest.approx(verwacht)
	assert rij["Minimum_Operationele_Cash"] == pytest.approx(min(verwacht, rij["Liquide_Middelen"]))


def test_minimum_cash_ignores_net_other_income(filings, monkeypatch):
	"""Other operating income above other costs does not lower the cash the company needs."""
	jaar = filings[-1]
	codes = {**jaar.codes, "640/8": -500_000.0}
	codes["60/66A"] = jaar.codes["60/66A"] - jaar.codes["640/8"] - 500_000.0
	codes["9901"] = codes["70/76A"] - codes["60/66A"]
	reeks = filings[:-1] + [replace(jaar, codes=codes)]
	rij = rij_van(reeks)
	assert rij["Overige_Kosten_Cash"] == 0.0
	assert rij["Minimum_Cash_Behoefte"] == pytest.approx(2_200_000 / 12 + 6_000_000 * config.MIN_CASH_PCT_INKOOP)


# --- 3.3 NWC peg --------------------------------------------------------------------------


def test_equal_twc_percentage_gives_no_adjustment(filings):
	cijfers = bouw_cijfers(filings)
	assert cijfers["NWC_Peg_Jaren"] == 3
	assert cijfers["NWC_Aanpassing"] == pytest.approx(0.0, abs=1e-6)


def met_gerekte_leveranciers(filings, extra=500_000.0):
	"""Last year: payables 0.5m higher and cash 0.5m higher (suppliers paid late before the sale)."""
	jaar = filings[-1]
	codes = dict(jaar.codes)
	for code in ("44", "42/48", "17/49", "10/49"):
		codes[code] += extra
	for code in ("54/58", "29/58", "20/58"):
		codes[code] += extra
	return filings[:-1] + [replace(jaar, codes=codes)]


def test_stretched_payables_lower_the_price_for_the_seller_not_the_sponsor_equity(filings):
	basis, gerekt = rij_van(filings), rij_van(met_gerekte_leveranciers(filings))
	assert bouw_cijfers(met_gerekte_leveranciers(filings))["Check_Data"] == labels.CHECK_OK
	aanpassing = gerekt["NWC_Aanpassing"]
	assert aanpassing < 0
	# Peg = average TWC % over three year-ends x last revenue
	twc = [0.15 * omzet + 0.05 * inkoop - 0.12 * inkoop for omzet, inkoop in ((9.0e6, 5.4e6), (9.5e6, 5.7e6), (10.0e6, 6.0e6))]
	twc[-1] -= 500_000.0
	pct = sum(t / o for t, o in zip(twc, (9.0e6, 9.5e6, 10.0e6))) / 3
	assert aanpassing == pytest.approx(twc[-1] - pct * 10.0e6)

	assert gerekt["LBO_Sponsor_Equity_Instap"] == pytest.approx(basis["LBO_Sponsor_Equity_Instap"])
	assert gerekt["LBO_Balanscheck"] == labels.CHECK_OK
	jaren = gerekt["LBO_Jaren"]
	assert jaren[0]["Cash"] == pytest.approx(gerekt["Minimum_Operationele_Cash"] - aanpassing)
	assert jaren[1]["NWC_Normalisatie"] == pytest.approx(-aanpassing)


def test_nwc_peg_can_be_switched_off(filings, monkeypatch):
	monkeypatch.setattr(config, "NWC_PEG_TOEPASSEN", False)
	assert bouw_cijfers(met_gerekte_leveranciers(filings))["NWC_Aanpassing"] == 0.0


# --- 3.4 Adjustment ledger ----------------------------------------------------------------

from src import normalisaties  # noqa: E402


def ledger_item(**wijzig):
	item = {
		"id": "A1", "categorie": "eenmalig", "omschrijving": "One-off legal cost.", "richting": "+",
		"bedrag": 100_000.0, "bron": "CSV code 6631", "bedrag_geverifieerd": True, "pagina": 20,
		"citaat_status": "verified", "market_level": None, "goedgekeurd": True,
	}
	item.update(wijzig)
	return item


@pytest.mark.parametrize(
	"wijzig, effect",
	[
		({}, 100_000.0),
		({"goedgekeurd": False}, 0.0),
		({"bedrag_geverifieerd": False}, 0.0),  # an AI amount never counts until verified
		({"richting": "-"}, -100_000.0),
		({"categorie": "bestuurdersvergoeding", "bedrag": 552_680.0}, 0.0),  # no market level yet
		({"categorie": "bestuurdersvergoeding", "bedrag": 552_680.0, "market_level": 300_000.0}, 252_680.0),
	],
)
def test_ledger_effect(wijzig, effect):
	assert normalisaties.totaal([ledger_item(**wijzig)]) == pytest.approx(effect)


def test_ledger_is_annualised():
	assert normalisaties.totaal([ledger_item()], maanden=18) == pytest.approx(100_000.0 * 12 / 18)


def test_approved_item_raises_entry_ebitda(cijfers):
	zonder = bouw_dataframe([cijfers]).iloc[0]
	met = bouw_dataframe([{**cijfers, "LBO_Adjustments": [ledger_item()]}]).iloc[0]
	assert met["Ledger_EBITDA"] == 100_000.0
	assert met["Genormaliseerde_EBITDA"] == pytest.approx(zonder["Genormaliseerde_EBITDA"] + 100_000.0)
	assert met["LBO_Instap_EV"] == pytest.approx(met["Genormaliseerde_EBITDA"] * met["Instap_Multiple"])
	assert met["LBO_Balanscheck"] == labels.CHECK_OK
	# A lasting adjustment: the screening forecast keeps the higher margin
	jaar5 = [rij["LBO_Scenarios"]["screening_base"]["Jaren"][-1]["EBITDA"] for rij in (zonder, met)]
	assert jaar5[1] > jaar5[0]


def test_unapproved_items_change_nothing(cijfers):
	zonder = bouw_dataframe([cijfers]).iloc[0]
	met = bouw_dataframe([{**cijfers, "LBO_Adjustments": [ledger_item(goedgekeurd=False)]}]).iloc[0]
	assert met["Genormaliseerde_EBITDA"] == zonder["Genormaliseerde_EBITDA"]
	assert met["LBO_IRR_Exact_Pct"] == zonder["LBO_IRR_Exact_Pct"]


def test_ledger_file_is_written_once_and_keeps_the_analyst_decisions(tmp_path, monkeypatch):
	import json

	monkeypatch.setattr(config, "SNAPSHOT_FOLDER", tmp_path)
	pad = normalisaties.ledger_pad("0123.456.789", "2024")
	assert pad.name == "0123456789_FY2024_adjustments.json"
	ai = [{
		"categorie": "bestuurdersvergoeding", "omschrijving": "Director pay.", "richting": "+", "bedrag_gebruikt": 552_680.0,
		"bedrag_bron": "CSV code 9503", "bedrag_geverifieerd": True, "pagina": 34, "citaat_status": "verified",
	}]
	items = normalisaties.laad_of_maak(pad, ai, "Testco")
	assert items[0]["goedgekeurd"] is False and items[0]["market_level"] is None
	inhoud = json.loads(pad.read_text(encoding="utf-8"))
	inhoud["items"][0].update(goedgekeurd=True, market_level=250_000.0)
	pad.write_text(json.dumps(inhoud), encoding="utf-8")
	opnieuw = normalisaties.laad_of_maak(pad, ai, "Testco")  # a new AI run never overwrites
	assert opnieuw[0]["goedgekeurd"] is True
	assert normalisaties.totaal(opnieuw) == pytest.approx(302_680.0)


def test_no_ai_items_writes_no_file(tmp_path, monkeypatch):
	monkeypatch.setattr(config, "SNAPSHOT_FOLDER", tmp_path)
	assert normalisaties.laad_of_maak(normalisaties.ledger_pad("1", "2024"), [], "X") == []
	assert not list(tmp_path.iterdir())


def test_workbook_has_the_ledger_table_with_switches(cijfers, filings):
	from src import excel_model
	from src.nbb_csv import bouw_meerjaren

	rij = bouw_dataframe([{**cijfers, "LBO_Adjustments": [ledger_item(), ledger_item(id="A2", goedgekeurd=False)]}]).iloc[0]
	wb, kaart = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(filings)])
	assert "Ledger_Total" in wb.defined_names
	ws = wb[labels.TAB_LBO]
	waarden = [ws.cell(row=r, column=6).value for r in range(1, ws.max_row + 1) if str(ws.cell(row=r, column=1).value).startswith("A")]
	assert waarden[:2] == [1, 0]
	entry = ws[f"C{kaart['rijen']['lbo']['entry_ebitda_rij']}"].value
	assert entry.endswith("+Ledger_Total")


def test_approved_item_also_lowers_the_ai_cost_ratio(cijfers, filings):
	from src.assumpties import AssumptieAntwoord, pack_uit_antwoord
	from tests.test_assumpties import nagebootste_gemini_respons

	def rij(items):
		pack = pack_uit_antwoord(AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))
		return bouw_dataframe([{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI, "LBO_Adjustments": items}]).iloc[0]

	zonder, met = rij([]), rij([ledger_item()])
	verschil = 100_000.0 / zonder["Omzet_of_Brutomarge"] * 100
	a, b = (r["LBO_Assumpties"]["base"]["overige_kosten_pct"]["waarden"][0] for r in (zonder, met))
	assert b == pytest.approx(a - verschil)
	jaar1 = [r["LBO_Scenarios"]["base"]["Jaren"][1] for r in (zonder, met)]
	assert jaar1[1]["EBITDA"] - jaar1[0]["EBITDA"] == pytest.approx(verschil / 100 * jaar1[1]["Omzet"])


# --- 3.5 Multiples ------------------------------------------------------------------------

from src.lbo_model import kies_multiples  # noqa: E402


def test_multiples_have_no_jump():
	onder, boven = kies_multiples(999_000.0), kies_multiples(1_001_000.0)
	assert abs(onder[0] - boven[0]) < 0.01 and abs(onder[1] - boven[1]) < 0.01


def test_multiples_rise_monotonically_and_stay_flat_outside_the_anchors():
	reeks = [kies_multiples(float(ebitda)) for ebitda in range(0, 12_000_001, 50_000)]
	assert all(b[0] >= a[0] and b[1] >= a[1] for a, b in zip(reeks, reeks[1:]))
	assert kies_multiples(100_000.0) == (4.0, 1.5) and kies_multiples(20_000_000.0) == (7.0, 3.5)
	assert kies_multiples(750_000.0) == (4.5, 2.0)
	assert kies_multiples(1_250_000.0) == pytest.approx((4.75, 2.25))
