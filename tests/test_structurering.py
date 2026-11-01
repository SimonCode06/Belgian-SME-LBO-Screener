"""Phase 4: debt capacity (Screening Stress) and ability-to-pay (Screening Base)."""
from dataclasses import replace

import pytest

from src import config, labels, structurering
from src.calculations import bouw_dataframe
from src.lbo_model import bereken_lbo, standaard_structuur
from src.nbb_csv import bouw_cijfers
from tests.conftest import TEKSTVELDEN, neerlegging


@pytest.fixture
def rij(cijfers):
	return bouw_dataframe([cijfers]).iloc[0]


def stress_model(rij, multiple):
	basis = standaard_structuur(rij["Genormaliseerde_EBITDA"])
	return bereken_lbo(rij, "screening_stress", replace(basis, senior_multiple=multiple))


# --- 4.1 Debt capacity --------------------------------------------------------------------


def test_at_the_capacity_every_covenant_holds_and_just_above_one_fails(rij):
	capaciteit = rij["Debt_Capacity_Multiple"]
	assert rij["Debt_Capacity_Status"] == labels.CAPACITY_OK
	assert config.LBO_DEBT_CAPACITY_MIN <= capaciteit < config.LBO_MAX_SENIOR_MULTIPLE
	assert structurering.haalt_covenants(stress_model(rij, capaciteit))
	assert not structurering.haalt_covenants(stress_model(rij, capaciteit + 0.1))
	assert rij["Debt_Capacity_EUR"] == pytest.approx(capaciteit * rij["Genormaliseerde_EBITDA"])
	assert rij["Debt_Capacity_Bindend"].split()[0] in ("DSCR", "Interest", "Leverage", "Minimum", "RCF", "EBITDA")


def filings_met_overige(overige):
	return [
		neerlegging(2022, 9_000_000.0, 5_400_000.0, 2_000_000.0, overige=overige),
		neerlegging(2023, 9_500_000.0, 5_700_000.0, 2_100_000.0, overige=overige),
		neerlegging(2024, 10_000_000.0, 6_000_000.0, 2_200_000.0, overige=overige),
	]


def test_more_ebitda_never_gives_less_capacity():
	basis = bouw_dataframe([{**bouw_cijfers(filings_met_overige(200_000.0)), **TEKSTVELDEN}]).iloc[0]
	beter = bouw_dataframe([{**bouw_cijfers(filings_met_overige(40_000.0)), **TEKSTVELDEN}]).iloc[0]
	assert beter["Genormaliseerde_EBITDA"] == pytest.approx(basis["Genormaliseerde_EBITDA"] * 1.1)
	assert beter["Debt_Capacity_EUR"] >= basis["Debt_Capacity_EUR"]


def test_no_capacity_when_even_half_a_turn_fails(cijfers, monkeypatch):
	monkeypatch.setattr(config, "LBO_COVENANT_MIN_DSCR", 50.0)
	rij = bouw_dataframe([cijfers]).iloc[0]
	assert rij["Debt_Capacity_Status"] == labels.CAPACITY_NONE
	assert rij["Debt_Capacity_Multiple"] == 0.0 and rij["Debt_Capacity_Bindend"] == "DSCR Y1"


def test_upper_bound_of_the_search(cijfers, monkeypatch):
	monkeypatch.setattr(config, "LBO_MAX_SENIOR_MULTIPLE", 0.6)
	rij = bouw_dataframe([cijfers]).iloc[0]
	assert rij["Debt_Capacity_Multiple"] == 0.6 and rij["Debt_Capacity_Bindend"] == labels.BINDING_CAP


def test_no_ebitda_gives_no_analysis(cijfers):
	rij = bouw_dataframe([{**cijfers, "Bedrijfswinst_EBIT": -2_000_000.0}]).iloc[0]
	assert rij["Debt_Capacity_Status"] == labels.CAPACITY_NA and rij["ATP_Status"] == labels.ATP_NA


# --- 4.2 Ability-to-pay -------------------------------------------------------------------


def test_irr_at_the_max_multiple_equals_the_target(rij):
	assert rij["ATP_Status"] == labels.ATP_OK
	assert abs(rij["ATP_IRR_Pct"] - config.LBO_MIN_IRR_PCT) < 0.1
	assert rij["ATP_Senior_Multiple"] <= min(rij["Debt_Capacity_Multiple"], rij["Senior_Multiple"]) + 1e-9
	assert rij["ATP_Max_EV"] == pytest.approx(rij["ATP_Max_Entry_Multiple"] * rij["Genormaliseerde_EBITDA"])
	assert rij["ATP_Headroom_Pct"] == pytest.approx((rij["ATP_Max_EV"] / rij["Indicatieve_EV"] - 1) * 100)
	assert rij["ATP_Max_Equity_Price"] == pytest.approx(rij["ATP_Max_EV"] - rij["Adjusted_Net_Debt"] + rij["NWC_Aanpassing"])


def test_a_higher_target_irr_gives_a_lower_max_ev(cijfers, monkeypatch):
	laag = bouw_dataframe([cijfers]).iloc[0]["ATP_Max_EV"]
	monkeypatch.setattr(config, "LBO_MIN_IRR_PCT", 30.0)
	hoog = bouw_dataframe([cijfers]).iloc[0]["ATP_Max_EV"]
	assert hoog < laag


def test_not_achievable_at_an_impossible_target(cijfers, monkeypatch):
	monkeypatch.setattr(config, "LBO_MIN_IRR_PCT", 500.0)
	rij = bouw_dataframe([cijfers]).iloc[0]
	assert rij["ATP_Status"] == labels.ATP_NOT_ACHIEVABLE and rij["ATP_AI_Status"] == labels.ATP_NOT_ACHIEVABLE


def test_senior_debt_respects_the_minimum_sponsor_equity():
	senior = structurering.max_senior_voor_equity(5.0, 0.10)
	kosten = config.LBO_TRANSACTIEKOSTEN_PCT + config.LBO_FINANCIERINGSKOSTEN_PCT
	sponsor = 5.0 * (1 + kosten) - senior - 0.5
	assert sponsor == pytest.approx(config.LBO_MIN_SPONSOR_EQUITY_PCT * 5.0 * (1 + kosten))


# --- 4.3 In the workbook ------------------------------------------------------------------


def test_workbook_block_and_live_cell(rij, filings):
	from src import excel_model
	from src.nbb_csv import bouw_meerjaren

	wb, kaart = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(filings)])
	ws = wb[labels.TAB_LBO]
	rl = kaart["rijen"]["lbo"]
	assert ws[f"C{rl['dc_multiple']}"].value == pytest.approx(rij["Debt_Capacity_Multiple"])
	assert ws[f"C{rl['atp_multiple']}"].value == pytest.approx(rij["ATP_Max_Entry_Multiple"])
	assert ws[f"C{rl['dc_binding']}"].value == rij["Debt_Capacity_Bindend"]
	live = ws[f"C{rl['dc_live']}"].value
	assert live.startswith('=IF(Scenario="Screening Stress"') and "Min_Cash" in live


# --- Senior financing by deal size ----------------------------------------------------------

from src.lbo_model import senior_markt  # noqa: E402


@pytest.mark.parametrize(
	"ebitda, aflossing, rente",
	[(1_000_000, 1 / 7, 0.065), (5_000_000, 0.5 / 6 + 0.005, 0.070), (11_500_000, 0.01, 0.080)],
)
def test_senior_follows_the_market_for_the_deal_size(ebitda, aflossing, rente):
	_, a, r = senior_markt(ebitda)
	assert a == pytest.approx(aflossing) and r == rente


def test_unitranche_amortises_one_percent_and_repays_at_exit(cijfers, monkeypatch):
	monkeypatch.setattr(config, "LBO_SENIOR_MARKT", [(float("inf"), "Unitranche", 0.01, 0.08)])
	monkeypatch.setattr(config, "LBO_CASH_SWEEP_PCT", 0.0)
	rij = bouw_dataframe([cijfers]).iloc[0]
	assert rij["Senior_Type"] == "Unitranche" and rij["Senior_Rente_Pct"] == pytest.approx(8.0)
	model = rij["LBO_Scenarios"]["screening_base"]
	senior_0 = model["LBO_Senior_Schuld"]
	jaar = model["Jaren"][1]
	assert jaar["Verplichte_Aflossing"] == pytest.approx(senior_0 * 0.01)
	assert jaar["Rente_Senior"] == pytest.approx(senior_0 * 0.08)
	assert model["Jaren"][-1]["Senior_Lening"] == pytest.approx(senior_0 * 0.95)  # the rest is in the exit net debt
	assert model["LBO_Balanscheck"] == labels.CHECK_OK


def test_bullet_debt_gives_more_capacity_than_amortising_debt(cijfers, monkeypatch):
	bank = bouw_dataframe([cijfers]).iloc[0]["Debt_Capacity_Multiple"]
	monkeypatch.setattr(config, "LBO_SENIOR_MARKT", [(float("inf"), "Unitranche", 0.01, 0.08)])
	unitranche = bouw_dataframe([cijfers]).iloc[0]["Debt_Capacity_Multiple"]
	assert unitranche > bank
