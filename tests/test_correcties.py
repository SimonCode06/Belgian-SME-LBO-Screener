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
