"""AI assumptions: schema validation, soft flags that never correct, scenario order, and use in the model."""
import copy
import json

import pytest
from pydantic import ValidationError

from src import assumpties, calculations, config, labels
from src.assumpties import AssumptieAntwoord, DRIVERS, SCENARIOS, pack_uit_antwoord
from src.lbo_model import bereken_lbo

BASISWAARDEN = {
	"prijsgroei": 2.0,
	"volumegroei": 1.0,
	"loonindexering": 2.0,
	"vte_elasticiteit": 0.8,
	"inkoop_pct": 60.0,
	"overige_kosten_pct": 2.0,
	"da_pct": 20.0,
	"capex_pct": 0.9,
	"dso": 54.0,
	"dio": 30.0,
	"dpo": 44.0,
	"dagen_vooruitbetaling": 0.0,
}
RICHTING_STAP = {"prijsgroei": 0.5, "volumegroei": 1.0, "loonindexering": -0.5, "inkoop_pct": -1.0, "overige_kosten_pct": -0.5, "capex_pct": -0.1, "dso": -2.0, "dio": -2.0, "dpo": 2.0}


def nagebootste_gemini_respons():
	"""The JSON Gemini would return, with Downside < Base < Upside in every favourable direction."""
	regels = []
	for scenario, stap in (("base", 0), ("downside", -1), ("upside", 1)):
		for sleutel, waarde in BASISWAARDEN.items():
			regels.append(
				{
					"scenario": scenario,
					"driver": sleutel,
					"waarden": [waarde + RICHTING_STAP.get(sleutel, 0.0) * stap] * 5,
					"rationale": "In line with the historical trend.",
					"source": 'p. 12: "new contract signed"',
					"confidence": "medium",
				}
			)
	return {"regels": regels}


def regel_van(respons, scenario, driver):
	return next(r for r in respons["regels"] if r["scenario"] == scenario and r["driver"] == driver)


@pytest.fixture
def pack():
	return pack_uit_antwoord(AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))


def pack_jaren(**velden):
	jaar = {"Inkoop_Pct": 60.0, "Overige_Pct": 2.0, "DA_Pct": 20.0, "Capex_Pct": 0.9, "DSO": 54.0, "DIO": 30.0, "DPO": 44.0, "Advance_Days": 0.0}
	return [{**jaar, **velden}]


# (a) the Pydantic schema
def test_schema_accepts_a_simulated_gemini_response():
	antwoord = AssumptieAntwoord.model_validate_json(json.dumps(nagebootste_gemini_respons()))
	pack = pack_uit_antwoord(antwoord)
	assert len(antwoord.regels) == 36
	assert pack["base"]["dso"]["waarden"] == [54.0] * 5
	assert pack["upside"]["prijsgroei"]["confidence"] == "medium"
	assert pack["base"]["dso"]["source"].startswith("p. 12")


def test_schema_covers_every_driver_of_the_model():
	assert set(BASISWAARDEN) == {driver.sleutel for driver in DRIVERS}


@pytest.mark.parametrize("aantal", [4, 6])
def test_schema_rejects_a_wrong_number_of_years(aantal):
	respons = nagebootste_gemini_respons()
	regel_van(respons, "base", "dso")["waarden"] = [54.0] * aantal
	with pytest.raises(ValidationError):
		AssumptieAntwoord.model_validate(respons)


def test_schema_rejects_an_unknown_confidence():
	respons = nagebootste_gemini_respons()
	regel_van(respons, "base", "dso")["confidence"] = "certain"
	with pytest.raises(ValidationError):
		AssumptieAntwoord.model_validate(respons)


def test_schema_rejects_a_missing_driver():
	respons = nagebootste_gemini_respons()
	respons["regels"].remove(regel_van(respons, "downside", "dpo"))
	with pytest.raises(ValidationError):
		AssumptieAntwoord.model_validate(respons)


def test_schema_rejects_a_duplicate_row():
	respons = nagebootste_gemini_respons()
	respons["regels"][0] = dict(respons["regels"][1])
	with pytest.raises(ValidationError):
		AssumptieAntwoord.model_validate(respons)


def test_schema_rejects_an_unknown_driver():
	respons = nagebootste_gemini_respons()
	respons["regels"][0]["driver"] = "marge"
	with pytest.raises(ValidationError):
		AssumptieAntwoord.model_validate(respons)


# (b) soft checks flag and never change a value
def test_clean_assumptions_get_no_flags(pack):
	assert assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0) == []


def test_bound_breach_flags_but_keeps_the_value(pack):
	pack["base"]["volumegroei"]["waarden"] = [40.0] * 5
	voor = copy.deepcopy(pack["base"]["volumegroei"]["waarden"])
	regels = assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert pack["base"]["volumegroei"]["waarden"] == voor
	assert pack["base"]["volumegroei"]["vlaggen"]
	assert any(labels.DRIVER_REVENUE_GROWTH in regel for regel in regels)


def test_history_breach_flags_but_keeps_the_value(pack):
	pack["base"]["inkoop_pct"]["waarden"] = [64.0] * 5  # 4 pp above the historical maximum
	voor = copy.deepcopy(pack)
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert pack["base"]["inkoop_pct"]["waarden"] == [64.0] * 5
	assert pack["base"]["inkoop_pct"]["vlaggen"]
	for scenario in SCENARIOS:
		for driver in DRIVERS:
			assert pack[scenario][driver.sleutel]["waarden"] == voor[scenario][driver.sleutel]["waarden"]


def test_within_three_points_of_history_is_not_flagged(pack):
	pack["base"]["inkoop_pct"]["waarden"] = [62.9] * 5
	pack["upside"]["inkoop_pct"]["waarden"] = [59.0] * 5
	pack["downside"]["inkoop_pct"]["waarden"] = [62.95] * 5
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert not pack["base"]["inkoop_pct"]["vlaggen"]


def test_days_use_the_days_tolerance(pack):
	pack["base"]["dso"]["waarden"] = [68.0] * 5  # 14 days above history: below the tolerance of 15
	pack["downside"]["dso"]["waarden"] = [69.0] * 5
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert not pack["base"]["dso"]["vlaggen"]


def test_ebitda_margin_outside_bounds_is_flagged(pack):
	pack["base"]["inkoop_pct"]["waarden"] = [99.0] * 5
	regels = assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert any(labels.DRIVER_EBITDA_MARGIN in regel for regel in regels)


def test_flags_reach_the_red_flags_and_the_model_uses_the_value_unchanged(cijfers, pack):
	pack["base"]["volumegroei"]["waarden"] = [40.0] * 5
	rij = calculations.bouw_dataframe(
		[{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI, "LBO_Driver_Pack": {"Fiscal_Years": pack_jaren()}}]
	).iloc[0]
	assert "Assumption flag" in rij["Red_Flags"]
	assert rij["LBO_Jaren"][1]["Omzetgroei_Pct"] == pytest.approx(((1.40 * 1.02) - 1) * 100)


# (c) scenario order
def test_inverted_scenarios_are_flagged(pack):
	pack["downside"]["prijsgroei"]["waarden"] = [9.0] * 5  # better than Base
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert any("Downside is better than Base" in vlag for vlag in pack["downside"]["prijsgroei"]["vlaggen"])


def test_cost_ratio_direction_is_respected(pack):
	pack["upside"]["inkoop_pct"]["waarden"] = [61.5] * 5  # higher cost than Base: Base beats Upside
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert any("Base is better than Upside" in vlag for vlag in pack["base"]["inkoop_pct"]["vlaggen"])


def test_one_inverted_year_is_named(pack):
	pack["downside"]["dpo"]["waarden"] = [42.0, 42.0, 50.0, 42.0, 42.0]
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert any("Y3" in vlag and "Y1" not in vlag for vlag in pack["downside"]["dpo"]["vlaggen"])


def test_equal_scenarios_are_not_inverted(pack):
	pack["upside"]["loonindexering"]["waarden"] = pack["base"]["loonindexering"]["waarden"]
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert not pack["base"]["loonindexering"]["vlaggen"]


def test_da_has_no_favourable_direction(pack):
	pack["downside"]["da_pct"]["waarden"] = [21.0] * 5
	pack["upside"]["da_pct"]["waarden"] = [19.0] * 5
	assumpties.controleer(pack, pack_jaren(), 10_000_000.0, 2_200_000.0)
	assert not pack["base"]["da_pct"]["vlaggen"] and not pack["downside"]["da_pct"]["vlaggen"]


# Model and fallback
def test_model_reads_a_different_value_per_year(cijfers, pack):
	pack["base"]["prijsgroei"]["waarden"] = [1.0, 2.0, 3.0, 4.0, 5.0]
	rij = calculations.bouw_dataframe(
		[{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI, "LBO_Driver_Pack": {"Fiscal_Years": pack_jaren()}}]
	).iloc[0]
	groei = [jaar["Omzetgroei_Pct"] for jaar in rij["LBO_Jaren"][1:]]
	assert groei == pytest.approx([((1.01) * (1 + p / 100) - 1) * 100 for p in (1, 2, 3, 4, 5)])


def test_fallback_is_labelled_and_runs(cijfers):
	rij = calculations.bouw_dataframe([{**cijfers, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_FALLBACK_HISTORY}]).iloc[0]
	voorstel = rij["LBO_Assumpties"]["base"]["inkoop_pct"]
	assert voorstel["rationale"] == labels.ASSUMPTIONS_FALLBACK_HISTORY
	assert rij["LBO_Assumptie_Bron"] == labels.ASSUMPTIONS_FALLBACK_HISTORY
	assert rij["LBO_Balanscheck"] == labels.CHECK_OK


def test_all_integrity_checks_pass_on_ai_assumptions_in_every_scenario(cijfers, pack):
	rij = calculations.bouw_dataframe([{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI}]).iloc[0]
	assert rij["LBO_Balanscheck"] == labels.CHECK_OK
	for scenario, model in rij["LBO_Scenarios"].items():
		assert all(test["Uitkomst"] != labels.CHECK_ERROR for test in model["Integriteit"]), scenario


def test_a_nan_assumption_gives_no_lbo_instead_of_a_silent_fallback(cijfers, pack):
	pack["base"]["dso"]["waarden"] = [float("nan")] * 5
	rij = calculations.bouw_dataframe([{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI}]).iloc[0]
	assert rij["LBO_Convenanten"].startswith(labels.NOT_APPLICABLE)


def test_opening_balance_interest_is_the_configured_basis():
	assert config.LBO_RENTE_BASIS == "begin"


def test_stub_gives_five_periods(cijfers, pack, monkeypatch):
	monkeypatch.setattr(config, "LBO_CLOSING_DATUM", "2025-03-31")
	rij = calculations.bouw_dataframe([{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI}]).iloc[0]
	assert len(rij["LBO_Jaren"]) == 6
	assert rij["LBO_Jaren"][1]["Fractie"] == pytest.approx(275 / 365)
	assert rij["LBO_Balanscheck"] == labels.CHECK_OK


def test_late_closing_is_limited_and_flagged(cijfers, pack, monkeypatch):
	monkeypatch.setattr(config, "LBO_CLOSING_DATUM", "2027-06-30")
	rij = calculations.bouw_dataframe([{**cijfers, "LBO_Assumpties": pack, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI}]).iloc[0]
	assert rij["LBO_Closing_Datum"] == "2025-12-30"
	assert "Closing date limited" in rij["Red_Flags"]
