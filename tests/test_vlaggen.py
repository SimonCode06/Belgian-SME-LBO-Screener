"""Phase 5.1: structured red flags."""
from src import config, labels, vlaggen
from src.calculations import bouw_dataframe


def ai_flag(categorie="verbonden_partijen", ernst="hoog", tekst="Large receivables from affiliated companies.", status="verified"):
	return {"categorie": categorie, "ernst": ernst, "omschrijving": tekst, "pagina": 32, "citaat": "x", "citaat_status": status}


def met_groep(cijfers, **extra):
	return {**cijfers, "Memo_Vorderingen_Verbonden": 0.4 * cijfers["Balanstotaal"], **extra}


def test_model_and_ai_flag_on_the_same_fact_are_merged(cijfers):
	rij = bouw_dataframe([met_groep(cijfers, AI_Red_Flags=[ai_flag()])]).iloc[0]
	groep = [vlag for vlag in rij["Red_Flag_Lijst"] if vlag["categorie"] == "verbonden_partijen"]
	assert len(groep) == 1
	assert groep[0]["bron"] == "model + AI" and groep[0]["pagina"] == 32
	assert groep[0]["ernst"] == "hoog"  # the more severe of the two
	assert rij["Red_Flags"].count("affiliated") == 1


def test_unrelated_ai_flag_is_kept_separately(cijfers):
	andere = ai_flag(categorie="juridisch", ernst="middel", tekst="Pending dispute with a customer.")
	rij = bouw_dataframe([met_groep(cijfers, AI_Red_Flags=[ai_flag(), andere])]).iloc[0]
	assert any(vlag["bron"] == "AI" and vlag["categorie"] == "juridisch" for vlag in rij["Red_Flag_Lijst"])


def test_model_flags_get_their_severity_from_config(cijfers):
	rij = bouw_dataframe([met_groep(cijfers)]).iloc[0]
	groep = next(vlag for vlag in rij["Red_Flag_Lijst"] if vlag["sleutel"] == "groepsvorderingen")
	assert groep["ernst"] == config.FLAG_ERNST["groepsvorderingen"] == "middel"
	assert rij["Aantal_Middel_Vlaggen"] >= 1 and rij["Aantal_Hoge_Vlaggen"] == 0


def test_heavy_items_are_high(cijfers):
	rij = bouw_dataframe([{**cijfers, "Eigen_Vermogen": -10.0, "Commissaris_Oordeel": labels.OPINION_QUALIFIED}]).iloc[0]
	assert rij["Aantal_Hoge_Vlaggen"] == 2
	assert rij["Red_Flag_Lijst"][0]["ernst"] == "hoog"  # most severe first


def test_ai_flag_without_a_found_quote_does_not_count(cijfers):
	rij = bouw_dataframe([{**cijfers, "AI_Red_Flags": [ai_flag(categorie="juridisch", status="not found")]}]).iloc[0]
	vlag = next(v for v in rij["Red_Flag_Lijst"] if v["bron"] == "AI")
	assert vlag["telt"] is False and rij["Aantal_Hoge_Vlaggen"] == 0


def test_analyst_case_flags_never_count(cijfers):
	lijst = vlaggen.analist_vlaggen({"LBO_Downside_Convenanten": "BREACHED: Y1 DSCR 0.50x", "LBO_Assumptie_Vlaggen": ["x"]})
	assert len(lijst) == 2 and not any(vlag["telt"] for vlag in lijst)


def test_text_summary_shows_severity_and_source():
	tekst = vlaggen.als_tekst([vlaggen._vlag("groepsvorderingen", "model + AI", "verbonden_partijen", "Group receivables", pagina=32)])
	assert tekst == "[MEDIUM] Group receivables (model + AI, p. 32)"



# --- 5.2 Deal type ------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize(
	"soort, verwacht",
	[("zelfstandig", labels.DEAL_PRIMARY), ("groepsdochter", labels.DEAL_CARVE_OUT), ("pe_backed", labels.DEAL_SECONDARY), ("onbekend", labels.DEAL_UNKNOWN)],
)
def test_deal_type_from_ownership(cijfers, soort, verwacht):
	eigendom = {"type": soort, "moederonderneming": "Groep NV", "ondernemingsnummer_moeder": None, "consoliderend": "ja", "pagina": 1, "citaat": "x"}
	rij = bouw_dataframe([{**cijfers, "AI_Eigendom": eigendom}]).iloc[0]
	assert rij["Dealtype"] == verwacht
	if verwacht == labels.DEAL_CARVE_OUT:
		assert "Groep NV" in rij["Dealtype_Toelichting"]


def test_no_text_pass_gives_unknown(cijfers):
	assert bouw_dataframe([cijfers]).iloc[0]["Dealtype"] == labels.DEAL_UNKNOWN



def test_large_participations_point_to_the_consolidated_accounts(cijfers):
	rij = bouw_dataframe([{**cijfers, "Deelnemingen_Verbonden": 0.5 * cijfers["Balanstotaal"]}]).iloc[0]
	assert any(vlag["sleutel"] == "deelnemingen" and vlag["ernst"] == "middel" for vlag in rij["Red_Flag_Lijst"])
