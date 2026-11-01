"""De screening case: regels uit de jaarrekening plus een vaste stress, los van Gemini."""
import copy

import pytest

from src import config, labels
from src.assumpties import AssumptieAntwoord, MODEL_SCENARIOS, pack_uit_antwoord, scenario_label
from src.calculations import bouw_dataframe
from src.nbb_csv import bouw_driver_pack
from tests.test_assumpties import nagebootste_gemini_respons


def ai_rij(cijfers, filings, respons=None):
	pack = pack_uit_antwoord(AssumptieAntwoord.model_validate(respons or nagebootste_gemini_respons()))
	return {
		**cijfers,
		"LBO_Assumpties": pack,
		"LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI,
		"LBO_Driver_Pack": bouw_driver_pack(filings),
	}


def forecast(rij, scenario):
	return [jaar for jaar in rij["LBO_Scenarios"][scenario]["Jaren"] if jaar["Jaar"] > 0]


def test_every_scenario_is_calculated(cijfers, filings):
	rij = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	assert set(rij["LBO_Scenarios"]) == set(MODEL_SCENARIOS)
	assert set(rij["LBO_Assumpties"]) == set(MODEL_SCENARIOS)
	assert scenario_label("screening_stress") == "Screening Stress"


def test_stress_ebitda_is_the_haircut_of_the_screening_base(cijfers, filings):
	rij = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	base, stress = forecast(rij, "screening_base"), forecast(rij, "screening_stress")
	assert len(base) == len(stress) == config.LBO_HOLDING_PERIOD_YEARS
	for jaar_b, jaar_s, haircut in zip(base, stress, config.LBO_STRESS_EBITDA_HAIRCUT):
		assert jaar_s["EBITDA"] == pytest.approx((1 - haircut) * jaar_b["EBITDA"], abs=1.0)
		assert jaar_s["Omzet"] == pytest.approx(jaar_b["Omzet"], abs=1.0)  # same revenue
		assert jaar_s["Handelsvorderingen"] == pytest.approx(jaar_b["Handelsvorderingen"], abs=1.0)  # same NWC


def test_stress_holds_with_a_stub_period(cijfers, filings, monkeypatch):
	monkeypatch.setattr(config, "LBO_CLOSING_DATUM", "2025-06-30")
	rij = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	assert forecast(rij, "screening_base")[0]["Fractie"] < 1
	for jaar_b, jaar_s, haircut in zip(
		forecast(rij, "screening_base"), forecast(rij, "screening_stress"), config.LBO_STRESS_EBITDA_HAIRCUT
	):
		assert jaar_s["EBITDA"] == pytest.approx((1 - haircut) * jaar_b["EBITDA"], abs=1.0)


def test_screening_case_does_not_depend_on_the_ai_snapshot(cijfers, filings):
	ander = copy.deepcopy(nagebootste_gemini_respons())
	for regel in ander["regels"]:
		regel["waarden"] = [waarde * 1.5 for waarde in regel["waarden"]]
	a = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	b = bouw_dataframe([ai_rij(cijfers, filings, ander)]).iloc[0]
	assert a["LBO_Scenarios"]["base"]["LBO_MoIC_Exact"] != b["LBO_Scenarios"]["base"]["LBO_MoIC_Exact"]
	for scenario in ("screening_base", "screening_stress"):
		assert a["LBO_Scenarios"][scenario]["LBO_MoIC_Exact"] == b["LBO_Scenarios"][scenario]["LBO_MoIC_Exact"]
	for kolom in ("LBO_Screening_IRR_Pct", "LBO_Stress_IRR_Pct", "LBO_Stress_Convenanten"):
		assert a[kolom] == b[kolom]


def test_without_ai_the_screening_base_equals_the_fallback_base(cijfers):
	rij = bouw_dataframe([{**cijfers, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_FALLBACK_NO_AI}]).iloc[0]
	assert rij["LBO_Screening_IRR_Pct"] == rij["Indicatieve_IRR_Pct"]
	assert rij["LBO_Stress_IRR_Pct"] < rij["LBO_Screening_IRR_Pct"]


def test_screening_drivers_are_labelled_rule_based(cijfers, filings):
	rij = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	assert rij["LBO_Assumpties"]["screening_base"]["dso"]["source"] == labels.ASSUMPTIONS_SCREENING
	assert "standard stress" in rij["LBO_Assumpties"]["screening_stress"]["overige_kosten_pct"]["rationale"]


def test_the_assessment_does_not_use_the_screening_case_yet(cijfers, filings, monkeypatch):
	"""Phase 1 only shows the screening case. The status still follows the analyst case."""
	voor = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]["LBO_Status"]
	monkeypatch.setattr(config, "LBO_STRESS_EBITDA_HAIRCUT", [0.9] * 5)
	na = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	assert na["LBO_Status"] == voor
	assert na["LBO_Stress_Convenanten"].startswith(labels.COVENANTS_BREACHED)
