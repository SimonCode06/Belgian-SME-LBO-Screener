"""The scorecard (0-100) and the robustness grid behind the assessment.

Six components, each scored linearly between a 0-threshold and a 100-threshold from config, with
weights from config. Every component carries its reason, so the label can be explained. All inputs
come from the filing and the screening case: a new AI snapshot cannot change the score.

Robustness: 18 runs of the screening case (entry EBITDA x entry multiple x senior debt). A run passes
when Screening Stress meets the bank tests and Screening Base earns the target IRR.
"""
import math

from . import assumpties, citaten, config, labels, structurering
from .lbo_model import Structuur, bereken_lbo, kies_multiples


def _getal(waarde):
	try:
		waarde = float(waarde)
	except (TypeError, ValueError):
		return float("nan")
	return waarde


def lineair(waarde, nul, vol):
	"""0 at the 0-threshold, 100 at the 100-threshold, linear in between (also when nul > vol)."""
	waarde = _getal(waarde)
	if math.isnan(waarde):
		return 0.0
	deel = (waarde - nul) / (vol - nul)
	return max(0.0, min(1.0, deel)) * 100


def _citaat_aandeel(rij):
	"""(verified quotes, checkable quotes) of the text pass."""
	items = [*(rij.get("AI_Normalisaties") or []), *(rij.get("AI_Red_Flags") or [])]
	if rij.get("AI_Eigendom"):
		items.append(rij["AI_Eigendom"])
	gecontroleerd = [item.get("citaat_status") for item in items if item.get("citaat_status") in (
		citaten.GEVERIFIEERD, citaten.ANDERE_PAGINA, citaten.NIET_GEVONDEN
	)]
	return sum(citaten.is_geverifieerd(status) for status in gecontroleerd), len(gecontroleerd)


def componenten(rij):
	"""[{sleutel, label, gewicht, score, reden}] in the order of config.SCORE_GEWICHTEN."""
	g = config.SCORE_GEWICHTEN
	uit = []

	def voeg(sleutel, score, reden):
		uit.append({"sleutel": sleutel, "label": labels.SCORE_LABELS[sleutel], "gewicht": g[sleutel], "score": score, "reden": reden})

	capaciteit = _getal(rij.get("Debt_Capacity_Multiple"))
	voeg(
		"debt_capacity",
		lineair(capaciteit, *config.SCORE_DEBT_CAPACITY),
		labels.SCORE_REASON_CAPACITY.format(x=0.0 if math.isnan(capaciteit) else capaciteit, binding=rij.get("Debt_Capacity_Bindend") or "-"),
	)

	status = rij.get("ATP_Status")
	if status == labels.ATP_CAP:
		voeg("headroom", 100.0, labels.SCORE_REASON_HEADROOM_CAP)
	elif status == labels.ATP_OK:
		headroom = _getal(rij["ATP_Headroom_Pct"])
		voeg("headroom", lineair(headroom, *config.SCORE_HEADROOM_PCT), labels.SCORE_REASON_HEADROOM.format(
			pct=headroom, multiple=_getal(rij["ATP_Max_Entry_Multiple"]), indicative=_getal(rij["Instap_Multiple"])
		))
	else:
		voeg("headroom", 0.0, str(status or labels.ATP_NA))

	conversie, schommeling = _getal(rij.get("Hist_Cash_Conversion_Pct")), _getal(rij.get("Hist_Marge_Schommeling_pp"))
	voeg(
		"cashflow",
		min(lineair(conversie, *config.SCORE_CASH_CONVERSIE_PCT), lineair(schommeling, *config.SCORE_MARGE_SCHOMMELING_PP)),
		labels.SCORE_REASON_CASHFLOW.format(conversion=conversie, swing=schommeling),
	)

	ebitda_cagr, omzet_cagr = _getal(rij.get("Driver_EBITDA_CAGR_Pct")), _getal(rij.get("Driver_Historische_CAGR_Pct"))
	w = config.SCORE_TREND_GEWICHT_EBITDA
	voeg(
		"trend",
		w * lineair(ebitda_cagr, *config.SCORE_CAGR_PCT) + (1 - w) * lineair(omzet_cagr, *config.SCORE_CAGR_PCT),
		labels.SCORE_REASON_TREND.format(ebitda=ebitda_cagr, revenue=omzet_cagr),
	)

	hoog, middel = int(rij.get("Aantal_Hoge_Vlaggen", 0)), int(rij.get("Aantal_Middel_Vlaggen", 0))
	governance = 0.0 if hoog >= 2 else max(0.0, 100.0 - config.SCORE_STRAF_HOGE_VLAG * hoog - config.SCORE_STRAF_MIDDEL_VLAG * middel)
	voeg("governance", governance, labels.SCORE_REASON_GOVERNANCE.format(high=hoog, medium=middel))

	volledigheid = str(rij.get("Data_Volledigheid", ""))
	geverifieerd, controleerbaar = _citaat_aandeel(rij)
	if rij.get("Check_Data") != labels.CHECK_OK or volledigheid.startswith(labels.DATA_INSUFFICIENT):
		data, reden = 0.0, volledigheid
	elif volledigheid != labels.DATA_COMPLETE:
		data, reden = float(config.SCORE_DATA_GEDEELTELIJK), volledigheid
	elif controleerbaar:
		data = config.SCORE_DATA_VOLLEDIG + (100 - config.SCORE_DATA_VOLLEDIG) * geverifieerd / controleerbaar
		reden = labels.SCORE_REASON_DATA.format(verified=geverifieerd, total=controleerbaar)
	else:
		data, reden = float(config.SCORE_DATA_GEEN_CITATEN), labels.SCORE_REASON_DATA_NO_QUOTES
	voeg("data", data, reden)
	return uit


def totaal(lijst):
	return sum(component["gewicht"] * component["score"] for component in lijst)


def zwakste(lijst, aantal=2):
	return sorted(lijst, key=lambda component: component["score"])[:aantal]


def toelichting(lijst):
	return "; ".join(f"{c['label']} {c['score']:.0f}/100 ({c['reden']})" for c in lijst)


def _variant(rij, deel):
	"""The company earning (1 + deel) x the forecast EBITDA, while price and debt stay sized on the reported EBITDA.

	That is the quality-of-earnings risk: the buyer pays for EBITDA that turns out 10% lower (or higher).
	"""
	if not deel:
		return rij
	nieuw = dict(rij)
	omzet, personeel = float(rij["Omzet_of_Brutomarge"]), float(rij["Personeelskosten"])
	nieuw["LBO_Assumpties"] = {
		**rij["LBO_Assumpties"],
		**{
			scenario: assumpties.verschuif_ebitda(rij["LBO_Assumpties"][scenario], omzet, personeel, deel)
			for scenario in assumpties.SCREENING_SCENARIOS
		},
	}
	return nieuw


def robuustheid(rij):
	"""(share of the 18 runs that pass, the runs). Without debt capacity: 0."""
	capaciteit = _getal(rij.get("Debt_Capacity_Multiple"))
	ebitda = _getal(rij.get("Genormaliseerde_EBITDA"))
	if math.isnan(capaciteit) or math.isnan(ebitda) or ebitda <= 0:
		return 0.0, []
	instap, _ = kies_multiples(ebitda)
	runs = []
	for deel in config.ROBUUST_EBITDA:
		variant = _variant(rij, deel)
		for verschil in config.ROBUUST_MULTIPLE:
			entry = instap + verschil
			for korting in config.ROBUUST_SENIOR_KORTING:
				senior = min(max(0.0, capaciteit - korting), structurering.max_senior_voor_equity(entry, config.LBO_VENDOR_LOAN_PCT_EV))
				structuur = Structuur(entry, instap, senior, config.LBO_VENDOR_LOAN_PCT_EV)
				stress = bereken_lbo(variant, "screening_stress", structuur)
				base = bereken_lbo(variant, "screening_base", structuur)
				irr = _getal(base["LBO_IRR_Exact_Pct"])
				geslaagd = structurering.haalt_covenants(stress) and not math.isnan(irr) and irr >= config.LBO_MIN_IRR_PCT
				runs.append({"ebitda": deel, "multiple": entry, "senior": senior, "irr": irr, "geslaagd": geslaagd})
	return sum(run["geslaagd"] for run in runs) / len(runs), runs


def analyseer(rij):
	lijst = componenten(rij)
	aandeel, runs = robuustheid(rij)
	return {
		"Score": totaal(lijst),
		"Score_Componenten": lijst,
		"Score_Toelichting": toelichting(lijst),
		"Robuustheid_Pct": aandeel * 100,
		"Robuustheid_Runs": runs,
	}
