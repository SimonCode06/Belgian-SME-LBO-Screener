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
from datetime import date

from . import config

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
	"Driver_Omzetgroei_Pct",
	"Driver_Inkoop_Pct",
	"Driver_Overige_Kosten_Pct",
	"Driver_DA_Pct_Vaste_Activa",
	"Driver_Capex_Pct",
	"Driver_DSO",
	"Driver_DIO",
	"Driver_DPO",
	"Driver_Dagen_Vooruitbetaling",
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
WERKKAPITAAL_ACTIVA = ("Voorraden", "Handelsvorderingen", "Overige_Activa_Operationeel")
WERKKAPITAAL_PASSIVA = ("Handelsschulden", "Vooruitbetalingen", "Sociale_Schulden", "Overige_Passiva")


def kies_multiples(ebitda):
	"""Instapmultiple en senior schuldmultiple volgens de grootte van het bedrijf."""
	if math.isnan(ebitda):
		return NIET_BESCHIKBAAR, NIET_BESCHIKBAAR
	for tot, instap, senior in config.LBO_MULTIPLE_TABEL:
		if ebitda < tot:
			return instap, senior
	return NIET_BESCHIKBAAR, NIET_BESCHIKBAAR


def net_debt(doel, financiele_schuld, cash, minimum_cash, debt_like=0.0):
	"""De enige plek die net debt berekent. De definitie per doel staat in config.NET_DEBT_DEFINITIES."""
	definitie = config.NET_DEBT_DEFINITIES[doel]
	schuld = financiele_schuld + debt_like if definitie["debt_like_meetellen"] else financiele_schuld
	aftrekbare_cash = cash - minimum_cash if definitie["alleen_cash_boven_minimum"] else cash
	return schuld - aftrekbare_cash


def net_debt_formule(doel):
	"""De definitie in woorden voor de Excel, afgeleid uit config zodat ze nooit afwijkt van de berekening."""
	definitie = config.NET_DEBT_DEFINITIES[doel]
	schuld = "financiële schuld + debt-like items" if definitie["debt_like_meetellen"] else "financiële schuld"
	cash = "cash boven de minimum operationele cash" if definitie["alleen_cash_boven_minimum"] else "alle cash"
	return f"{schuld} − {cash}. Gebruikt voor: {definitie['gebruik']}."


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


def _glide(start, doel, boekjaar):
	"""Lineair glide path: het laatste boekjaar is de start, na LBO_KOSTEN_GLIDE_JAREN het doel."""
	aandeel = min(boekjaar / config.LBO_KOSTEN_GLIDE_JAREN, 1.0)
	return start + (doel - start) * aandeel


def _plus_jaren(datum, jaren):
	try:
		return datum.replace(year=datum.year + jaren)
	except ValueError:  # 29 februari
		return datum.replace(year=datum.year + jaren, day=28)


def _periodes(boekjaar_einde):
	"""De closing en de forecastperiodes: eventueel een stub, daarna volledige boekjaren tot de exit."""
	einde = date.fromisoformat(boekjaar_einde)
	closing = einde
	if config.LBO_CLOSING_DATUM:
		closing = max(einde, date.fromisoformat(config.LBO_CLOSING_DATUM))

	boekjaar = 1
	while _plus_jaren(einde, boekjaar) <= closing:
		boekjaar += 1
	volgend_einde = _plus_jaren(einde, boekjaar)
	fractie = (volgend_einde - closing).days / (volgend_einde - _plus_jaren(einde, boekjaar - 1)).days

	if fractie == 1.0:
		fracties = [1.0] * config.LBO_HOLDING_PERIOD_YEARS
	else:
		fracties = [fractie] + [1.0] * round(config.LBO_HOLDING_PERIOD_YEARS - fractie)

	periodes = []
	for nr, deel in enumerate(fracties, start=1):
		jaartal = _plus_jaren(einde, boekjaar + nr - 1).year
		periodes.append(
			{
				"Nr": nr,
				"Fractie": deel,
				"Boekjaar_Index": boekjaar + nr - 1,
				"Label": f"{jaartal}F (stub)" if deel < 1 else f"{jaartal}F",
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


def _toets_convenanten(jaren):
	"""Geeft per geschonden convenant de periode en de waarde."""
	breuken = []
	for jaar in jaren[1:]:
		if jaar["DSCR"] < config.LBO_COVENANT_MIN_DSCR:
			breuken.append(f"J{jaar['Jaar']} DSCR {jaar['DSCR']:.2f}x")
		if jaar["Rentedekking"] < config.LBO_COVENANT_MIN_RENTEDEKKING:
			breuken.append(f"J{jaar['Jaar']} rentedekking {jaar['Rentedekking']:.2f}x")
		if jaar["Leverage"] > config.LBO_COVENANT_MAX_LEVERAGE:
			breuken.append(f"J{jaar['Jaar']} leverage {jaar['Leverage']:.2f}x")
		elif jaar["EBITDA"] <= 0:
			breuken.append(f"J{jaar['Jaar']} EBITDA negatief")
	return breuken


def _integriteitstesten(jaren, bronnen, bestedingen, minimum_cash):
	"""De testen van het model. Ze reconstrueren de saldi uit de uitvoer, los van de rekenlus."""
	forecast = jaren[1:]
	senior = jaren[0]["Senior_Lening"]
	rcf = jaren[0]["RCF"]
	eigen_vermogen = jaren[0]["Eigen_Vermogen"]
	afwijking_schuld = abs(jaren[0]["Vendor_Loan"] - forecast[-1]["Vendor_Loan"])
	afwijking_eigen_vermogen = 0.0
	for jaar in forecast:
		senior -= jaar["Verplichte_Aflossing"] + jaar["Cash_Sweep"]
		rcf += jaar["RCF_Opname"] - jaar["RCF_Aflossing"]
		eigen_vermogen += jaar["Nettowinst"] - jaar["Dividend"]
		afwijking_schuld = max(
			afwijking_schuld, abs(senior - jaar["Senior_Lening"]), abs(rcf - jaar["RCF"])
		)
		afwijking_eigen_vermogen = max(afwijking_eigen_vermogen, abs(eigen_vermogen - jaar["Eigen_Vermogen"]))

	laagste_schuld = min(min(jaar["Senior_Lening"], jaar["RCF"], jaar["Vendor_Loan"]) for jaar in jaren)
	tekort = max(0.0, minimum_cash - min(jaar["Cash"] for jaar in forecast))

	def test(naam, definitie, afwijking, tolerantie, soort="FOUT"):
		geslaagd = afwijking < tolerantie if tolerantie else afwijking == 0
		return {
			"Test": naam,
			"Definitie": definitie,
			"Afwijking": afwijking,
			"Tolerantie": tolerantie,
			"Uitkomst": "OK" if geslaagd else soort,
		}

	return [
		test(
			"Balans sluit",
			"Totaal activa − totaal passiva, per periode",
			max(abs(jaar["Balansverschil"]) for jaar in jaren),
			1,
		),
		test(
			"Cash sluit",
			"Eindcash kasstroomtabel = cash volgens de schuldwaterval",
			max(abs(jaar["Cash"] - jaar["Cash_Waterval"]) for jaar in forecast),
			1,
		),
		test("Schuld sluit", "Eindsaldo per tranche uit de mutaties = balans", afwijking_schuld, 1),
		test(
			"Eigen vermogen sluit",
			"Begin + nettowinst − dividend + kapitaal = einde",
			afwijking_eigen_vermogen,
			1,
		),
		test("Bronnen = bestedingen", "Bij closing", abs(bronnen - bestedingen), 1),
		test("Geen negatieve schuld", "Elke tranche ≥ 0", max(0.0, -laagste_schuld), 0),
		test(
			"Rente-iteratie geconvergeerd",
			"Restverschil tussen de laatste twee iteraties",
			max(jaar["Iteratie_Restverschil"] for jaar in forecast),
			1,
		),
		test("Cash ≥ minimum", "Na RCF-trekking (flag, geen rekenfout)", tekort, 0, soort="FLAG"),
	]


def bereken_lbo(rij, scenario="base"):
	"""Rekent de LBO door voor één bedrijf en één scenario. Geeft de samenvatting, 'Jaren' en 'Integriteit' terug."""
	if any(math.isnan(float(rij[veld])) for veld in VEREISTE_VELDEN):
		return _geen_lbo("N.V.T. (Onvoldoende data)")
	ebitda_0 = float(rij["Genormaliseerde_EBITDA"])
	if ebitda_0 <= 0:
		return _geen_lbo("N.V.T. (Geen EBITDA)")

	aannames = config.LBO_SCENARIOS[scenario]
	groei = rij["Driver_Omzetgroei_Pct"] / 100
	prijs = aannames["prijsgroei"]
	volume = (1 + groei) / (1 + config.LBO_SCENARIOS["base"]["prijsgroei"]) - 1 + aannames["volume_delta"]
	indexering = aannames["indexering"]
	da_pct = rij["Driver_DA_Pct_Vaste_Activa"] / 100
	capex_pct = rij["Driver_Capex_Pct"] / 100
	kosten_60 = rij["Driver_Kosten_60_Pct"] / 100
	kosten_6061 = rij["Driver_Kosten_6061_Pct"] / 100

	# 1. Bronnen en bestedingen
	instap_multiple, senior_multiple = kies_multiples(ebitda_0)
	instap_ev = ebitda_0 * instap_multiple
	transactiekosten = instap_ev * config.LBO_TRANSACTIEKOSTEN_PCT
	financieringskosten = instap_ev * config.LBO_FINANCIERINGSKOSTEN_PCT
	kosten = transactiekosten + financieringskosten
	senior_0 = ebitda_0 * senior_multiple
	vendor = instap_ev * config.LBO_VENDOR_LOAN_PCT_EV
	sponsor_equity = instap_ev + kosten - senior_0 - vendor
	rcf_limiet = ebitda_0 * config.LBO_RCF_LIMIET_X_EBITDA
	bronnen = senior_0 + vendor + sponsor_equity
	bestedingen = (
		float(rij["Indicatieve_Equity_Value"]) + float(rij["Adjusted_Net_Debt"]) + transactiekosten + financieringskosten
	)

	# 2. Openingsbalans na de overname
	minimum_cash = float(rij["Minimum_Operationele_Cash"])
	omzet_0 = float(rij["Omzet_of_Brutomarge"])
	personeel_0 = float(rij["Personeelskosten"])
	inkoop_pct_0 = float(rij["Inkoop"]) / omzet_0  # zonder positieve omzet is de LBO al weggevallen (DSO)
	# De overige kosten zijn het residu: zo sluit het laatste boekjaar exact op de instap-EBITDA
	overige_pct_0 = (omzet_0 - float(rij["Inkoop"]) - personeel_0 - ebitda_0) / omzet_0
	inkoop_doel = rij["Driver_Inkoop_Pct"] / 100 + aannames["inkoop_delta"]
	overige_doel = rij["Driver_Overige_Kosten_Pct"] / 100

	vte_0 = float(rij["VTE"])
	vte_elasticiteit = config.LBO_VTE_ELASTICITEIT

	vaste_activa_0 = float(rij["Open_Vaste_Activa"])
	posten = {
		"Voorraden": float(rij["Voorraden"]),
		"Handelsvorderingen": float(rij["Handelsvorderingen"]),
		"Overige_Activa_Operationeel": float(rij["Open_Overige_Activa_Operationeel"]),
		"Handelsschulden": float(rij["Handelsschulden"]),
		"Vooruitbetalingen": float(rij["Ontvangen_Vooruitbetalingen"]),
		"Sociale_Schulden": float(rij["Open_Sociale_Schulden"]),
		"Overige_Passiva": float(rij["Open_Overige_Passiva"]),
	}
	overige_activa_0 = posten["Overige_Activa_Operationeel"]
	sociale_schulden_0 = posten["Sociale_Schulden"]
	overige_passiva_0 = posten["Overige_Passiva"]
	niet_operationeel = float(rij["Open_Overige_Activa_Niet_Operationeel"])
	financiele_activa = float(rij["Open_Financiele_Vaste_Activa"])

	netto_activa = (
		vaste_activa_0
		+ financiele_activa
		+ niet_operationeel
		+ minimum_cash
		+ sum(posten[post] for post in WERKKAPITAAL_ACTIVA)
		- sum(posten[post] for post in WERKKAPITAAL_PASSIVA)
	)
	goodwill_0 = (instap_ev + transactiekosten) - netto_activa

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

	cash = minimum_cash
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
	jaren = [balans("Closing", 0)]

	# 3. Forecast: resultatenrekening, kasstroom, schuldschema en balans
	for periode in periodes:
		fractie = periode["Fractie"]
		boekjaar = periode["Boekjaar_Index"]

		# Kostenstructuur op jaarbasis. De stub neemt daar een deel van.
		omzet_jaar = omzet_0 * ((1 + volume) * (1 + prijs)) ** boekjaar
		vte_groei = (1 + volume * vte_elasticiteit) ** boekjaar
		personeel_jaar = personeel_0 * vte_groei * (1 + indexering) ** boekjaar
		inkoop_pct = _glide(inkoop_pct_0, inkoop_doel, boekjaar)
		overige_pct = _glide(overige_pct_0, overige_doel, boekjaar)
		ebitda_jaar = omzet_jaar * (1 - inkoop_pct - overige_pct) - personeel_jaar

		omzet = omzet_jaar * fractie
		inkoop = omzet_jaar * inkoop_pct * fractie
		personeel = personeel_jaar * fractie
		overige = omzet_jaar * overige_pct * fractie
		ebitda = omzet - inkoop - personeel - overige

		capex = omzet * capex_pct
		afschrijving_bestaand = min(rest_bestaande_activa, vaste_activa_0 * da_pct * fractie)
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
			"Voorraden": rij["Driver_DIO"] / 365 * omzet_jaar * kosten_60,
			"Handelsvorderingen": rij["Driver_DSO"] / 365 * omzet_jaar,
			"Overige_Activa_Operationeel": overige_activa_0 * omzet_jaar / omzet_0,
			"Handelsschulden": rij["Driver_DPO"] / 365 * omzet_jaar * kosten_6061,
			"Vooruitbetalingen": rij["Driver_Dagen_Vooruitbetaling"] / 365 * omzet_jaar,
			"Sociale_Schulden": sociale_schulden_0 * personeel_jaar / personeel_0 if personeel_0 > 0 else sociale_schulden_0,
			"Overige_Passiva": overige_passiva_0 * omzet_jaar / omzet_0,
		}
		delta_twc = sum(posten[post] - posten_begin[post] for post in ("Voorraden", "Handelsvorderingen")) - sum(
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

			rente_senior = saldo_senior * config.LBO_SENIOR_RENTE * fractie
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

			fcf = ebitda - belasting - capex - delta_twc - delta_overig - rente + rente_opbrengst
			verplichte_aflossing = min(senior, senior_0 / config.LBO_SENIOR_LOOPTIJD_JAAR * fractie)
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
			afschrijvingen + goodwill_afschrijving + kosten_afschrijving,
			capex,
			ronde["RCF_Opname"] - ronde["RCF_Aflossing"] - ronde["Verplichte_Aflossing"] - ronde["Cash_Sweep"],
			ronde["Dividend"],
		)

		senior_begin, rcf_begin = senior, rcf
		cash = cash + kasstroom["KS_Netto"]
		senior = senior_eind
		rcf = rcf_eind
		vaste_activa = vaste_activa + capex - afschrijvingen
		rest_bestaande_activa -= afschrijving_bestaand
		goodwill = goodwill - goodwill_afschrijving
		geactiveerde_kosten = geactiveerde_kosten - kosten_afschrijving
		eigen_vermogen = eigen_vermogen + ronde["Nettowinst"] - ronde["Dividend"]
		reserves = reserves + ronde["Nettowinst"] - ronde["Dividend"]

		vte = vte_0 * vte_groei
		ebitda_op_jaarbasis = ebitda / fractie
		schuld = senior + rcf + vendor
		vorige_omzet_jaar = omzet_jaar / ((1 + volume) * (1 + prijs))
		jaren.append(
			balans(
				periode["Label"],
				periode["Nr"],
				Fractie=fractie,
				Omzet=omzet,
				Omzetgroei_Pct=(omzet_jaar / vorige_omzet_jaar - 1) * 100,
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
				DSO=rij["Driver_DSO"],
				DIO=rij["Driver_DIO"],
				DPO=rij["Driver_DPO"],
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
				Rentedekking=_deel(ebitda, ronde["Rente"]),
				DSCR=_deel(
					ebitda - capex - ronde["Belasting"], ronde["Rente"] + ronde["Verplichte_Aflossing"]
				),
				Leverage=_deel(net_debt("bank_covenant", schuld, cash, minimum_cash), ebitda_op_jaarbasis),
			)
		)

	# 4. Uitstap en rendement. De normale cash hoort bij de EV, zoals bij de instap.
	forecast = jaren[1:]
	exit_ebitda = forecast[-1]["EBITDA"] / forecast[-1]["Fractie"]
	exit_ev = max(exit_ebitda, 0.0) * instap_multiple
	eind_net_debt = net_debt("waardering", senior + rcf + vendor, cash, minimum_cash)
	exit_equity = exit_ev - eind_net_debt
	eind_leverage = round(eind_net_debt / exit_ebitda, 2) if exit_ebitda > 0 else NIET_BESCHIKBAAR
	duur = sum(jaar["Fractie"] for jaar in forecast)
	dividenden = sum(jaar["Dividend"] for jaar in forecast)

	if sponsor_equity > 0 and exit_equity > 0:
		moic = round((exit_equity + dividenden) / sponsor_equity, 2)
		kasstromen = [(0.0, -sponsor_equity)]
		tijd = 0.0
		for jaar in forecast:
			tijd += jaar["Fractie"]
			if jaar["Dividend"] > 0:
				kasstromen.append((tijd, jaar["Dividend"]))
		kasstromen.append((duur, exit_equity))
		irr_pct = round(_irr(kasstromen) * 100, 1)
	else:
		moic = 0.0
		irr_pct = -100.0

	breuken = _toets_convenanten(jaren)
	integriteit = _integriteitstesten(jaren, bronnen, bestedingen, minimum_cash)
	balans_ok = not any(test["Uitkomst"] == "FOUT" for test in integriteit)

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
			"JA (< 2,0x)" if eind_leverage < config.LBO_TARGET_END_LEVERAGE else f"NEE ({eind_leverage:.2f}x)"
		),
		"LBO_Laagste_DSCR": round(min(jaar["DSCR"] for jaar in forecast), 2),
		"LBO_Laagste_Rentedekking": round(min(jaar["Rentedekking"] for jaar in forecast), 2),
		"LBO_Hoogste_Leverage": round(max(jaar["Leverage"] for jaar in forecast), 2),
		"LBO_Laagste_Cash": min(jaar["Cash"] for jaar in forecast),
		"LBO_Cash_Onder_Minimum": max(0.0, minimum_cash - min(jaar["Cash"] for jaar in forecast)),
		"LBO_RCF_Limiet": rcf_limiet,
		"LBO_RCF_Piek": max(jaar["RCF"] for jaar in forecast),
		"LBO_RCF_Eind": rcf,
		"LBO_Convenanten": "OK" if not breuken else "GESCHONDEN: " + "; ".join(breuken),
		"LBO_Balanscheck": "OK" if balans_ok else "FOUT",
		"LBO_Exit_EV_Jaar5": exit_ev,
		"LBO_Exit_Equity_Jaar5": exit_equity,
		"Indicatieve_MoIC": moic,
		"Indicatieve_IRR_Pct": irr_pct,
		"Jaren": jaren,
		"Integriteit": integriteit,
	}


def bereken_scenarios(rij):
	"""Rekent elk scenario één keer door. De rest van het project toont dit resultaat."""
	return {scenario: bereken_lbo(rij, scenario) for scenario in config.LBO_SCENARIOS}
