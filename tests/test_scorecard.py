"""Phase 5.3-5.4: scorecard and robustness grid."""
import copy

import pytest

from src import config, labels, scorecard, structurering
from src.calculations import bouw_dataframe
from src.lbo_model import Structuur, bereken_lbo
from tests.test_screening import ai_rij
from tests.test_assumpties import nagebootste_gemini_respons


@pytest.fixture
def rij(cijfers):
	return bouw_dataframe([cijfers]).iloc[0]


def test_linear_scoring_and_bounds():
	assert scorecard.lineair(0.5, 0.5, 3.0) == 0.0
	assert scorecard.lineair(3.0, 0.5, 3.0) == 100.0
	assert scorecard.lineair(1.75, 0.5, 3.0) == pytest.approx(50.0)
	assert scorecard.lineair(10.0, 0.5, 3.0) == 100.0 and scorecard.lineair(-1.0, 0.5, 3.0) == 0.0
	assert scorecard.lineair(3.0, 5.0, 1.0) == pytest.approx(50.0)  # lower is better
	assert scorecard.lineair(float("nan"), 0, 1) == 0.0


def test_weights_add_up_to_one():
	assert sum(config.SCORE_GEWICHTEN.values()) == pytest.approx(1.0)


def test_score_has_six_explained_components(rij):
	lijst = rij["Score_Componenten"]
	assert [c["sleutel"] for c in lijst] == list(config.SCORE_GEWICHTEN)
	assert all(0 <= c["score"] <= 100 and c["reden"] for c in lijst)
	assert rij["Score"] == pytest.approx(sum(c["gewicht"] * c["score"] for c in lijst))
	assert labels.SCORE_LABELS["debt_capacity"] in rij["Score_Toelichting"]


def test_governance_component_counts_high_and_medium_flags(cijfers):
	een_hoge = bouw_dataframe([{**cijfers, "Eigen_Vermogen": -1.0}]).iloc[0]
	twee_hoge = bouw_dataframe([{**cijfers, "Eigen_Vermogen": -1.0, "Commissaris_Oordeel": labels.OPINION_ADVERSE}]).iloc[0]

	def gov(r):
		return next(c["score"] for c in r["Score_Componenten"] if c["sleutel"] == "governance")

	middel = een_hoge["Aantal_Middel_Vlaggen"]
	assert gov(een_hoge) == pytest.approx(max(0, 100 - 40 - 15 * middel))
	assert gov(twee_hoge) == 0.0


def test_score_and_robustness_do_not_move_with_a_new_ai_snapshot(cijfers, filings):
	ander = copy.deepcopy(nagebootste_gemini_respons())
	for regel in ander["regels"]:
		regel["waarden"] = [waarde * 1.4 for waarde in regel["waarden"]]
	a = bouw_dataframe([ai_rij(cijfers, filings)]).iloc[0]
	b = bouw_dataframe([ai_rij(cijfers, filings, ander)]).iloc[0]
	assert a["LBO_IRR_Exact_Pct"] != b["LBO_IRR_Exact_Pct"]  # the analyst case does move
	assert a["Score"] == pytest.approx(b["Score"])
	assert a["Robuustheid_Pct"] == b["Robuustheid_Pct"]


def test_robustness_grid_has_18_runs_and_the_pass_rule(rij):
	runs = rij["Robuustheid_Runs"]
	assert len(runs) == 18
	assert rij["Robuustheid_Pct"] == pytest.approx(sum(r["geslaagd"] for r in runs) / 18 * 100)
	# Check one run by hand: the central one (EBITDA 0, multiple 0, senior = capacity)
	centraal = next(r for r in runs if r["ebitda"] == 0.0 and r["multiple"] == rij["Instap_Multiple"] and r["senior"] == pytest.approx(min(rij["Debt_Capacity_Multiple"], structurering.max_senior_voor_equity(r["multiple"], config.LBO_VENDOR_LOAN_PCT_EV))))
	structuur = Structuur(centraal["multiple"], rij["Instap_Multiple"], centraal["senior"], config.LBO_VENDOR_LOAN_PCT_EV)
	stress = bereken_lbo(rij, "screening_stress", structuur)
	base = bereken_lbo(rij, "screening_base", structuur)
	assert centraal["geslaagd"] == (structurering.haalt_covenants(stress) and base["LBO_IRR_Exact_Pct"] >= config.LBO_MIN_IRR_PCT)


def test_lower_earnings_never_make_a_run_pass_that_failed(rij):
	runs = {(r["ebitda"], r["multiple"], r["senior"]): r["geslaagd"] for r in rij["Robuustheid_Runs"]}
	for (ebitda, multiple, senior), geslaagd in runs.items():
		if ebitda < 0 and geslaagd:
			assert runs[(0.0, multiple, senior)]


def test_without_debt_capacity_robustness_is_zero(cijfers):
	rij = bouw_dataframe([{**cijfers, "Bedrijfswinst_EBIT": -2_000_000.0}]).iloc[0]
	assert rij["Robuustheid_Pct"] == 0.0 and rij["Robuustheid_Runs"] == []
