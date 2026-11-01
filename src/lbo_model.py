"""3-statement LBO-model op basis van de NBB-cijfers, per scenario doorgerekend.

Resultatenrekening. De EBITDA is een resultaat, geen input: omzet (volume en prijs), inkoop,
personeel (VTE × kost per VTE × indexering) en overige kosten. De indexering volgt de wet en
niet de klantprijs: zo reageert de marge op kostinflatie en op operationele hefboom. De
instap-EV en de forecast delen één basis: het laatste boekjaar sluit exact op de EBITDA
waarop de sponsor betaalt, daarna lopen de kostenratio's geleidelijk naar hun doelniveau.

Balans. Elke post rolt door. Werkkapitaal volgt de omzet of, voor de sociale schulden, de
loonmassa. Groepsvorderingen en andere niet-operationele posten blijven constant. De cash
komt uit de kasstroomtabel.

Kasstroom. De schuldwaterval start bij de EBITDA (directe methode) en bepaalt de aflossingen.
De kasstroomtabel start bij de nettowinst (indirecte methode) en levert de cash voor de balans.

Integriteit. De testen in _integriteitstesten staan los van de rekenlus: ze reconstrueren de
saldi achteraf uit de uitvoer. Een fout die alle routes op dezelfde manier raakt, zoals een
verkeerde rentevoet, valt daarmee niet op: 'OK' betekent consistent, niet juist.

De overname is cash-free/debt-free: de EV betaalt de bestaande schuld en de verkoper, de
minimum operationele cash blijft in het bedrijf. De goodwill is het verschil tussen de
aankoopprijs (met transactiekosten) en de overgenomen nettoactiva. Ze wordt afgeschreven
(Belgische norm) maar is fiscaal niet aftrekbaar: dat raakt de nettowinst en de uitkeerbare
reserves, niet de cash. De cijfers zijn pro forma, alsof BidCo en OpCo één entiteit zijn.
Financieringskosten worden geactiveerd en lineair afgeschreven over de looptijd van de lening.

Een RCF vangt tekorten op: een tekort op de minimum cash gaat eerst naar een trekking, een
overschot eerst naar de terugbetaling van de RCF, pas daarna naar de sweep en het dividend.
"""
import math
from dataclasses import dataclass
from datetime import date, timedelta

from . import assumpties, config, labels

NIET_BESCHIKBAAR = float("nan")

VEREISTE_VELDEN = [
	"Genormaliseerde_EBITDA",
	"Omzet_of_Brutomarge",
	"Inkoop",
	"Personeelskosten",
	"Minimum_Operationele_Cash",
	"Voorraden",
	"Handelsvorderingen",
	"Handelsschulden",
	"Ontvangen_Vooruitbetalingen",
	"Driver_Kosten_60_Pct",
	"Driver_Kosten_6061_Pct",
	"Open_Vaste_Activa",
	"Open_Financiele_Vaste_Activa",
	"Open_Overige_Activa_Operationeel",
	"Open_Overige_Activa_Niet_Operationeel",
	"Open_Sociale_Schulden",
	"Open_Overige_Passiva",
]

# Werkkapitaalposten in de kasstroomtabel: een stijging van een activapost kost cash
# NWC_Normalisatie: het werkkapitaal dat in jaar 1 wordt aangevuld (of vrijkomt) tot het normale niveau (de peg)
WERKKAPITAAL_ACTIVA = ("Voorraden", "Handelsvorderingen", "Overige_Activa_Operationeel", "NWC_Normalisatie")
WERKKAPITAAL_PASSIVA = ("Handelsschulden", "Vooruitbetalingen", "Sociale_Schulden", "Overige_Passiva")


def kies_multiples(ebitda):
	"""Instapmultiple en senior schuldmultiple volgens de grootte: lineair tussen de ankerpunten, vlak erbuiten."""
	if math.isnan(ebitda):
		return NIET_BESCHIKBAAR, NIET_BESCHIKBAAR
	ankers = sorted(config.LBO_MULTIPLE_ANKERS)
	if ebitda <= ankers[0][0]:
		return ankers[0][1], ankers[0][2]
	for (x0, instap0, senior0), (x1, instap1, senior1) in zip(ankers, ankers[1:]):
		if ebitda <= x1:
			deel = (ebitda - x0) / (x1 - x0)
			return instap0 + deel * (instap1 - instap0), senior0 + deel * (senior1 - senior0)
	return ankers[-1][1], ankers[-1][2]


@dataclass(frozen=True)
class Structuur:
	"""De financieringsstructuur van één doorrekening. Zonder structuur gebruikt het model de standaard."""

	entry_multiple: float
	exit_multiple: float
	senior_multiple: float
	vendor_pct: float
	senior_aflossing: float = None  # verplichte aflossing per jaar, deel van het startbedrag; None = marktband
	senior_rente: float = None      # None = marktband


def senior_markt(ebitda):
	"""(naam, jaarlijkse aflossing, rente) van de senior financiering voor deze dealgrootte."""
	for tot, naam, aflossing, rente in config.LBO_SENIOR_MARKT:
		if ebitda < tot:
			return naam, aflossing, rente
	_, naam, aflossing, rente = config.LBO_SENIOR_MARKT[-1]
	return naam, aflossing, rente


def standaard_structuur(ebitda):
	"""Instap = exit (geen multiple expansion), senior volgens de grootte, vendor loan uit config."""
	instap, senior = kies_multiples(ebitda)
	return Structuur(instap, instap, senior, config.LBO_VENDOR_LOAN_PCT_EV)


def net_debt(doel, financiele_schuld, cash, minimum_cash, debt_like=0.0):
	"""De enige plek die net debt berekent. De definitie per doel staat in config.NET_DEBT_DEFINITIES."""
	definitie = config.NET_DEBT_DEFINITIES[doel]
	schuld = financiele_schuld + debt_like if definitie["debt_like_meetellen"] else financiele_schuld
	aftrekbare_cash = cash - minimum_cash if definitie["alleen_cash_boven_minimum"] else cash
	return schuld - aftrekbare_cash


def net_debt_formule(doel):
	"""De definitie in woorden voor de Excel, afgeleid uit config zodat ze nooit afwijkt van de berekening."""
	definitie = config.NET_DEBT_DEFINITIES[doel]
	schuld = labels.NET_DEBT_FINANCIAL_DEBT_LIKE if definitie["debt_like_meetellen"] else labels.NET_DEBT_FINANCIAL
	cash = labels.NET_DEBT_EXCESS_CASH if definitie["alleen_cash_boven_minimum"] else labels.NET_DEBT_ALL_CASH
	return labels.NET_DEBT_USED_FOR.format(debt=schuld, cash=cash, use=definitie["gebruik"])


def _geen_lbo(reden):
	"""Geen rekenbare LBO: de bedragen blijven leeg in plaats van een schijnbare 0."""
	leeg = NIET_BESCHIKBAAR
	return {
		"LBO_Instap_EV": leeg,
		"LBO_Transactiekosten": leeg,
		"LBO_Financieringskosten": leeg,
		"LBO_Kosten": leeg,
		"LBO_Senior_Schuld": leeg,
		"LBO_Vendor_Loan": leeg,
		"LBO_Sponsor_Equity_Instap": leeg,
		"LBO_Closing_Datum": "",
		"LBO_Duur_Jaren": leeg,
		"LBO_EBITDA_Jaar5": leeg,
		"LBO_EBITDA_Marge_Exit_Pct": leeg,
		"LBO_FCF_Cumulatief_5J": leeg,
		"LBO_Dividend_Cumulatief": leeg,
		"LBO_Eind_Net_Debt_Jaar5": leeg,
		"LBO_Eind_Net_Debt_to_EBITDA": leeg,
		"LBO_Schuld_Onder_2x_5J": reden,
		"LBO_Laagste_DSCR": leeg,
		"LBO_Laagste_Rentedekking": leeg,
		"LBO_Hoogste_Leverage": leeg,
		"LBO_Laagste_Cash": leeg,
		"LBO_Cash_Onder_Minimum": leeg,
		"LBO_RCF_Limiet": leeg,
		"LBO_RCF_Piek": leeg,
		"LBO_RCF_Eind": leeg,
		"LBO_Convenanten": reden,
		"LBO_Balanscheck": reden,
		"LBO_Exit_EV_Jaar5": leeg,
		"LBO_Exit_Equity_Jaar5": leeg,
		"Indicatieve_MoIC": leeg,
		"Indicatieve_IRR_Pct": leeg,
		"LBO_MoIC_Exact": leeg,
		"LBO_IRR_Exact_Pct": leeg,
		"Jaren": [],
		"Integriteit": [],
	}


def _belasting(belastbaar):
	if belastbaar <= 0:
		return 0.0  # verliezen worden niet overgedragen: voorzichtig gerekend
	if config.LBO_KMO_TARIEF_TOEPASSEN:
		eerste_schijf = min(belastbaar, config.LBO_KMO_SCHIJF)
		return eerste_schijf * config.LBO_KMO_TARIEF + (belastbaar - eerste_schijf) * config.LBO_TAX_RATE
	return belastbaar * config.LBO_TAX_RATE


def _aftrekbare_financiering(kosten, opbrengst, ebitda, fractie, periode_nr):
	"""De rente zit op BidCo: pas aftrekbaar na de fusie, en dan binnen de renteaftrekbeperking.

	De beperking geldt op het saldo, dus financiële opbrengsten vergroten de ruimte.
	"""
	if periode_nr < config.LBO_RENTEAFTREK_VANAF_JAAR:
		return 0.0
	plafond = max(config.LBO_RENTEAFTREK_DREMPEL_EUR * fractie, ebitda * config.LBO_RENTEAFTREK_EBITDA_PCT)
	return min(kosten, plafond + opbrengst)


def _irr(kasstromen):
	"""IRR via bisectie op (tijdstip in jaren, bedrag): klopt ook met een stub-periode."""
	def contante_waarde(rendement):
		return sum(stroom / (1 + rendement) ** tijd for tijd, stroom in kasstromen)

	onder, boven = -0.99, 10.0
	if contante_waarde(onder) * contante_waarde(boven) > 0:
		return NIET_BESCHIKBAAR
	for _ in range(200):
		midden = (onder + boven) / 2
		if contante_waarde(onder) * contante_waarde(midden) <= 0:
			boven = midden
		else:
			onder = midden
	return (onder + boven) / 2


def _plus_jaren(datum, jaren):
	try:
		return datum.replace(year=datum.year + jaren)
	except ValueError:  # 29 februari
		return datum.replace(year=datum.year + jaren, day=28)


def _periodes(boekjaar_einde):
	"""De closing en de vijf forecastperiodes: jaar 1 is eventueel een stub tot het eerste boekjaareinde."""
	einde = date.fromisoformat(boekjaar_einde)
	eerste_einde = _plus_jaren(einde, 1)
	closing = einde
	if config.LBO_CLOSING_DATUM:
		closing = max(einde, date.fromisoformat(config.LBO_CLOSING_DATUM))
		closing = min(closing, eerste_einde - timedelta(days=1))
	fractie = (eerste_einde - closing).days / (eerste_einde - einde).days

	periodes = []
	for nr in range(1, config.LBO_HOLDING_PERIOD_YEARS + 1):
		einddatum = _plus_jaren(einde, nr)
		deel = fractie if nr == 1 else 1.0
		periodes.append(
			{
				"Nr": nr,
				"Fractie": deel,
				"Einde": einddatum,
				"Label": labels.period_label(einddatum.year, stub=deel < 1),
			}
		)
	return closing, periodes


def _kasstroomtabel(vorig, huidig, nettowinst, niet_kaskosten, capex, schuldmutatie, dividend):
	"""Indirecte methode: van nettowinst en balansmutaties naar de cash, los van de waterval."""
	mutaties = {f"KS_{post}": vorig[post] - huidig[post] for post in WERKKAPITAAL_ACTIVA}
	mutaties.update({f"KS_{post}": huidig[post] - vorig[post] for post in WERKKAPITAAL_PASSIVA})
	operationeel = nettowinst + niet_kaskosten + sum(mutaties.values())
	return {
		**mutaties,
		"KS_Operationeel": operationeel,
		"KS_Voor_Financiering": operationeel - capex,
		"KS_Financiering": schuldmutatie - dividend,
		"KS_Netto": operationeel - capex + schuldmutatie - dividend,
	}


def _deel(waarde, noemer):
	return waarde / noemer if noemer > 0 else NIET_BESCHIKBAAR


def _convenantratios(ebitda, ebitda_jaar, capex, delta_twc, delta_overig, ronde, senior, rcf, vendor, cash, minimum_cash):
	"""DSCR, interest coverage en leverage volgens config.LBO_COVENANT_DEFINITIE (zie config.py)."""
	totale_schuld = senior + rcf + vendor
	totaal = _deel(net_debt("bank_covenant", totale_schuld, cash, minimum_cash), ebitda_jaar)
	if config.LBO_COVENANT_DEFINITIE == "oud":
		return {
			"CFADS": ebitda - capex - ronde["Belasting"],
			"Rentedekking": _deel(ebitda, ronde["Rente"]),
			"DSCR": _deel(ebitda - capex - ronde["Belasting"], ronde["Rente"] + ronde["Verplichte_Aflossing"]),
			"Leverage": totaal,
			"Leverage_Totaal": totaal,
		}
	bankrente = ronde["Rente_Senior"] + ronde["Rente_RCF"] + ronde["Commitment_Fee"]
	if not config.LBO_VENDOR_ACHTERGESTELD:
		bankrente += ronde["Rente_Vendor"]
	cfads = ebitda - ronde["Belasting"] - capex - delta_twc - delta_overig
	return {
		"CFADS": cfads,
		"Rentedekking": _deel(ebitda, bankrente),
		"DSCR": _deel(cfads, bankrente + ronde["Verplichte_Aflossing"]),
		"Leverage": _deel(senior + rcf - cash, ebitda_jaar),
		"Leverage_Totaal": totaal,
	}


def _toets_convenanten(jaren):
	"""Geeft per geschonden convenant de periode en de waarde."""
	breuken = []
	for jaar in jaren[1:]:
		if jaar["DSCR"] < config.LBO_COVENANT_MIN_DSCR:
			breuken.append(labels.BREACH_DSCR.format(year=jaar["Jaar"], value=jaar["DSCR"]))
		if jaar["Rentedekking"] < config.LBO_COVENANT_MIN_RENTEDEKKING:
			breuken.append(labels.BREACH_INTEREST.format(year=jaar["Jaar"], value=jaar["Rentedekking"]))
		if jaar["Leverage"] > config.LBO_COVENANT_MAX_LEVERAGE:
			breuken.append(labels.BREACH_LEVERAGE.format(year=jaar["Jaar"], value=jaar["Leverage"]))
		elif jaar["EBITDA"] <= 0:
			breuken.append(labels.BREACH_EBITDA.format(year=jaar["Jaar"]))
	return breuken


def _integriteitstesten(jaren, bronnen, bestedingen, minimum_cash):
	"""De testen van het model. Ze reconstrueren de saldi uit de uitvoer, los van de rekenlus."""
	forecast = jaren[1:]
	senior = jaren[0]["Senior_Lening"]
	rcf = jaren[0]["RCF"]
	eigen_vermogen = jaren[0]["Eigen_Vermogen"]
	vendor = jaren[0]["Vendor_Loan"]
	afwijking_schuld = 0.0
	afwijking_eigen_vermogen = 0.0
	for jaar in forecast:
		senior -= jaar["Verplichte_Aflossing"] + jaar["Cash_Sweep"]
		rcf += jaar["RCF_Opname"] - jaar["RCF_Aflossing"]
		vendor += jaar["PIK_Rente"]  # zonder PIK blijft de vendor loan gelijk tot de exit
		eigen_vermogen += jaar["Nettowinst"] - jaar["Dividend"]
		afwijking_schuld = max(
			afwijking_schuld, abs(senior - jaar["Senior_Lening"]), abs(rcf - jaar["RCF"]), abs(vendor - jaar["Vendor_Loan"])
		)
		afwijking_eigen_vermogen = max(afwijking_eigen_vermogen, abs(eigen_vermogen - jaar["Eigen_Vermogen"]))

	laagste_schuld = min(min(jaar["Senior_Lening"], jaar["RCF"], jaar["Vendor_Loan"]) for jaar in jaren)
	tekort = max(0.0, minimum_cash - min(jaar["Cash"] for jaar in forecast))

	def test(omschrijving, afwijking, tolerantie, soort=labels.CHECK_ERROR):
		geslaagd = afwijking < tolerantie if tolerantie else afwijking == 0
		return {
			"Test": omschrijving[0],
			"Definitie": omschrijving[1],
			"Afwijking": afwijking,
			"Tolerantie": tolerantie,
			"Uitkomst": labels.CHECK_OK if geslaagd else soort,
		}

	return [
		test(labels.TEST_BALANCE, max(abs(jaar["Balansverschil"]) for jaar in jaren), 1),
		test(labels.TEST_CASH, max(abs(jaar["Cash"] - jaar["Cash_Waterval"]) for jaar in forecast), 1),
		test(labels.TEST_DEBT, afwijking_schuld, 1),
		test(labels.TEST_EQUITY, afwijking_eigen_vermogen, 1),
		test(labels.TEST_SOURCES, abs(bronnen - bestedingen), 1),
		test(labels.TEST_NEGATIVE_DEBT, max(0.0, -laagste_schuld), 0),
		test(labels.TEST_ITERATION, max(jaar["Iteratie_Restverschil"] for jaar in forecast), 1),
		test(labels.TEST_MINIMUM_CASH, tekort, 0, soort=labels.CHECK_FLAG),
	]


def bereken_lbo(rij, scenario="base", structuur=None):
	"""Rekent de LBO door voor één bedrijf en één scenario. Geeft de samenvatting, 'Jaren' en 'Integriteit' terug.

	structuur: een andere financieringsstructuur (debt capacity, ability-to-pay); None = de standaard.
	"""
	if any(math.isnan(float(rij[veld])) for veld in VEREISTE_VELDEN):
		return _geen_lbo(labels.not_available(labels.REASON_INSUFFICIENT_DATA))
	ebitda_0 = float(rij["Genormaliseerde_EBITDA"])
	if ebitda_0 <= 0:
		return _geen_lbo(labels.not_available(labels.REASON_NO_EBITDA))

	drivers = rij["LBO_Assumpties"][scenario]
	if assumpties.heeft_lege_waarden({scenario: drivers}):
		return _geen_lbo(labels.not_available(labels.REASON_INSUFFICIENT_DATA))

	def driver(sleutel, jaar):
		"""De aanname ongewijzigd: geen begrenzing en geen terugval."""
		return drivers[sleutel]["waarden"][jaar - 1]

	kosten_60 = rij["Driver_Kosten_60_Pct"] / 100
	kosten_6061 = rij["Driver_Kosten_6061_Pct"] / 100

	# 1. Bronnen en bestedingen
	structuur = structuur or standaard_structuur(ebitda_0)
	instap_multiple, senior_multiple = structuur.entry_multiple, structuur.senior_multiple
	_, markt_aflossing, markt_rente = senior_markt(ebitda_0)
	senior_aflossing = markt_aflossing if structuur.senior_aflossing is None else structuur.senior_aflossing
	senior_rente = markt_rente if structuur.senior_rente is None else structuur.senior_rente
	instap_ev = ebitda_0 * instap_multiple
	transactiekosten = instap_ev * config.LBO_TRANSACTIEKOSTEN_PCT
	financieringskosten = instap_ev * config.LBO_FINANCIERINGSKOSTEN_PCT
	kosten = transactiekosten + financieringskosten
	senior_0 = ebitda_0 * senior_multiple
	vendor = instap_ev * structuur.vendor_pct
	# De NWC-aanpassing verandert de prijs voor de verkoper, niet wat de sponsor inbrengt: het verschil
	# blijft als cash in het bedrijf voor de normalisatie van het werkkapitaal in jaar 1
	nwc_aanpassing = float(rij.get("NWC_Aanpassing", 0.0))
	sponsor_equity = instap_ev + kosten - senior_0 - vendor
	rcf_limiet = ebitda_0 * config.LBO_RCF_LIMIET_X_EBITDA
	bronnen = senior_0 + vendor + sponsor_equity
	nwc_aanpassing_0 = float(rij.get("NWC_Aanpassing", 0.0))
	# De equity-prijs volgt de EV van deze structuur (bij de standaard: de indicatieve equity value)
	equity_prijs = instap_ev - float(rij["Adjusted_Net_Debt"]) + nwc_aanpassing_0
	bestedingen = (
		equity_prijs + float(rij["Adjusted_Net_Debt"]) + transactiekosten + financieringskosten
		- nwc_aanpassing_0  # cash die in het bedrijf blijft voor de normalisatie van het werkkapitaal
	)

	# 2. Openingsbalans na de overname
	minimum_cash = float(rij["Minimum_Operationele_Cash"])
	omzet_0 = float(rij["Omzet_of_Brutomarge"])
	personeel_0 = float(rij["Personeelskosten"])
	vte_0 = float(rij["VTE"])

	vaste_activa_0 = float(rij["Open_Vaste_Activa"])
	posten = {
		"Voorraden": float(rij["Voorraden"]),
		"Handelsvorderingen": float(rij["Handelsvorderingen"]),
		"Overige_Activa_Operationeel": float(rij["Open_Overige_Activa_Operationeel"]),
		"NWC_Normalisatie": 0.0,
		"Handelsschulden": float(rij["Handelsschulden"]),
		"Vooruitbetalingen": float(rij["Ontvangen_Vooruitbetalingen"]),
		"Sociale_Schulden": float(rij["Open_Sociale_Schulden"]),
		"Overige_Passiva": float(rij["Open_Overige_Passiva"]),
	}
	overige_activa_0 = posten["Overige_Activa_Operationeel"]
	sociale_schulden_0 = posten["Sociale_Schulden"]
	overige_passiva_0 = posten["Overige_Passiva"]
	# Groepsvorderingen die vóór closing vereffend worden, staan niet meer op de openingsbalans
	niet_operationeel = float(rij["Open_Overige_Activa_Niet_Operationeel"]) - float(rij.get("Open_Intercompany_Cash_Like", 0.0))
	financiele_activa = float(rij["Open_Financiele_Vaste_Activa"])

	netto_activa = (
		vaste_activa_0
		+ financiele_activa
		+ niet_operationeel
		+ minimum_cash
		+ sum(posten[post] for post in WERKKAPITAAL_ACTIVA)
		- sum(posten[post] for post in WERKKAPITAAL_PASSIVA)
	)
	goodwill_0 = (instap_ev + nwc_aanpassing + transactiekosten) - netto_activa

	def balans(periode_label, periode_nr, **resultaat):
		"""Eén kolom van het model: de balans wordt altijd volledig opnieuw opgeteld."""
		activa = (
			goodwill + geactiveerde_kosten + vaste_activa + financiele_activa + niet_operationeel + cash
			+ sum(posten[post] for post in WERKKAPITAAL_ACTIVA)
		)
		passiva = eigen_vermogen + senior + rcf + vendor + sum(posten[post] for post in WERKKAPITAAL_PASSIVA)
		financiele_schuld = senior + rcf + vendor
		return {
			"Jaar": periode_nr,
			"Label": periode_label,
			**resultaat,
			**posten,
			"Goodwill": goodwill,
			"Geactiveerde_Financieringskosten": geactiveerde_kosten,
			"Vaste_Activa": vaste_activa,
			"Financiele_Vaste_Activa": financiele_activa,
			"Overige_Activa_Niet_Operationeel": niet_operationeel,
			"Cash": cash,
			"Totaal_Activa": activa,
			"Eigen_Vermogen": eigen_vermogen,
			"Senior_Lening": senior,
			"RCF": rcf,
			"Vendor_Loan": vendor,
			"Totaal_Passiva": passiva,
			"Balansverschil": round(activa - passiva, 2),
			"Net_Debt_Bank_Covenant": net_debt("bank_covenant", financiele_schuld, cash, minimum_cash),
			"Net_Debt_Waardering": net_debt("waardering", financiele_schuld, cash, minimum_cash),
		}

	cash = minimum_cash - nwc_aanpassing
	senior = senior_0
	rcf = 0.0
	eigen_vermogen = sponsor_equity
	goodwill = goodwill_0
	geactiveerde_kosten = financieringskosten
	vaste_activa = vaste_activa_0
	reserves = 0.0
	rest_bestaande_activa = vaste_activa_0
	vintages = []  # [aankoopwaarde, nog af te schrijven]
	closing, periodes = _periodes(rij["Boekjaar_Einde"])
	jaren = [balans(labels.LABEL_CLOSING, 0)]
	omzet_jaar = omzet_0
	personeel_jaar = personeel_0
	vte = vte_0

	# 3. Forecast: resultatenrekening, kasstroom, schuldschema en balans
	for periode in periodes:
		fractie = periode["Fractie"]
		jaar = periode["Nr"]

		# Kostenstructuur op jaarbasis. De stub neemt daar een deel van.
		volume = driver("volumegroei", jaar) / 100
		prijs = driver("prijsgroei", jaar) / 100
		vte_factor = 1 + volume * driver("vte_elasticiteit", jaar)
		inkoop_pct = driver("inkoop_pct", jaar) / 100
		overige_pct = driver("overige_kosten_pct", jaar) / 100
		capex_pct = driver("capex_pct", jaar) / 100

		omzet_jaar = omzet_jaar * (1 + volume) * (1 + prijs)
		personeel_jaar = personeel_jaar * vte_factor * (1 + driver("loonindexering", jaar) / 100)
		vte = vte * vte_factor

		omzet = omzet_jaar * fractie
		inkoop = omzet_jaar * inkoop_pct * fractie
		personeel = personeel_jaar * fractie
		overige = omzet_jaar * overige_pct * fractie
		ebitda = omzet - inkoop - personeel - overige

		capex = omzet * capex_pct
		afschrijving_bestaand = min(
			rest_bestaande_activa, vaste_activa_0 * driver("da_pct", jaar) / 100 * fractie
		)
		vintages.append([capex, capex])
		afschrijving_nieuw = 0.0
		for vintage in vintages:
			deel = min(vintage[1], vintage[0] / config.LBO_CAPEX_LEVENSDUUR_JAAR * fractie)
			vintage[1] -= deel
			afschrijving_nieuw += deel
		afschrijvingen = afschrijving_bestaand + afschrijving_nieuw
		# Negatieve goodwill (netto-activa boven de prijs) wordt niet afgeschreven
		goodwill_afschrijving = min(max(goodwill, 0.0), max(goodwill_0, 0.0) / config.LBO_GOODWILL_LOOPTIJD_JAAR * fractie)
		kosten_afschrijving = min(
			geactiveerde_kosten, financieringskosten / config.LBO_SENIOR_LOOPTIJD_JAAR * fractie
		)

		posten_begin = dict(posten)
		posten = {
			"Voorraden": driver("dio", jaar) / config.DAGEN_PER_JAAR * omzet_jaar * kosten_60,
			"Handelsvorderingen": driver("dso", jaar) / config.DAGEN_PER_JAAR * omzet_jaar,
			"Overige_Activa_Operationeel": overige_activa_0 * omzet_jaar / omzet_0,
			"NWC_Normalisatie": -nwc_aanpassing,
			"Handelsschulden": driver("dpo", jaar) / config.DAGEN_PER_JAAR * omzet_jaar * kosten_6061,
			"Vooruitbetalingen": driver("dagen_vooruitbetaling", jaar) / config.DAGEN_PER_JAAR * omzet_jaar,
			"Sociale_Schulden": sociale_schulden_0 * personeel_jaar / personeel_0 if personeel_0 > 0 else sociale_schulden_0,
			"Overige_Passiva": overige_passiva_0 * omzet_jaar / omzet_0,
		}
		delta_twc = sum(
			posten[post] - posten_begin[post] for post in ("Voorraden", "Handelsvorderingen", "NWC_Normalisatie")
		) - sum(
			posten[post] - posten_begin[post] for post in ("Handelsschulden", "Vooruitbetalingen")
		)
		delta_overig = (
			posten["Overige_Activa_Operationeel"] - posten_begin["Overige_Activa_Operationeel"]
			- (posten["Sociale_Schulden"] - posten_begin["Sociale_Schulden"])
			- (posten["Overige_Passiva"] - posten_begin["Overige_Passiva"])
		)

		def reken(senior_eind, rcf_eind, cash_eind):
			"""Eén rekenronde van de periode, gegeven een schatting van de eindsaldi voor de rente."""
			gemiddeld = config.LBO_RENTE_BASIS == "gemiddeld"
			saldo_senior = (senior + senior_eind) / 2 if gemiddeld else senior
			saldo_rcf = (rcf + rcf_eind) / 2 if gemiddeld else rcf
			saldo_cash = (cash + cash_eind) / 2 if gemiddeld else cash

			rente_senior = saldo_senior * senior_rente * fractie
			rente_rcf = saldo_rcf * config.LBO_RCF_RENTE * fractie
			commitment_fee = (rcf_limiet - saldo_rcf) * config.LBO_RCF_COMMITMENT_FEE * fractie
			rente_vendor = vendor * config.LBO_VENDOR_LOAN_RENTE * fractie
			rente = rente_senior + rente_rcf + commitment_fee + rente_vendor
			rente_opbrengst = max(saldo_cash, 0.0) * config.LBO_CASH_RENTE * fractie

			aftrekbaar = _aftrekbare_financiering(
				rente + kosten_afschrijving, rente_opbrengst, ebitda, fractie, periode["Nr"]
			)
			# De goodwillafschrijving is fiscaal niet aftrekbaar en blijft dus buiten de basis
			belasting = _belasting(ebitda - afschrijvingen + rente_opbrengst - aftrekbaar)
			ebit = ebitda - afschrijvingen - goodwill_afschrijving
			winst_voor_belasting = ebit - rente - kosten_afschrijving + rente_opbrengst
			nettowinst = winst_voor_belasting - belasting

			# PIK: de rente op de vendor loan wordt gekapitaliseerd en verlaat de waterval niet
			pik = rente_vendor if config.LBO_VENDOR_LOAN_PIK else 0.0
			fcf = ebitda - belasting - capex - delta_twc - delta_overig - (rente - pik) + rente_opbrengst
			verplichte_aflossing = min(senior, senior_0 * senior_aflossing * fractie)
			excess_cash_flow = fcf - verplichte_aflossing

			# Waterval: tekort op de minimum cash naar de RCF, overschot eerst naar de RCF en dan naar de sweep
			positie = cash + excess_cash_flow - minimum_cash
			rcf_opname = min(max(0.0, -positie), rcf_limiet - rcf)
			rcf_aflossing = min(max(0.0, positie), rcf)
			# Alleen de kasstroom van dit jaar: wat vorige jaren is opgebouwd, wordt niet opnieuw geswept.
			sweep = min(
				max(0.0, excess_cash_flow - rcf_aflossing) * config.LBO_CASH_SWEEP_PCT,
				max(0.0, positie - rcf_aflossing),
				senior - verplichte_aflossing,
			)

			rcf_nieuw = max(0.0, rcf + rcf_opname - rcf_aflossing)
			vrij = min(excess_cash_flow, positie) - rcf_aflossing - sweep
			dividend = 0.0
			if rcf_nieuw == 0.0:
				dividend = min(max(0.0, vrij) * config.LBO_DIVIDEND_PCT, max(0.0, reserves + nettowinst))

			return {
				"Rente_Senior": rente_senior,
				"Rente_RCF": rente_rcf,
				"Commitment_Fee": commitment_fee,
				"Rente_Vendor": rente_vendor,
				"PIK_Rente": pik,
				"Rente": rente,
				"Rente_Opbrengst": rente_opbrengst,
				"Belasting": belasting,
				"EBIT": ebit,
				"Winst_Voor_Belasting": winst_voor_belasting,
				"Nettowinst": nettowinst,
				"FCF": fcf,
				"Verplichte_Aflossing": verplichte_aflossing,
				"Excess_Cash_Flow": excess_cash_flow,
				"RCF_Opname": rcf_opname,
				"RCF_Aflossing": rcf_aflossing,
				"Cash_Sweep": sweep,
				"Dividend": dividend,
				"senior_eind": max(0.0, senior - verplichte_aflossing - sweep),
				"rcf_eind": rcf_nieuw,
				"cash_eind": cash + excess_cash_flow + rcf_opname - rcf_aflossing - sweep - dividend,
			}

		schatting = (senior, rcf, cash)
		restverschil = 0.0
		if config.LBO_RENTE_BASIS == "gemiddeld":
			for _ in range(config.LBO_RENTE_ITERATIES):
				ronde = reken(*schatting)
				nieuw = (ronde["senior_eind"], ronde["rcf_eind"], ronde["cash_eind"])
				restverschil = max(abs(a - b) for a, b in zip(nieuw, schatting))
				schatting = nieuw
		else:
			ronde = reken(*schatting)
		senior_eind = ronde.pop("senior_eind")
		rcf_eind = ronde.pop("rcf_eind")
		cash_waterval = ronde.pop("cash_eind")

		kasstroom = _kasstroomtabel(
			posten_begin,
			posten,
			ronde["Nettowinst"],
			afschrijvingen + goodwill_afschrijving + kosten_afschrijving + ronde["PIK_Rente"],
			capex,
			ronde["RCF_Opname"] - ronde["RCF_Aflossing"] - ronde["Verplichte_Aflossing"] - ronde["Cash_Sweep"],
			ronde["Dividend"],
		)

		senior_begin, rcf_begin = senior, rcf
		vendor = vendor + ronde["PIK_Rente"]
		cash = cash + kasstroom["KS_Netto"]
		senior = senior_eind
		rcf = rcf_eind
		vaste_activa = vaste_activa + capex - afschrijvingen
		rest_bestaande_activa -= afschrijving_bestaand
		goodwill = goodwill - goodwill_afschrijving
		geactiveerde_kosten = geactiveerde_kosten - kosten_afschrijving
		eigen_vermogen = eigen_vermogen + ronde["Nettowinst"] - ronde["Dividend"]
		reserves = reserves + ronde["Nettowinst"] - ronde["Dividend"]

		ebitda_op_jaarbasis = ebitda / fractie
		schuld = senior + rcf + vendor
		jaren.append(
			balans(
				periode["Label"],
				periode["Nr"],
				Fractie=fractie,
				Einde=periode["Einde"].isoformat(),
				Omzet=omzet,
				Omzetgroei_Pct=((1 + volume) * (1 + prijs) - 1) * 100,
				Inkoop=inkoop,
				Personeel=personeel,
				Overige_Kosten=overige,
				EBITDA=ebitda,
				EBITDA_Marge_Pct=ebitda / omzet * 100,
				Inkoop_Pct=inkoop_pct * 100,
				Personeel_Pct=personeel / omzet * 100,
				Overige_Pct=overige_pct * 100,
				Capex_Pct=capex_pct * 100,
				VTE=vte,
				Kost_Per_VTE=personeel_jaar / vte if vte > 0 else NIET_BESCHIKBAAR,
				DSO=driver("dso", jaar),
				DIO=driver("dio", jaar),
				DPO=driver("dpo", jaar),
				Advance_Days=driver("dagen_vooruitbetaling", jaar),
				Afschrijvingen=afschrijvingen,
				Afschrijving_Bestaand=afschrijving_bestaand,
				Afschrijving_Nieuw=afschrijving_nieuw,
				Goodwill_Afschrijving=goodwill_afschrijving,
				Afschrijving_Financieringskosten=kosten_afschrijving,
				Financieel_Resultaat=ronde["Rente_Opbrengst"] - ronde["Rente"] - kosten_afschrijving,
				Capex=capex,
				Delta_TWC=delta_twc,
				Delta_Overig=delta_overig,
				**ronde,
				**kasstroom,
				Senior_Begin=senior_begin,
				RCF_Begin=rcf_begin,
				RCF_Ruimte=rcf_limiet - rcf,
				Cash_Waterval=cash_waterval,
				Iteratie_Restverschil=restverschil,
				**_convenantratios(
					ebitda, ebitda_op_jaarbasis, capex,
					# De normalisatie van het werkkapitaal is bij closing al gefinancierd: niet in de CFADS
					delta_twc - (posten["NWC_Normalisatie"] - posten_begin["NWC_Normalisatie"]),
					delta_overig, ronde, senior, rcf, vendor, cash, minimum_cash,
				),
			)
		)

	# 4. Uitstap en rendement. De normale cash hoort bij de EV, zoals bij de instap.
	forecast = jaren[1:]
	exit_ebitda = forecast[-1]["EBITDA"] / forecast[-1]["Fractie"]
	exit_ev = max(exit_ebitda, 0.0) * structuur.exit_multiple
	eind_net_debt = net_debt("waardering", senior + rcf + vendor, cash, minimum_cash)
	exit_equity = exit_ev - eind_net_debt
	eind_leverage = round(eind_net_debt / exit_ebitda, 2) if exit_ebitda > 0 else NIET_BESCHIKBAAR
	duur = sum(jaar["Fractie"] for jaar in forecast)
	dividenden = sum(jaar["Dividend"] for jaar in forecast)

	if sponsor_equity > 0 and exit_equity > 0:
		moic = (exit_equity + dividenden) / sponsor_equity
		# Zonder stub zijn de periodes gelijk (Excel: IRR). Met een stub telt de datum (Excel: XIRR).
		met_stub = forecast[0]["Fractie"] < 1
		kasstromen = [(0.0, -sponsor_equity)]
		tijd = 0.0
		for jaar, periode in zip(forecast, periodes):
			tijd = (periode["Einde"] - closing).days / config.DAGEN_PER_JAAR if met_stub else tijd + 1
			kasstromen.append((tijd, jaar["Dividend"] + (exit_equity if jaar is forecast[-1] else 0.0)))
		irr_pct = _irr(kasstromen) * 100
	else:
		moic = 0.0
		irr_pct = -100.0

	breuken = _toets_convenanten(jaren)
	integriteit = _integriteitstesten(jaren, bronnen, bestedingen, minimum_cash)
	balans_ok = not any(test["Uitkomst"] == labels.CHECK_ERROR for test in integriteit)

	return {
		"LBO_Instap_EV": instap_ev,
		"LBO_Transactiekosten": transactiekosten,
		"LBO_Financieringskosten": financieringskosten,
		"LBO_Kosten": kosten,
		"LBO_Senior_Schuld": senior_0,
		"LBO_Vendor_Loan": vendor,
		"LBO_Sponsor_Equity_Instap": sponsor_equity,
		"LBO_Closing_Datum": closing.isoformat(),
		"LBO_Duur_Jaren": round(duur, 2),
		"LBO_EBITDA_Jaar5": exit_ebitda,
		"LBO_EBITDA_Marge_Exit_Pct": forecast[-1]["EBITDA_Marge_Pct"],
		"LBO_FCF_Cumulatief_5J": sum(jaar["FCF"] for jaar in forecast),
		"LBO_Dividend_Cumulatief": dividenden,
		"LBO_Eind_Net_Debt_Jaar5": eind_net_debt,
		"LBO_Eind_Net_Debt_to_EBITDA": eind_leverage,
		"LBO_Schuld_Onder_2x_5J": (
			labels.debt_target(eind_leverage < config.LBO_TARGET_END_LEVERAGE, eind_leverage)
		),
		"LBO_Laagste_DSCR": round(min(jaar["DSCR"] for jaar in forecast), 2),
		"LBO_Laagste_Rentedekking": round(min(jaar["Rentedekking"] for jaar in forecast), 2),
		"LBO_Hoogste_Leverage": round(max(jaar["Leverage"] for jaar in forecast), 2),
		"LBO_Laagste_Cash": min(jaar["Cash"] for jaar in forecast),
		"LBO_Cash_Onder_Minimum": max(0.0, minimum_cash - min(jaar["Cash"] for jaar in forecast)),
		"LBO_RCF_Limiet": rcf_limiet,
		"LBO_RCF_Piek": max(jaar["RCF"] for jaar in forecast),
		"LBO_RCF_Eind": rcf,
		"LBO_Convenanten": labels.COVENANTS_OK if not breuken else labels.covenants_breached(breuken),
		"LBO_Balanscheck": labels.CHECK_OK if balans_ok else labels.CHECK_ERROR,
		"LBO_Exit_EV_Jaar5": exit_ev,
		"LBO_Exit_Equity_Jaar5": exit_equity,
		"Indicatieve_MoIC": round(moic, 2),
		"Indicatieve_IRR_Pct": round(irr_pct, 1),
		"LBO_MoIC_Exact": moic,
		"LBO_IRR_Exact_Pct": irr_pct,
		"Jaren": jaren,
		"Integriteit": integriteit,
	}


def bereken_scenarios(rij):
	"""Rekent elk scenario één keer door (analyst case + screening case). De rest van het project toont dit resultaat."""
	return {scenario: bereken_lbo(rij, scenario) for scenario in assumpties.MODEL_SCENARIOS if scenario in rij["LBO_Assumpties"]}
