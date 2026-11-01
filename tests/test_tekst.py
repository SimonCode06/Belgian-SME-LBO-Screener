"""Phase 2: the structured text pass, the quote check, the Economics block and the new soft flags."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import main as app
from src import assumpties, citaten, config, labels
from src.nbb_csv import bouw_driver_pack, groepeer_per_bedrijf, lees_neerlegging
from src.tekst_schema import OordeelAntwoord, TekstAntwoord, verwerk_normalisatie, verwerk_tekst

BASELINE_LOKAAL = Path(__file__).resolve().parent / "baseline_local"
ECHT = (BASELINE_LOKAAL / "Cloudar.pdf").exists()


def maak_pdf(pad, paginas):
	"""A minimal, valid PDF with one line of text per page (no extra package needed). None = page without text."""
	objecten = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
	kinderen = []
	for tekst in paginas:
		inhoud = f"BT /F1 9 Tf 20 700 Td ({tekst}) Tj ET".encode("latin-1") if tekst else b""
		objecten.append(f"<< /Length {len(inhoud)} >>\nstream\n{inhoud.decode('latin-1')}\nendstream")
		inhoud_nr = len(objecten)
		objecten.append(
			f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {inhoud_nr} 0 R "
			"/Resources << /Font << /F1 3 0 R >> >> >>"
		)
		kinderen.append(f"{len(objecten)} 0 R")
	objecten[1] = f"<< /Type /Pages /Kids [{' '.join(kinderen)}] /Count {len(kinderen)} >>"
	uit, posities = b"%PDF-1.4\n", []
	for nummer, obj in enumerate(objecten, start=1):
		posities.append(len(uit))
		uit += f"{nummer} 0 obj\n{obj}\nendobj\n".encode("latin-1")
	xref = len(uit)
	uit += f"xref\n0 {len(objecten) + 1}\n0000000000 65535 f \n".encode()
	uit += "".join(f"{positie:010d} 00000 n \n" for positie in posities).encode()
	uit += f"trailer\n<< /Size {len(objecten) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
	pad.write_bytes(uit)
	return pad


VULTEKST = "Dit is gewone toelichting bij de jaarrekening zonder bijzonderheden voor de lezer. " * 2
PAGINAS = [
	VULTEKST,
	VULTEKST + "Aan bestuurders en zaakvoerders 9503 552.680 bezoldiging ten laste van de resultatenrekening",
	VULTEKST + "De Cronos Groep NV Consoliderende moederonderneming - Grootste geheel 0467132994",
	VULTEKST,
]


@pytest.fixture
def pdf_paginas(tmp_path):
	return citaten.pdf_paginas(maak_pdf(tmp_path / "test.pdf", PAGINAS))


def antwoord(**wijzig):
	data = {
		"ondernemingsnummer": "0123.456.789",
		"boekjaar": "2024",
		"commissaris_oordeel": labels.OPINION_UNQUALIFIED,
		"normalisaties": [
			{
				"categorie": "bestuurdersvergoeding",
				"omschrijving": "Director remuneration.",
				"bedrag_eur": 500_000.0,  # Gemini names another amount than the CSV
				"nbb_code": "9503",
				"richting": "+",
				"pagina": 2,
				"citaat": "Aan bestuurders en zaakvoerders 9503 552.680",
				"confidence": "medium",
			},
			{
				"categorie": "huur_verbonden_partij",
				"omschrijving": "Rent paid to the owner's property company.",
				"bedrag_eur": 120_000.0,
				"nbb_code": None,
				"richting": "+",
				"pagina": 3,
				"citaat": "Huur betaald aan Vastgoed BV van de zaakvoerder",
				"confidence": "high",
			},
		],
		"red_flags": [
			{
				"categorie": "verbonden_partijen",
				"ernst": "hoog",
				"omschrijving": "Large group receivables.",
				"pagina": 3,
				"citaat": "Consoliderende moederonderneming - Grootste geheel",
			}
		],
		"eigendom": {
			"type": "groepsdochter",
			"moederonderneming": "De Cronos Groep NV",
			"ondernemingsnummer_moeder": "0467.132.994",
			"consoliderend": "ja",
			"pagina": 3,
			"citaat": "De Cronos Groep NV Consoliderende moederonderneming",
		},
		"buitenbalans": [{"omschrijving": "Operating leases", "bedrag_eur": 80_000.0, "pagina": 4}],
		"Gebruikt_Model": config.MODELLEN[0],
	}
	data.update(wijzig)
	return data


# --- 2.1 Schema -----------------------------------------------------------------------------


def test_schema_accepts_a_full_answer():
	TekstAntwoord.model_validate(antwoord())


@pytest.mark.parametrize(
	"veld, waarde",
	[("categorie", "marketing"), ("ernst", "kritiek")],
)
def test_schema_refuses_an_unknown_category_or_severity(veld, waarde):
	data = antwoord()
	data["red_flags"][0][veld] = waarde
	with pytest.raises(ValidationError):
		TekstAntwoord.model_validate(data)


def test_schema_refuses_an_unknown_ownership_type():
	data = antwoord()
	data["eigendom"]["type"] = "familie"
	with pytest.raises(ValidationError):
		TekstAntwoord.model_validate(data)


def test_amount_with_an_nbb_code_comes_from_the_csv():
	regel = verwerk_normalisatie(antwoord()["normalisaties"][0], {"9503": 552_680.0}, None)
	assert regel["bedrag_gebruikt"] == 552_680.0 and regel["bedrag_eur"] == 500_000.0
	assert regel["bedrag_bron"] == labels.AMOUNT_FROM_CSV.format(code="9503") and regel["bedrag_geverifieerd"]


def test_amount_without_a_csv_code_is_labelled_unverified():
	regel = verwerk_normalisatie(antwoord()["normalisaties"][1], {"9503": 552_680.0}, None)
	assert regel["bedrag_gebruikt"] == 120_000.0
	assert regel["bedrag_bron"] == labels.AMOUNT_AI_UNVERIFIED and not regel["bedrag_geverifieerd"]


@pytest.mark.skipif(not ECHT, reason="tests/baseline_local ontbreekt")
def test_cloudar_9503_comes_from_the_csv_whatever_gemini_says():
	bedrijf = groepeer_per_bedrijf([lees_neerlegging(p) for p in sorted(BASELINE_LOKAAL.glob("Cloudar_JR*.csv"))])[0]
	regel = verwerk_normalisatie(antwoord()["normalisaties"][0], bedrijf[-1].codes, None)
	assert regel["bedrag_gebruikt"] == 552_680.0


def test_verwerk_tekst_builds_readable_columns_and_lists(pdf_paginas):
	velden = verwerk_tekst(antwoord(), {"9503": 552_680.0}, pdf_paginas)
	assert "EUR 552,680 (CSV code 9503)" in velden["Normalisatie_Voorstellen"]
	assert "AI, to be verified" in velden["Normalisatie_Voorstellen"]
	assert velden["Red_Flags"].startswith("[HIGH] Related parties")
	assert velden["Eigendom"].startswith("Group subsidiary of De Cronos Groep NV (0467.132.994), consolidated: yes")
	assert len(velden["AI_Normalisaties"]) == 2 and velden["AI_Eigendom"]["citaat_status"] == citaten.GEVERIFIEERD


def test_koppel_tekst_checks_the_company(cijfers):
	verkeerd = app.koppel_tekst(cijfers, antwoord(ondernemingsnummer="0999.999.999"), {}, None)
	assert verkeerd["Commissaris_Oordeel"] == labels.OPINION_UNKNOWN and verkeerd["AI_Normalisaties"] == []
	ander_jaar = app.koppel_tekst(cijfers, antwoord(boekjaar="2023"), {}, None)
	assert ander_jaar["Red_Flags"].startswith(labels.TEXT_WRONG_YEAR.format(pdf="2023", figures="2024"))


def test_an_old_cache_format_counts_as_no_cache(tmp_path):
	oud = tmp_path / "tekst.json"
	oud.write_text(json.dumps({"Ondernemingsnummer": "0123.456.789", "Red_Flags": "x"}), encoding="utf-8")
	assert app.lees_cache(oud) is None
	nieuw = tmp_path / "nieuw.json"
	nieuw.write_text(json.dumps(antwoord()), encoding="utf-8")
	assert app.lees_cache(nieuw)["ondernemingsnummer"] == "0123.456.789"


# --- 2.2 Quote check ----------------------------------------------------------------------


def test_a_real_quote_is_found_and_an_invented_one_is_not(pdf_paginas):
	assert citaten.controleer_citaat("Grootste geheel 0467132994", 3, pdf_paginas)[0] == citaten.GEVERIFIEERD
	status, score = citaten.controleer_citaat("De vennootschap verloor haar grootste klant in 2024", 3, pdf_paginas)
	assert status == citaten.NIET_GEVONDEN and score < config.CITAAT_MIN_SCORE


def test_quote_matching_ignores_case_white_space_and_accents(pdf_paginas):
	assert citaten.controleer_citaat("AAN  bestuurders en\nzaakvoerders 9503 552.680", 2, pdf_paginas)[0] == citaten.GEVERIFIEERD


def test_quote_on_a_neighbouring_or_other_page(pdf_paginas):
	assert citaten.controleer_citaat("Grootste geheel 0467132994", 4, pdf_paginas)[0] == citaten.GEVERIFIEERD
	assert citaten.controleer_citaat("Grootste geheel 0467132994", 1, pdf_paginas)[0] == citaten.ANDERE_PAGINA
	assert citaten.controleer_citaat("Grootste geheel 0467132994", None, pdf_paginas)[0] == citaten.GEVERIFIEERD


def test_shortened_quote_with_an_ellipsis(pdf_paginas):
	citaat = "Aan bestuurders en zaakvoerders ... ten laste van de resultatenrekening"
	assert citaten.controleer_citaat(citaat, 2, pdf_paginas)[0] == citaten.GEVERIFIEERD


def test_historical_trend_is_no_quote(pdf_paginas):
	assert citaten.controleer_citaat(config.ASSUMPTIE_BRON_HISTORIEK, None, pdf_paginas)[0] == citaten.GEEN_CITAAT


def test_scanned_pdf_is_not_checkable_and_does_not_crash(tmp_path):
	paginas = citaten.pdf_paginas(maak_pdf(tmp_path / "scan.pdf", [None, None]))
	assert paginas is None
	assert citaten.controleer_citaat("Een citaat van voldoende lengte", 1, paginas)[0] == citaten.NIET_CONTROLEERBAAR
	kapot = tmp_path / "kapot.pdf"
	kapot.write_bytes(b"not a pdf")
	assert citaten.pdf_paginas(kapot) is None


def test_source_parsing():
	assert citaten.splits_bron('p. 12: "new contract signed"') == (12, "new contract signed")
	assert citaten.splits_bron("page 3 - Huur betaald") == (3, "Huur betaald")
	assert citaten.splits_bron("historical trend") == (None, "historical trend")


def test_assumption_with_a_quote_that_is_not_found_gets_low_confidence(pdf_paginas):
	from tests.test_assumpties import nagebootste_gemini_respons

	pack = assumpties.pack_uit_antwoord(assumpties.AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))
	pack["base"]["dso"]["source"] = 'p. 3: "Grootste geheel 0467132994"'
	niet = citaten.controleer_assumpties(pack, pdf_paginas, assumpties.SCENARIOS)
	assert pack["base"]["dso"]["citaat_status"] == citaten.GEVERIFIEERD
	assert ("base", "dpo") in niet  # 'p. 12: "new contract signed"' is not in this PDF
	assert pack["base"]["dpo"]["confidence"] == "low"
	assert labels.QUOTE_NOT_FOUND in pack["base"]["dpo"]["vlaggen"]


@pytest.mark.skipif(not ECHT, reason="tests/baseline_local ontbreekt")
def test_real_cloudar_pdf():
	paginas = citaten.pdf_paginas(BASELINE_LOKAAL / "Cloudar.pdf")
	assert len(paginas) == 57
	echt = "De Cronos Groep NV Consoliderende moederonderneming - Grootste geheel 0467132994"
	assert citaten.controleer_citaat(echt, 36, paginas)[0] == citaten.GEVERIFIEERD
	verzonnen = "De vennootschap heeft haar belangrijkste klant verloren in het voorbije boekjaar"
	assert citaten.controleer_citaat(verzonnen, 36, paginas)[0] == citaten.NIET_GEVONDEN


# --- 2.3 Economics ------------------------------------------------------------------------


def test_driver_pack_has_the_economics_block(filings):
	economics = bouw_driver_pack(filings)["Economics"]
	# Testco 2024: revenue 10.0m, purchases 6.0m, EBITDA 1.6m
	assert economics["Gross_Margin_Pct"] == 40.0
	assert economics["EBITDA_Margin_Pct"] == 16.0
	assert economics["COGS_Pct_Revenue"] == 60.0
	assert economics["EBITDA_Sensitivity_Per_1pp_Cost_Pct"] == pytest.approx(100_000 / 1_600_000 * 100)


def test_economics_is_in_the_prompt(filings):
	from src.ai_extraction import bouw_assumptie_prompt

	prompt = bouw_assumptie_prompt(bouw_driver_pack(filings))
	assert "EBITDA_Sensitivity_Per_1pp_Cost_Pct" in prompt and "business_model" in prompt


def test_business_model_is_optional_for_old_snapshots():
	from tests.test_assumpties import nagebootste_gemini_respons

	assert assumpties.AssumptieAntwoord.model_validate(nagebootste_gemini_respons()).business_model == ""


# --- 2.4 Soft flags on the AI case ----------------------------------------------------------


def ai_pack():
	from tests.test_assumpties import nagebootste_gemini_respons

	return assumpties.pack_uit_antwoord(assumpties.AssumptieAntwoord.model_validate(nagebootste_gemini_respons()))


def test_a_downside_that_wipes_out_ebitda_is_flagged(cijfers, filings):
	pack = ai_pack()
	pack["downside"]["overige_kosten_pct"]["waarden"] = [25.0] * 5  # margin from 16% to about 4%
	regels = assumpties.controleer(
		pack, bouw_driver_pack(filings)["Fiscal_Years"], cijfers["Omzet_of_Brutomarge"], cijfers["Personeelskosten"],
		ebitda_0=1_600_000.0, hist_ebitda_cagr=cijfers["Driver_EBITDA_CAGR_Pct"],
	)
	assert any("not a credible setback" in regel for regel in regels)


def test_a_hockey_stick_base_is_flagged(cijfers, filings):
	pack = ai_pack()
	pack["base"]["volumegroei"]["waarden"] = [15.0] * 5
	regels = assumpties.controleer(
		pack, bouw_driver_pack(filings)["Fiscal_Years"], cijfers["Omzet_of_Brutomarge"], cijfers["Personeelskosten"],
		ebitda_0=1_600_000.0, hist_ebitda_cagr=-5.0,
	)
	assert any("above the trend" in regel for regel in regels)


def test_a_plausible_ai_case_gets_no_ebitda_flags(cijfers, filings):
	regels = assumpties.controleer(
		ai_pack(), bouw_driver_pack(filings)["Fiscal_Years"], cijfers["Omzet_of_Brutomarge"], cijfers["Personeelskosten"],
		ebitda_0=1_600_000.0, hist_ebitda_cagr=cijfers["Driver_EBITDA_CAGR_Pct"],
	)
	assert not any("credible setback" in regel or "above the trend" in regel for regel in regels)


@pytest.mark.skipif(not ECHT, reason="tests/baseline_local ontbreekt")
def test_cached_cloudar_set_gets_both_flags():
	from src.calculations import bouw_dataframe
	from tests.test_regressie import _cloudar_rij

	vlaggen = bouw_dataframe([_cloudar_rij()]).iloc[0]["LBO_Assumptie_Vlaggen"]
	assert any("EUR 29,988" in vlag and "EUR 1,768,845" in vlag for vlag in vlaggen)
	assert any("+10.5%" in vlag and "-8.6%" in vlag for vlag in vlaggen)


# --- 2.5 Second pass ----------------------------------------------------------------------


def oordeel(**wijzig):
	data = {
		"kwalitatief_lbo_oordeel": "Stable cash flow, but the stress case breaches the DSCR.",
		"investment_thesis": ["Recurring revenue.", "Low capex.", "Thin margin."],
		"dd_vragen": [{"vraag": f"Question {i}?", "gekoppeld_aan": "Red flag"} for i in range(5)],
	}
	data.update(wijzig)
	return data


def test_second_pass_needs_three_bullets_and_five_questions():
	OordeelAntwoord.model_validate(oordeel())
	with pytest.raises(ValidationError):
		OordeelAntwoord.model_validate(oordeel(investment_thesis=["Only one."]))
	with pytest.raises(ValidationError):
		OordeelAntwoord.model_validate(oordeel(dd_vragen=oordeel()["dd_vragen"][:4]))


def test_second_pass_fills_thesis_and_questions(cijfers, tmp_path, monkeypatch):
	from src.calculations import bouw_dataframe

	monkeypatch.setattr(config, "CACHE_FOLDER", tmp_path)
	df = bouw_dataframe([{**cijfers, "Kwalitatief_LBO_Oordeel": ""}])

	class Client:
		models = None

		def __init__(self):
			self.models = self

		def generate_content(self, model, contents, config):
			class Antwoord:
				text = json.dumps(oordeel())

			return Antwoord

	app.voeg_oordelen_toe(df, Client(), [])
	rij = df.iloc[0]
	assert rij["Kwalitatief_LBO_Oordeel"].startswith("Stable cash flow")
	assert len(rij["AI_Investment_Thesis"]) == 3 and len(rij["AI_DD_Vragen"]) == 5
	# From the cache the second time, also without a client
	df2 = bouw_dataframe([{**cijfers, "Kwalitatief_LBO_Oordeel": ""}])
	app.voeg_oordelen_toe(df2, None, [])
	assert len(df2.iloc[0]["AI_DD_Vragen"]) == 5
