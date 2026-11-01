"""Regressietest: de volledige berekening (CSV -> cijfers -> LBO-model -> oordeel) zonder Gemini.

Waarom: elke latere wijziging moet zichtbaar maken welke cijfers ze verandert. Deze test
vergelijkt de kerncijfers met een opgeslagen 'baseline' (JSON). Wijkt één cijfer af, dan faalt
de test en toont hij welk cijfer van wat naar wat ging.

Twee soorten baselines:
- tests/baseline/        : synthetisch testbedrijf (Testco), staat in git en draait ook in CI.
- tests/baseline_local/  : echte data (Cloudar), staat NIET in git. Ontbreekt de map, dan
                           wordt die test overgeslagen. De map bevat de CSV's en een vaste kopie
                           van de AI-assumpties en de AI-tekst, zodat er nooit een API-call nodig is.

Verandert een stap BEWUST een cijfer, werk de baseline dan bij in dezelfde commit:
    set UPDATE_BASELINE=1 && pytest tests/test_regressie.py      (Windows cmd)
    UPDATE_BASELINE=1 pytest tests/test_regressie.py             (Mac/Linux)
en zet in de commitboodschap wat er veranderde en waarom.
"""
import json
import math
import os
from pathlib import Path

import pytest

import main as app
from src.assumpties import AssumptieAntwoord, pack_uit_antwoord
from src.calculations import bouw_dataframe
from src import labels
from src.nbb_csv import bouw_cijfers, bouw_driver_pack, groepeer_per_bedrijf, lees_neerlegging
from tests.conftest import TEKSTVELDEN
from tests.test_assumpties import nagebootste_gemini_respons

MAP = Path(__file__).resolve().parent
BASELINE = MAP / "baseline"
BASELINE_LOKAAL = MAP / "baseline_local"
BIJWERKEN = os.environ.get("UPDATE_BASELINE") == "1"

TOLERANTIE_REL = 1e-9
TOLERANTIE_ABS = 0.01  # euro / procentpunt: afrondingsruis, geen echte wijziging

# Velden uit de DataFrame-rij die het oordeel dragen
RIJVELDEN = (
	"LBO_Status",
	"Data_Volledigheid",
	"Check_Data",
	"Genormaliseerde_EBITDA",
	"Adjusted_Net_Debt",
	"Net_Debt",
	"Minimum_Operationele_Cash",
	"Instap_Multiple",
	"Senior_Multiple",
	"Indicatieve_EV",
	"Indicatieve_Equity_Value",
	"LBO_Instap_EV",
	"LBO_Senior_Schuld",
	"LBO_Sponsor_Equity_Instap",
	"LBO_EBITDA_Jaar5",
	"LBO_Eind_Net_Debt_to_EBITDA",
	"LBO_Laagste_Cash",
	"LBO_RCF_Piek",
	"LBO_Balanscheck",
)
# Velden per scenario (base, downside, upside)
SCENARIOVELDEN = (
	"Indicatieve_IRR_Pct",
	"Indicatieve_MoIC",
	"LBO_Laagste_DSCR",
	"LBO_Laagste_Rentedekking",
	"LBO_Hoogste_Leverage",
	"LBO_Convenanten",
)


def _schoon(waarde):
	"""JSON kent geen NaN: een lege waarde wordt null. Numpy-getallen worden gewone getallen."""
	if hasattr(waarde, "item"):
		waarde = waarde.item()
	if isinstance(waarde, float) and math.isnan(waarde):
		return None
	return waarde


def kerncijfers(rij):
	flags = [flag for flag in str(rij["Red_Flags"] or "").split("; ") if flag.strip()]
	return {
		**{veld: _schoon(rij[veld]) for veld in RIJVELDEN},
		"Scenarios": {
			naam: {veld: _schoon(model[veld]) for veld in SCENARIOVELDEN}
			for naam, model in rij["LBO_Scenarios"].items()
		},
		"Aantal_Red_Flags": len(flags),
	}


def _verschillen(verwacht, gekregen, pad=""):
	"""Lijst van leesbare verschillen, bv. 'Scenarios.base.Indicatieve_IRR_Pct: 18.2 -> 17.9'."""
	if isinstance(verwacht, dict) and isinstance(gekregen, dict):
		fouten = []
		for sleutel in sorted(set(verwacht) | set(gekregen)):
			fouten += _verschillen(verwacht.get(sleutel), gekregen.get(sleutel), f"{pad}.{sleutel}".lstrip("."))
		return fouten
	getallen = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (verwacht, gekregen))
	if getallen and math.isclose(verwacht, gekregen, rel_tol=TOLERANTIE_REL, abs_tol=TOLERANTIE_ABS):
		return []
	return [] if verwacht == gekregen else [f"{pad}: {verwacht!r} -> {gekregen!r}"]


def vergelijk_met_baseline(pad, gekregen):
	if BIJWERKEN or not pad.exists():
		pad.parent.mkdir(parents=True, exist_ok=True)
		pad.write_text(json.dumps(gekregen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
		if not BIJWERKEN:
			pytest.fail(f"Baseline {pad.name} bestond niet en is nu aangemaakt: controleer ze en draai opnieuw.")
		return
	verwacht = json.loads(pad.read_text(encoding="utf-8"))
	fouten = _verschillen(verwacht, gekregen)
	assert not fouten, "Afwijking van de baseline:\n  " + "\n  ".join(fouten)


def test_testco_mechanische_drivers(filings, cijfers):
	"""Zonder AI: de assumpties komen uit de mechanische drivers."""
	df = bouw_dataframe([{**cijfers, "LBO_Assumptie_Bron": labels.ASSUMPTIONS_FALLBACK_NO_AI}])
	vergelijk_met_baseline(BASELINE / "testco_mechanisch.json", kerncijfers(df.iloc[0]))


def test_testco_ai_assumpties(filings, cijfers):
	"""Met een vaste, nagebootste Gemini-respons: zo blijft ook het AI-pad bewaakt."""
	pack = pack_uit_antwoord(AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))
	rij = {
		**cijfers,
		"LBO_Assumpties": pack,
		"LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI,
		"LBO_Driver_Pack": bouw_driver_pack(filings),
	}
	df = bouw_dataframe([rij])
	vergelijk_met_baseline(BASELINE / "testco.json", kerncijfers(df.iloc[0]))


def _cloudar_rij():
	csvs = sorted(BASELINE_LOKAAL.glob("Cloudar_JR*.csv"))
	bedrijf = groepeer_per_bedrijf([lees_neerlegging(pad) for pad in csvs])[0]
	cijfers = bouw_cijfers(bedrijf)

	tekst = json.loads((BASELINE_LOKAAL / "cloudar_tekst.json").read_text(encoding="utf-8"))
	velden = app.koppel_tekst(cijfers, tekst)

	data = json.loads((BASELINE_LOKAAL / "cloudar_assumpties.json").read_text(encoding="utf-8"))
	antwoord = AssumptieAntwoord.model_validate({k: v for k, v in data.items() if k != "Gebruikt_Model"})
	return {
		**cijfers,
		**velden,
		"LBO_Assumpties": pack_uit_antwoord(antwoord),
		"LBO_Assumptie_Bron": labels.ASSUMPTIONS_AI,
		"LBO_Driver_Pack": bouw_driver_pack(bedrijf),
	}


@pytest.mark.skipif(
	not (BASELINE_LOKAAL / "cloudar_assumpties.json").exists(),
	reason="tests/baseline_local ontbreekt (echte data staat niet in git)",
)
def test_cloudar_echte_data():
	df = bouw_dataframe([_cloudar_rij()])
	vergelijk_met_baseline(BASELINE_LOKAAL / "cloudar.json", kerncijfers(df.iloc[0]))
