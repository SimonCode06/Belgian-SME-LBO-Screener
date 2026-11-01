"""De datalaag: van NBB-CSV naar cijfers. Elke regel hier beschermt een keuze uit nbb_csv.py."""
import math
from dataclasses import replace
from datetime import date

import pytest

from src import config, labels
from src.calculations import bouw_dataframe
from src.nbb_csv import (
	Neerlegging,
	bouw_cijfers,
	bouw_driver_pack,
	bouw_meerjaren,
	groepeer_per_bedrijf,
	lees_neerlegging,
)
from tests.conftest import TEKSTVELDEN, neerlegging


def met_codes(jaar, weg=(), **erbij):
	"""Kopie van een neerlegging met codes weggelaten of aangepast. Sleutels: '_' staat voor '/'."""
	codes = {code: bedrag for code, bedrag in jaar.codes.items() if code not in weg}
	codes.update({code.replace("_", "/"): bedrag for code, bedrag in erbij.items()})
	return replace(jaar, codes=codes)


def status(filings):
	df = bouw_dataframe([{**bouw_cijfers(filings), **TEKSTVELDEN}])
	return df.iloc[0]


# --- Ontbrekende codes: 0 of onbekend (NaN) -----------------------------------------------


def test_ontbrekende_code_is_nul_als_het_totaal_zonder_sluit(filings):
	"""61 staat niet in de CSV, maar 60/66A sluit zonder 61: dan is 61 bewezen 0."""
	jaar = met_codes(filings[-1], weg=("61",))
	assert jaar.is_bekend("61")
	assert jaar.waarde("61") == 0.0


def test_ontbrekende_code_zonder_bewijs_is_nan(filings):
	"""Zonder totaal 60/66A kan niets bewijzen dat de personeelskosten 0 zijn."""
	jaar = met_codes(filings[-1], weg=("60/66A", "62"))
	assert not jaar.is_bekend("62")
	assert math.isnan(jaar.waarde("62"))
	assert math.isnan(jaar.waarde("62", "70"))  # één onbekende code maakt de som onbekend


def test_onbekende_kerncode_geeft_onvoldoende_data(filings):
	reeks = filings[:-1] + [met_codes(filings[-1], weg=("60/66A", "62"))]
	cijfers = bouw_cijfers(reeks)
	assert math.isnan(cijfers["Personeelskosten"])
	assert cijfers["Data_Volledigheid"].startswith(labels.DATA_INSUFFICIENT)
	assert "62" in cijfers["Data_Volledigheid"]
	assert cijfers["Check_Data"] == labels.CHECK_OK  # geen rekenfout, gewoon geen gegevens
	assert status(reeks)["LBO_Status"] == labels.STATUS_INSUFFICIENT


def test_volledige_reeks_is_complete(filings):
	cijfers = bouw_cijfers(filings)
	assert cijfers["Data_Volledigheid"] == labels.DATA_COMPLETE
	assert cijfers["Check_Data"] == labels.CHECK_OK


def test_te_weinig_jaren_is_gedeeltelijk(filings):
	cijfers = bouw_cijfers(filings[-2:])
	assert cijfers["Data_Volledigheid"].startswith(labels.DATA_PARTIAL)


def test_een_jaar_geeft_geen_vorig_jaar(filings):
	cijfers = bouw_cijfers(filings[-1:])
	assert math.isnan(cijfers["Omzet_of_Brutomarge_Vorig_Jaar"])
	assert cijfers["Data_Volledigheid"].startswith(labels.DATA_PARTIAL)
	assert labels.SIGNAL_NO_PRIOR_YEAR.format(year="2024") in cijfers["Cijfer_Flags"]
	assert cijfers["Driver_Omzetgroei_Pct"] == pytest.approx(config.LBO_GROEI_STANDAARD * 100)


# --- Schema's ------------------------------------------------------------------------------


def test_volledig_schema_gebruikt_omzet(filings):
	cijfers = bouw_cijfers(filings)
	assert cijfers["Schema_Type"] == "VOL"
	assert cijfers["Omzet_Basis"] == labels.BASIS_REVENUE
	assert cijfers["Omzet_of_Brutomarge"] == 10_000_000.0
	assert cijfers["Inkoop"] == 6_000_000.0
	assert cijfers["Driver_Inkoop_Pct"] == pytest.approx(60.0)


def test_verkort_schema_zonder_omzet_gebruikt_brutomarge(filings_vkt):
	cijfers = bouw_cijfers(filings_vkt)
	assert cijfers["Schema_Type"] == "VKT/MIC"
	assert cijfers["Omzet_Basis"] == labels.BASIS_GROSS_MARGIN
	assert cijfers["Omzet_of_Brutomarge"] == 4_000_000.0  # 10,0 mio omzet - 6,0 mio aankopen
	assert cijfers["Inkoop"] == 0.0
	assert cijfers["Driver_Inkoop_Pct"] == 0.0
	assert cijfers["Check_Data"] == labels.CHECK_OK


def test_verkort_schema_geeft_dezelfde_ebitda(filings, filings_vkt):
	"""Het schema verandert de voorstelling, niet de winst."""
	vol, vkt = status(filings), status(filings_vkt)
	assert vkt["Genormaliseerde_EBITDA"] == pytest.approx(vol["Genormaliseerde_EBITDA"])
	# Only the minimum cash differs: an abridged schema does not show purchases, so their share is 0
	verschil = config.MIN_CASH_PCT_INKOOP * vol["Inkoop"]
	assert vkt["Adjusted_Net_Debt"] == pytest.approx(vol["Adjusted_Net_Debt"] - verschil)


def test_micro_schema_heeft_geen_toelichting(filings_mic):
	"""Micro-schema's publiceren de toelichting niet: een leeg memo-bedrag is onbekend, niet 0."""
	cijfers = bouw_cijfers(filings_mic)
	assert cijfers["Schema_Type"] == "MIC"
	assert math.isnan(cijfers["Memo_Vorderingen_Verbonden"])
	assert math.isnan(cijfers["Memo_Zekerheden_Derden"])


def test_volledig_schema_memo_leeg_is_nul(filings):
	assert bouw_cijfers(filings)["Memo_Vorderingen_Verbonden"] == 0.0


def test_schema_uit_codes_als_model_onbekend(filings):
	assert replace(filings[-1], model="").schema == "VOL"


# --- Controles en signalen -----------------------------------------------------------------


def test_activa_niet_gelijk_aan_passiva_geeft_controleer(filings):
	jaar = filings[-1]
	fout = met_codes(jaar, **{"10_49": jaar.codes["10/49"] + 10.0, "17_49": jaar.codes["17/49"] + 10.0})
	cijfers = bouw_cijfers(filings[:-1] + [fout])
	assert cijfers["Check_Data"].startswith(labels.CHECK_REVIEW)
	assert status(filings[:-1] + [fout])["LBO_Status"] == labels.STATUS_REVIEW_DATA


def test_afrondingsverschil_binnen_tolerantie_is_ok(filings):
	jaar = filings[-1]
	klein = config.CSV_TOLERANTIE_EUR - 1
	afgerond = met_codes(jaar, **{"10_49": jaar.codes["10/49"] + klein, "17_49": jaar.codes["17/49"] + klein})
	assert bouw_cijfers(filings[:-1] + [afgerond])["Check_Data"] == labels.CHECK_OK


def test_verplichte_code_en_valuta(filings):
	jaar = replace(met_codes(filings[-1], weg=("9901",)), valuta="USD")
	check = bouw_cijfers(filings[:-1] + [jaar])["Check_Data"]
	assert "9901" in check and "USD" in check


def test_vereffening_en_correctie_zijn_signalen(filings):
	jaar = replace(filings[-1], vereffening=True, correctie=True)
	cijfers = bouw_cijfers(filings[:-1] + [jaar])
	assert labels.FLAG_LIQUIDATION in cijfers["Cijfer_Flags"]
	assert labels.SIGNAL_CORRECTED.format(year="2024") in cijfers["Cijfer_Flags"]


def test_sociale_schuld_buiten_toelichting_is_signaal(filings):
	jaar = filings[-1]
	afwijkend = met_codes(jaar, **{"9077": jaar.codes["9077"] - 1_000.0})
	cijfers = bouw_cijfers(filings[:-1] + [afwijkend])
	assert "454/9" in cijfers["Cijfer_Flags"]


# --- Boekjaren -----------------------------------------------------------------------------


def test_boekjaar_van_18_maanden_wordt_omgerekend(filings):
	lang = neerlegging(
		2024, 15_000_000.0, 9_000_000.0, 3_300_000.0, begin=date(2023, 7, 1), einde=date(2024, 12, 31)
	)
	cijfers = bouw_cijfers([lang])
	assert cijfers["Boekjaar_Maanden"] == 18
	assert cijfers["Omzet_of_Brutomarge"] == pytest.approx(15_000_000.0 * 12 / 18)
	assert cijfers["Personeelskosten"] == pytest.approx(3_300_000.0 * 12 / 18)
	assert cijfers["Handelsvorderingen"] == pytest.approx(lang.codes["40"])  # balans: niet omgerekend
	assert cijfers["Balanstotaal"] == pytest.approx(lang.codes["20/58"])
	assert labels.SIGNAL_MONTHS.format(year="2024", months=18) in cijfers["Cijfer_Flags"]


def test_hoogste_referentie_wint_bij_dubbele_neerlegging(filings):
	oud = replace(filings[-1], referentie="2024-00001")
	verbeterd = replace(filings[-1], referentie="2024-00002", naam="Testco verbeterd")
	for volgorde in ([oud, verbeterd], [verbeterd, oud]):
		bedrijf = groepeer_per_bedrijf(filings[:-1] + volgorde)[0]
		assert len(bedrijf) == 3
		assert bedrijf[-1].naam == "Testco verbeterd"


def test_groepeert_per_ondernemingsnummer_van_oud_naar_recent(filings):
	ander = [replace(jaar, ondernemingsnummer="0987654321") for jaar in filings]
	bedrijven = groepeer_per_bedrijf(list(reversed(filings)) + ander)
	assert len(bedrijven) == 2
	assert [jaar.boekjaar for jaar in bedrijven[0]] == ["2022", "2023", "2024"]


def test_gat_tussen_boekjaren_telt_alleen_de_aansluitende_reeks(filings):
	los = neerlegging(2019, 8_000_000.0, 4_800_000.0, 1_900_000.0)
	cijfers = bouw_cijfers([los] + filings)
	assert cijfers["Driver_Aantal_Jaren"] == 3
	assert [jaar["Fiscal_Year"] for jaar in bouw_driver_pack([los] + filings)["Fiscal_Years"]] == ["2022", "2023", "2024"]


def test_vorig_jaar_met_gat_telt_niet(filings):
	cijfers = bouw_cijfers([filings[0], filings[-1]])
	assert math.isnan(cijfers["Omzet_of_Brutomarge_Vorig_Jaar"])
	assert cijfers["Driver_Aantal_Jaren"] == 1


def test_maximaal_aantal_jaren(filings):
	reeks = [neerlegging(jaar, 9_000_000.0, 5_400_000.0, 2_000_000.0) for jaar in range(2016, 2025)]
	assert bouw_cijfers(reeks)["Driver_Aantal_Jaren"] == config.LBO_MAX_JAREN


# --- Cash ----------------------------------------------------------------------------------


def test_eigen_aandelen_tellen_niet_als_cash(filings):
	jaar = filings[-1]
	eigen_aandelen = 100_000.0
	met_eigen = met_codes(
		jaar,
		**{
			"50_53": eigen_aandelen,
			"50": eigen_aandelen,
			"29_58": jaar.codes["29/58"] + eigen_aandelen,
			"20_58": jaar.codes["20/58"] + eigen_aandelen,
			"10_49": jaar.codes["10/49"] + eigen_aandelen,
			"10_15": jaar.codes["10/15"] + eigen_aandelen,
		},
	)
	cijfers = bouw_cijfers(filings[:-1] + [met_eigen])
	assert cijfers["Check_Data"] == labels.CHECK_OK
	assert cijfers["Eigen_Aandelen"] == eigen_aandelen
	assert cijfers["Liquide_Middelen"] == pytest.approx(jaar.codes["54/58"])


# --- Inlezen van de CSV --------------------------------------------------------------------


def schrijf_csv(pad, velden):
	pad.write_text("\n".join(f'"{sleutel}","{waarde}"' for sleutel, waarde in velden.items()), encoding="utf-8-sig")
	return pad


KOP = {
	"Entity number": "0123456789",
	"Entity name": "Testco",
	"Accounting period start date": "2024-01-01",
	"Accounting period end date": "2024-12-31",
	"Reference number": "2025-00012",
	"Currency": "EUR",
	"Model code": "m02-f",
}


def test_leest_een_nbb_csv(tmp_path):
	pad = schrijf_csv(tmp_path / "Testco_JR2024.csv", {**KOP, "Liquidation flag": "TRUE", "70": "1000.5", "9901": "-20"})
	jaar = lees_neerlegging(pad)
	assert isinstance(jaar, Neerlegging)
	assert jaar.naam == "Testco" and jaar.boekjaar == "2024" and jaar.maanden == 12
	assert jaar.codes == {"70": 1000.5, "9901": -20.0}
	assert jaar.vereffening and not jaar.correctie
	assert jaar.schema == "VOL"


def test_bedrijf_en_jaar_komen_uit_de_inhoud_niet_uit_de_bestandsnaam(tmp_path):
	jaar = lees_neerlegging(schrijf_csv(tmp_path / "Iets_Anders_JR1999.csv", KOP))
	assert jaar.naam == "Testco" and jaar.boekjaar == "2024"


def test_ongeldig_bedrag_geeft_valueerror(tmp_path):
	pad = schrijf_csv(tmp_path / "fout.csv", {**KOP, "70": "duizend"})
	with pytest.raises(ValueError, match="70"):
		lees_neerlegging(pad)


def test_ontbrekend_kopveld_geeft_valueerror(tmp_path):
	kop = {sleutel: waarde for sleutel, waarde in KOP.items() if sleutel != "Currency"}
	with pytest.raises(ValueError, match="Currency"):
		lees_neerlegging(schrijf_csv(tmp_path / "fout.csv", kop))


def test_drie_kolommen_geeft_valueerror(tmp_path):
	pad = tmp_path / "fout.csv"
	pad.write_text('"Entity number","0123456789","extra"\n', encoding="utf-8")
	with pytest.raises(ValueError, match="twee kolommen"):
		lees_neerlegging(pad)


# --- Meerjarentab --------------------------------------------------------------------------


def test_meerjaren_een_rij_per_boekjaar(filings):
	rijen = bouw_meerjaren(filings)
	assert [rij["Boekjaar"] for rij in rijen] == ["2022", "2023", "2024"]
	laatste = rijen[-1]
	assert laatste["Omzet"] == 10_000_000.0
	assert laatste["Net_Debt"] == pytest.approx(-filings[-1].codes["54/58"])
	assert math.isnan(rijen[0]["Model"]["Omzetgroei_Pct"])
	assert rijen[-1]["Model"]["Omzetgroei_Pct"] == pytest.approx((10_000_000 / 9_500_000 - 1) * 100)


def test_meerjaren_verkort_schema(filings_vkt):
	rijen = bouw_meerjaren(filings_vkt)
	assert rijen[-1]["Omzet"] == 4_000_000.0
	assert rijen[-1]["Model"]["Inkoop"] == 0.0
