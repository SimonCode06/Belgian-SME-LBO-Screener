"""Debt capacity and ability-to-pay: the two questions a PE fund asks before it bids.

Debt capacity: the highest senior multiple (x LTM EBITDA) at which the company, in the
Screening Stress case, meets every covenant in every year, never drops below the minimum
cash after drawing the RCF, and has repaid the RCF at exit. Found by bisection.

Ability-to-pay: the highest entry multiple at which the sponsor still earns the target IRR
(config.LBO_MIN_IRR_PCT) in the Screening Base case, with senior debt at the lower of the
debt capacity and the table value, and exit at the table multiple (no multiple expansion).
The same is calculated on the analyst (AI) base case, as information.

Everything here runs the Python model; Excel shows the results as inputs (bisection needs no macro).
"""
import math
from dataclasses import replace

from . import config, labels
from .lbo_model import Structuur, bereken_lbo, kies_multiples, standaard_structuur

NIET_BESCHIKBAAR = float("nan")


def _getal(waarde):
	try:
		waarde = float(waarde)
	except (TypeError, ValueError):
		return NIET_BESCHIKBAAR
	return waarde


def haalt_covenants(model):
	"""Every covenant met every year, cash never below the minimum after the RCF, RCF repaid at exit."""
	return (
		model["LBO_Balanscheck"] == labels.CHECK_OK
		and model["LBO_Convenanten"] == labels.COVENANTS_OK
		and model["LBO_Cash_Onder_Minimum"] <= 1.0
		and model["LBO_RCF_Eind"] <= 1.0
	)


def eerste_breuk(model, minimum_cash):
	"""The first test that fails, as 'DSCR Y2', 'Interest Coverage Y1', 'Leverage Y3', 'Minimum Cash Y2' or 'RCF at Exit'."""
	for jaar in model["Jaren"][1:]:
		nr = jaar["Jaar"]
		if jaar["EBITDA"] <= 0:
			return labels.BINDING_EBITDA.format(year=nr)
		if jaar["DSCR"] < config.LBO_COVENANT_MIN_DSCR:
			return labels.BINDING_DSCR.format(year=nr)
		if jaar["Rentedekking"] < config.LBO_COVENANT_MIN_RENTEDEKKING:
			return labels.BINDING_ICR.format(year=nr)
		if jaar["Leverage"] > config.LBO_COVENANT_MAX_LEVERAGE:
			return labels.BINDING_LEVERAGE.format(year=nr)
		if jaar["Cash"] < minimum_cash - 1.0:
			return labels.BINDING_CASH.format(year=nr)
	if model["LBO_RCF_Eind"] > 1.0:
		return labels.BINDING_RCF
	return labels.BINDING_NONE


def debt_capacity(rij):
	"""Returns {multiple, eur, bindend, status}. Bisection on the senior multiple in Screening Stress."""
	ebitda = _getal(rij["Genormaliseerde_EBITDA"])
	leeg = {"multiple": NIET_BESCHIKBAAR, "eur": NIET_BESCHIKBAAR, "bindend": "", "status": labels.CAPACITY_NA}
	if math.isnan(ebitda) or ebitda <= 0 or "screening_stress" not in rij["LBO_Assumpties"]:
		return leeg
	basis = standaard_structuur(ebitda)
	minimum_cash = _getal(rij["Minimum_Operationele_Cash"])

	def toets(multiple):
		model = bereken_lbo(rij, "screening_stress", replace(basis, senior_multiple=multiple))
		if math.isnan(_getal(model["LBO_Instap_EV"])):
			return None, model
		return haalt_covenants(model), model

	ondergrens, bovengrens = config.LBO_DEBT_CAPACITY_MIN, config.LBO_MAX_SENIOR_MULTIPLE
	ok, model = toets(ondergrens)
	if ok is None:
		return leeg
	if not ok:
		return {"multiple": 0.0, "eur": 0.0, "bindend": eerste_breuk(model, minimum_cash), "status": labels.CAPACITY_NONE}
	ok, model = toets(bovengrens)
	if ok:
		return {
			"multiple": bovengrens, "eur": bovengrens * ebitda, "bindend": labels.BINDING_CAP, "status": labels.CAPACITY_OK,
		}
	falend = model
	for _ in range(config.LBO_BISECTIE_MAX_ITERATIES):
		if bovengrens - ondergrens <= config.LBO_DEBT_CAPACITY_PRECISIE:
			break
		midden = (ondergrens + bovengrens) / 2
		ok, model = toets(midden)
		if ok:
			ondergrens = midden
		else:
			bovengrens, falend = midden, model
	return {
		"multiple": ondergrens,
		"eur": ondergrens * ebitda,
		"bindend": eerste_breuk(falend, minimum_cash),
		"status": labels.CAPACITY_OK,
	}


def max_senior_voor_equity(entry_multiple, vendor_pct):
	"""The sponsor puts in at least LBO_MIN_SPONSOR_EQUITY_PCT of the purchase price plus fees."""
	kosten = config.LBO_TRANSACTIEKOSTEN_PCT + config.LBO_FINANCIERINGSKOSTEN_PCT
	return max(0.0, ((1 - config.LBO_MIN_SPONSOR_EQUITY_PCT) * (1 + kosten) - vendor_pct) * entry_multiple)


def ability_to_pay(rij, scenario, senior_multiple):
	"""The entry multiple at which the IRR of the scenario equals the target IRR. Returns a dict."""
	ebitda = _getal(rij["Genormaliseerde_EBITDA"])
	leeg = {"multiple": NIET_BESCHIKBAAR, "ev": NIET_BESCHIKBAAR, "irr": NIET_BESCHIKBAAR, "senior": NIET_BESCHIKBAAR, "status": labels.ATP_NA}
	if math.isnan(ebitda) or ebitda <= 0 or math.isnan(_getal(senior_multiple)) or scenario not in rij["LBO_Assumpties"]:
		return leeg
	exit_multiple, _ = kies_multiples(ebitda)
	doel = config.LBO_MIN_IRR_PCT

	def reken(entry):
		senior = min(senior_multiple, max_senior_voor_equity(entry, config.LBO_VENDOR_LOAN_PCT_EV))
		model = bereken_lbo(rij, scenario, Structuur(entry, exit_multiple, senior, config.LBO_VENDOR_LOAN_PCT_EV))
		return _getal(model["LBO_IRR_Exact_Pct"]), senior

	onder, boven = config.LBO_ATP_MIN_MULTIPLE, config.LBO_ATP_MAX_MULTIPLE
	irr_onder, senior = reken(onder)
	if math.isnan(irr_onder) or irr_onder < doel:
		return {**leeg, "status": labels.ATP_NOT_ACHIEVABLE}
	irr_boven, senior_boven = reken(boven)
	if irr_boven >= doel:
		return {"multiple": boven, "ev": boven * ebitda, "irr": irr_boven, "senior": senior_boven, "status": labels.ATP_CAP}
	beste = (onder, irr_onder, senior)
	for _ in range(config.LBO_BISECTIE_MAX_ITERATIES * 2):
		midden = (onder + boven) / 2
		irr, senior = reken(midden)
		if irr >= doel:
			onder, beste = midden, (midden, irr, senior)
		else:
			boven = midden
		if abs(beste[1] - doel) < config.LBO_ATP_IRR_PRECISIE_PP and boven - onder < 0.01:
			break
	multiple, irr, senior = beste
	return {"multiple": multiple, "ev": multiple * ebitda, "irr": irr, "senior": senior, "status": labels.ATP_OK}


def analyseer(rij):
	"""All phase 4 fields for one company row."""
	capaciteit = debt_capacity(rij)
	_, tabel_senior = kies_multiples(_getal(rij["Genormaliseerde_EBITDA"]))
	senior = min(capaciteit["multiple"], tabel_senior) if not math.isnan(_getal(capaciteit["multiple"])) else NIET_BESCHIKBAAR
	screening = ability_to_pay(rij, "screening_base", senior)
	ai = ability_to_pay(rij, "base", senior)
	ev = _getal(rij["Indicatieve_EV"])
	brug = -_getal(rij["Adjusted_Net_Debt"]) + _getal(rij.get("NWC_Aanpassing", 0.0))

	def headroom(max_ev):
		return (max_ev / ev - 1) * 100 if ev > 0 and not math.isnan(max_ev) else NIET_BESCHIKBAAR

	return {
		"Debt_Capacity_Multiple": capaciteit["multiple"],
		"Debt_Capacity_EUR": capaciteit["eur"],
		"Debt_Capacity_Bindend": capaciteit["bindend"],
		"Debt_Capacity_Status": capaciteit["status"],
		"ATP_Senior_Multiple": screening["senior"],
		"ATP_Max_Entry_Multiple": screening["multiple"],
		"ATP_Max_EV": screening["ev"],
		"ATP_IRR_Pct": screening["irr"],
		"ATP_Headroom_Pct": headroom(screening["ev"]),
		"ATP_Max_Equity_Price": screening["ev"] + brug,
		"ATP_Status": screening["status"],
		"ATP_AI_Max_Entry_Multiple": ai["multiple"],
		"ATP_AI_Max_EV": ai["ev"],
		"ATP_AI_Headroom_Pct": headroom(ai["ev"]),
		"ATP_AI_Status": ai["status"],
	}
