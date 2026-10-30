"""Shared test data: a realistic row built from a synthetic filing, so the tests need no private CSV."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import labels  # noqa: E402
from src.nbb_csv import Neerlegging, bouw_cijfers  # noqa: E402

TEKSTVELDEN = {
	"Normalisatie_Voorstellen": "None",
	"Commissaris_Oordeel": labels.OPINION_UNQUALIFIED,
	"Buitenbalans_Verplichtingen": "None",
	"Red_Flags": "",
	"Kwalitatief_LBO_Oordeel": "",
	"Gebruikt_Model": "-",
}


def neerlegging(jaar, omzet, aankopen, personeel, overige=200_000.0, afschrijving=100_000.0, cash=900_000.0):
	"""A consistent full-schema filing: every total reconciles."""
	from datetime import date

	ebit = omzet - aankopen - personeel - overige - afschrijving
	vaste_activa = 500_000.0
	vorderingen = omzet * 0.15
	voorraad = aankopen * 0.05
	handelsschulden = aankopen * 0.12
	sociaal = personeel * 0.1
	totaal_activa = vaste_activa + voorraad + vorderingen + cash
	eigen_vermogen = totaal_activa - handelsschulden - sociaal
	codes = {
		"20/58": totaal_activa, "22/27": vaste_activa, "21/28": vaste_activa, "29/58": voorraad + vorderingen + cash,
		"3": voorraad, "40": vorderingen, "40/41": vorderingen, "54/58": cash,
		"10/49": totaal_activa, "10/15": eigen_vermogen, "14": eigen_vermogen - 100_000.0, "17/49": handelsschulden + sociaal,
		"42/48": handelsschulden + sociaal, "44": handelsschulden, "45": sociaal, "454/9": sociaal, "9077": sociaal,
		"450": 0.0, "9072": 0.0, "9073": 0.0, "9076": 0.0,
		"70": omzet, "70/76A": omzet, "60": aankopen, "61": 0.0, "62": personeel, "630": afschrijving,
		"640/8": overige, "60/66A": aankopen + personeel + afschrijving + overige, "9901": ebit,
		"66A": 0.0, "76A": 0.0, "635/8": 0.0, "631/4": 0.0, "9903": ebit, "9904": ebit * 0.75, "9087": 40.0,
		"8169": 90_000.0,
	}
	return Neerlegging(
		bestand=f"Test_JR{jaar}.csv",
		ondernemingsnummer="0123456789",
		naam="Testco",
		begin=date(jaar, 1, 1),
		einde=date(jaar, 12, 31),
		referentie=str(jaar),
		valuta="EUR",
		vereffening=False,
		correctie=False,
		codes=codes,
		model="m02-f",
	)


@pytest.fixture
def filings():
	return [
		neerlegging(2022, 9_000_000.0, 5_400_000.0, 2_000_000.0),
		neerlegging(2023, 9_500_000.0, 5_700_000.0, 2_100_000.0),
		neerlegging(2024, 10_000_000.0, 6_000_000.0, 2_200_000.0),
	]


@pytest.fixture
def cijfers(filings):
	return {**bouw_cijfers(filings), **TEKSTVELDEN}
