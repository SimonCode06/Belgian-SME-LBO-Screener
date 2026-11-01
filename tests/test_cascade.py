"""Phase 5.5: the new cascade in bepaal_status, one test per step."""
import pandas as pd
import pytest

from src import config, labels
from src.calculations import bepaal_status, bouw_dataframe


def componenten(score):
	return [
		{"sleutel": s, "label": labels.SCORE_LABELS[s], "gewicht": g, "score": score, "reden": "x"}
		for s, g in config.SCORE_GEWICHTEN.items()
	]


def rij(**wijzig):
	"""A row that passes every gate, with a strong score: change one field per test."""
	basis = {
		"Check_Data": labels.CHECK_OK,
		"LBO_Balanscheck": labels.CHECK_OK,
		"Data_Volledigheid": labels.DATA_COMPLETE,
		"Driver_Aantal_Jaren": 3,
		"Genormaliseerde_EBITDA": 1_500_000.0,
		"Debt_Capacity_Status": labels.CAPACITY_OK,
		"Debt_Capacity_Multiple": 2.5,
		"ATP_Max_Equity_Price": 8_000_000.0,
		"Score": 80.0,
		"Robuustheid_Pct": 70.0,
		"Aantal_Hoge_Vlaggen": 0,
		"Dealtype": labels.DEAL_PRIMARY,
		"Score_Componenten": componenten(80.0),
	}
	basis.update(wijzig)
	return pd.Series(basis)


def test_strong():
	assert bepaal_status(rij()) == labels.STATUS_STRONG


def test_1_data_does_not_reconcile():
	assert bepaal_status(rij(Check_Data=labels.check_review(["x"]))) == labels.STATUS_REVIEW_DATA


def test_2_model_does_not_reconcile():
	assert bepaal_status(rij(LBO_Balanscheck=labels.CHECK_ERROR)) == labels.STATUS_REVIEW_MODEL


@pytest.mark.parametrize("wijzig", [{"Data_Volledigheid": labels.data_insufficient("62")}, {"Driver_Aantal_Jaren": 2}])
def test_3_insufficient_data_and_too_few_years(wijzig):
	assert bepaal_status(rij(**wijzig)) == labels.STATUS_INSUFFICIENT


def test_4_no_ebitda_and_too_small():
	assert bepaal_status(rij(Genormaliseerde_EBITDA=-1.0)) == labels.STATUS_NO_GO_EBITDA
	assert bepaal_status(rij(Genormaliseerde_EBITDA=float("nan"))) == labels.STATUS_NO_GO_EBITDA
	assert bepaal_status(rij(Genormaliseerde_EBITDA=config.LBO_MIN_EBITDA - 1)) == labels.STATUS_NO_GO_SIZE


def test_5_no_debt_capacity():
	assert bepaal_status(rij(Debt_Capacity_Multiple=config.LBO_MIN_DEBT_CAPACITY - 0.01)) == labels.STATUS_NO_GO_CAPACITY
	assert bepaal_status(rij(Debt_Capacity_Status=labels.CAPACITY_NONE, Debt_Capacity_Multiple=0.0)) == labels.STATUS_NO_GO_CAPACITY


def test_6_no_equity_for_the_seller():
	assert bepaal_status(rij(ATP_Max_Equity_Price=-1.0)) == labels.STATUS_NO_GO_EQUITY
	assert bepaal_status(rij(ATP_Max_Equity_Price=float("nan"))) == labels.STATUS_NO_GO_EQUITY


@pytest.mark.parametrize(
	"wijzig, reden",
	[
		({"Dealtype": labels.DEAL_CARVE_OUT}, "Carve-out deal"),
		({"Dealtype": labels.DEAL_SECONDARY}, "Secondary deal"),
		({"Aantal_Hoge_Vlaggen": 1}, "1 high red flag"),
		({"Robuustheid_Pct": 50.0}, "robustness 50%"),
	],
)
def test_7_strong_score_but_a_blocker_gives_possible_with_the_reason(wijzig, reden):
	status = bepaal_status(rij(**wijzig))
	assert status.startswith(labels.STATUS_POSSIBLE) and reden in status


def test_8_possible_names_the_two_weakest_components():
	lijst = componenten(60.0)
	lijst[0]["score"], lijst[3]["score"] = 10.0, 20.0
	status = bepaal_status(rij(Score=60.0, Score_Componenten=lijst))
	assert status.startswith(labels.STATUS_POSSIBLE)
	assert "Debt Capacity 10" in status and "Trend 20" in status


def test_9_weak_below_the_possible_threshold():
	status = bepaal_status(rij(Score=config.SCORE_MOGELIJK - 1, Score_Componenten=componenten(30.0)))
	assert status.startswith(labels.STATUS_WEAK)


def test_the_analyst_case_is_shown_but_never_decides(cijfers):
	rij_df = bouw_dataframe([cijfers]).iloc[0]
	assert rij_df["Analyst_Case"].startswith("Analyst case (")
	assert "IRR" in rij_df["Analyst_Case"]
