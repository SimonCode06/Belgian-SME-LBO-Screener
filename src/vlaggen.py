"""Structured red flags: one list per company, every flag with a source, category and severity.

Sources: 'model' (Python on the filing and the screening case), 'data' (signals from the CSV),
'AI' (the text pass on the PDF) and 'analyst case' (results of the AI scenarios). Analyst-case
flags are shown but never count in the score or the status: a new AI snapshot may not move the label.

Every model flag gets a fixed severity from config.FLAG_ERNST. A model flag and an AI flag about
the same fact (for example the group receivables) are merged into one row with both sources.
"""
from . import citaten, config, labels

ERNST_VOLGORDE = {"hoog": 0, "middel": 1, "laag": 2}
BRON_MODEL, BRON_DATA, BRON_AI, BRON_ANALIST = "model", "data", "AI", "analyst case"

# Model flag -> (category, keywords that identify the same fact in an AI flag of that category)
SAMENVOEGEN = {
	"groepsvorderingen": ("verbonden_partijen", ("receivab", "vordering", "intercompany", "affiliat", "group")),
	"vordering_bestuurders": ("verbonden_partijen", ("director", "bestuurder", "zaakvoerder", "manager")),
	"commissaris": ("governance", ("auditor", "commissaris", "opinion", "qualified")),
	"vereffening": ("going_concern", ("liquidat", "vereffen")),
}


def _vlag(sleutel, bron, categorie, tekst, ernst=None, pagina=None, telt=True):
	return {
		"sleutel": sleutel,
		"bron": bron,
		"categorie": categorie,
		"ernst": ernst or config.FLAG_ERNST.get(sleutel, "laag"),
		"tekst": tekst,
		"pagina": pagina,
		"telt": telt,
	}


def _getal(rij, veld, standaard=0.0):
	waarde = rij.get(veld, standaard)
	try:
		waarde = float(waarde)
	except (TypeError, ValueError):
		return standaard
	return standaard if waarde != waarde else waarde  # NaN


def model_vlaggen(rij):
	"""Flags from the filing and the screening case (deterministic)."""
	vlaggen = []
	screening = (rij.get("LBO_Scenarios") or {}).get("screening_base") or {}
	stress = (rij.get("LBO_Scenarios") or {}).get("screening_stress") or {}

	def voeg(sleutel, categorie, tekst):
		vlaggen.append(_vlag(sleutel, BRON_MODEL, categorie, tekst))

	if _getal(rij, "Eigen_Vermogen") < 0:
		voeg("negatief_eigen_vermogen", "financieel", labels.FLAG_NEGATIVE_EQUITY.format(value=rij["Eigen_Vermogen"]))
	if _getal(rij, "Overgedragen_Resultaat") < 0:
		voeg("overgedragen_verlies", "financieel", labels.FLAG_ACCUMULATED_LOSS.format(value=rij["Overgedragen_Resultaat"]))
	if rij.get("Commissaris_Oordeel") in labels.OPINIONS_HEAVY:
		voeg("commissaris", "governance", labels.FLAG_AUDITOR.format(opinion=rij["Commissaris_Oordeel"]))
	if labels.FLAG_LIQUIDATION in str(rij.get("Cijfer_Flags", "")):
		voeg("vereffening", "going_concern", labels.FLAG_LIQUIDATION)
	if _getal(rij, "Memo_Vorderingen_Bestuurders") > 0:
		voeg(
			"vordering_bestuurders", "verbonden_partijen",
			labels.FLAG_DIRECTOR_RECEIVABLE.format(value=rij["Memo_Vorderingen_Bestuurders"]),
		)
	balans = _getal(rij, "Balanstotaal")
	groep = _getal(rij, "Memo_Vorderingen_Verbonden")
	if balans > 0 and groep / balans * 100 > config.MAX_GROEPSVORDERINGEN_PCT:
		voeg("groepsvorderingen", "verbonden_partijen", labels.FLAG_GROUP_RECEIVABLES.format(value=groep, pct=groep / balans * 100))
	deelnemingen = _getal(rij, "Deelnemingen_Verbonden")
	if balans > 0 and deelnemingen / balans * 100 > config.MAX_DEELNEMINGEN_PCT:
		voeg("deelnemingen", "financieel", labels.FLAG_PARTICIPATIONS.format(value=deelnemingen, pct=deelnemingen / balans * 100))
	if _getal(rij, "Memo_Zekerheden_Derden") > max(_getal(rij, "Genormaliseerde_EBITDA"), 0):
		voeg("zekerheden_derden", "financieel", labels.FLAG_THIRD_PARTY_GUARANTEES.format(value=rij["Memo_Zekerheden_Derden"]))
	if _getal(rij, "Trade_Working_Capital") < 0:
		voeg("negatief_nwc", "financieel", labels.FLAG_NEGATIVE_NWC.format(value=rij["Trade_Working_Capital"]))
	if _getal(rij, "Minimum_Cash_Behoefte") > _getal(rij, "Liquide_Middelen"):
		voeg("lage_cash", "financieel", labels.FLAG_LOW_CASH.format(cash=rij["Liquide_Middelen"], need=rij["Minimum_Cash_Behoefte"]))
	if _getal(rij, "Omzet_of_Brutomarge_Vorig_Jaar") > 0 and _getal(rij, "Omzetgroei_Pct") < 0:
		voeg("omzetdaling", "financieel", labels.FLAG_REVENUE_DECLINE.format(value=rij["Omzetgroei_Pct"]))
	if _getal(rij, "Omzet_of_Brutomarge_Vorig_Jaar") > 0 and _getal(rij, "Marge_Verandering_pp") < -config.MAX_MARGE_DALING_PP:
		voeg("margedaling", "financieel", labels.FLAG_MARGIN_DECLINE.format(value=rij["Marge_Verandering_pp"]))

	# Results of the screening case: rule-based, so a new AI snapshot cannot change them
	jaren = screening.get("Jaren") or []
	if jaren:
		groei = ((jaren[-1]["Omzet"] / jaren[-1]["Fractie"] / _getal(rij, "Omzet_of_Brutomarge", 1.0)) ** (1 / len(jaren[1:])) - 1) * 100
		if _getal(rij, "Driver_EBITDA_CAGR_Pct") < 0 < groei:
			voeg("ebitda_trend", "financieel", labels.FLAG_EBITDA_TREND.format(cagr=rij["Driver_EBITDA_CAGR_Pct"], growth=groei))
		if _getal(screening, "LBO_RCF_Eind") > 0:
			voeg("rcf_exit", "financieel", labels.FLAG_RCF_AT_EXIT.format(value=screening["LBO_RCF_Eind"]))
		if _getal(screening, "LBO_Cash_Onder_Minimum") > 0:
			voeg("cash_onder_minimum", "financieel", labels.FLAG_CASH_BELOW_MINIMUM.format(value=screening["LBO_Cash_Onder_Minimum"]))
		if _getal(screening, "LBO_RCF_Piek") > 0:
			voeg("rcf_nodig", "financieel", labels.FLAG_RCF_NEEDED.format(peak=screening["LBO_RCF_Piek"], limit=screening["LBO_RCF_Limiet"]))
		eind = _getal(screening, "LBO_Eind_Net_Debt_to_EBITDA", float("nan"))
		if eind == eind and eind >= config.LBO_TARGET_END_LEVERAGE:
			voeg("leverage_doel", "financieel", labels.FLAG_LEVERAGE_TARGET.format(value=eind))
	if str(stress.get("LBO_Convenanten", "")).startswith(labels.COVENANTS_BREACHED):
		detail = stress["LBO_Convenanten"][len(labels.COVENANTS_BREACHED) + 2:]
		voeg("stress_convenanten", "financieel", labels.FLAG_STRESS_COVENANTS.format(detail=detail))
	return vlaggen


def data_vlaggen(rij):
	vlaggen = []
	for signaal in [deel.strip() for deel in str(rij.get("Cijfer_Flags", "") or "").split(";") if deel.strip()]:
		if signaal != labels.FLAG_LIQUIDATION:
			vlaggen.append(_vlag("data_signaal", BRON_DATA, "data", signaal))
	if rij.get("Tekst_Signaal"):
		vlaggen.append(_vlag("data_signaal", BRON_DATA, "data", rij["Tekst_Signaal"]))
	if config.LBO_CLOSING_DATUM and rij.get("LBO_Closing_Datum") and rij["LBO_Closing_Datum"] < config.LBO_CLOSING_DATUM:
		vlaggen.append(_vlag("closing_beperkt", BRON_DATA, "data", labels.FLAG_CLOSING_LIMITED.format(date=rij["LBO_Closing_Datum"])))
	return vlaggen


def ai_vlaggen(rij):
	"""From the text pass. A flag whose quote is not found in the PDF is shown but does not count."""
	vlaggen = []
	for item in rij.get("AI_Red_Flags") or []:
		status = item.get("citaat_status", "")
		soort = labels.FLAG_CATEGORIES.get(item["categorie"], item["categorie"])
		vlaggen.append(
			_vlag(
				"ai", BRON_AI, item["categorie"], f"{soort}: {item['omschrijving']}", ernst=item["ernst"],
				pagina=item.get("pagina"), telt=status != citaten.NIET_GEVONDEN,
			)
		)
	return vlaggen


def analist_vlaggen(rij):
	"""Results of the AI scenarios: information for the analyst, never part of the score or the status."""
	vlaggen = []
	downside = str(rij.get("LBO_Downside_Convenanten", ""))
	if downside.startswith(labels.COVENANTS_BREACHED):
		detail = downside[len(labels.COVENANTS_BREACHED) + 2:]
		vlaggen.append(_vlag("ai_downside", BRON_ANALIST, "analyst_case", labels.FLAG_DOWNSIDE_COVENANTS.format(detail=detail), telt=False))
	for detail in rij.get("LBO_Assumptie_Vlaggen") or []:
		vlaggen.append(_vlag("ai_assumptie", BRON_ANALIST, "analyst_case", labels.FLAG_ASSUMPTIONS.format(detail=detail), telt=False))
	return vlaggen


def samenvoegen(model, ai):
	"""A model flag and an AI flag about the same fact become one row with both sources."""
	over = list(ai)
	resultaat = []
	for vlag in model:
		regel = SAMENVOEGEN.get(vlag["sleutel"])
		if regel:
			categorie, woorden = regel
			gelijk = [a for a in over if a["categorie"] == categorie and any(w in a["tekst"].casefold() for w in woorden)]
			if gelijk:
				over = [a for a in over if a not in gelijk]
				ernst = min([vlag["ernst"], *(a["ernst"] for a in gelijk)], key=ERNST_VOLGORDE.get)
				pagina = next((a["pagina"] for a in gelijk if a["pagina"]), None)
				vlag = {**vlag, "bron": f"{BRON_MODEL} + {BRON_AI}", "ernst": ernst, "pagina": pagina}
		resultaat.append(vlag)
	return resultaat + over


def bouw_vlaggen(rij):
	"""All flags of one company, the most severe first."""
	vlaggen = samenvoegen(model_vlaggen(rij), ai_vlaggen(rij)) + data_vlaggen(rij) + analist_vlaggen(rij)
	return sorted(vlaggen, key=lambda vlag: (not vlag["telt"], ERNST_VOLGORDE.get(vlag["ernst"], 3)))


def als_tekst(vlaggen):
	"""The summary column: '[HIGH] text (model + AI, p. 32)'."""
	regels = []
	for vlag in vlaggen:
		herkomst = vlag["bron"] + (f", p. {vlag['pagina']}" if vlag.get("pagina") else "")
		regels.append(f"[{labels.SEVERITIES.get(vlag['ernst'], vlag['ernst'])}] {vlag['tekst']} ({herkomst})")
	return "; ".join(regels)


def tel(vlaggen, ernst):
	return sum(1 for vlag in vlaggen if vlag["telt"] and vlag["ernst"] == ernst)
