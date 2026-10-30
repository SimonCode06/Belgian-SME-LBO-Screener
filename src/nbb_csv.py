"""Leest NBB-jaarrekeningen uit CSV: de cijfers komen rechtstreeks uit de neerlegging.

Een CSV bevat één boekjaar en geen kolom 'vorig boekjaar'. Daarom worden alle
CSV's van een bedrijf samengebracht en komt vorig jaar uit de CSV van dat jaar.
Bedrijf en boekjaar komen uit de inhoud van het bestand, nooit uit de bestandsnaam.

Een code die niet in de CSV staat, kan twee dingen betekenen: de rubriek is leeg
(echt 0) of het schema kent de rubriek niet (onbekend). Een code telt alleen als 0
als het bovenliggende totaal sluit zonder die code, of als andere cijfers bewijzen
dat dit deel van het formulier bestaat. Anders blijft de waarde leeg (NaN).

Resultaten worden omgerekend naar 12 maanden, zodat een verlengd of verkort
boekjaar de groei niet vertekent. Balansposten blijven ongewijzigd.
"""
import csv
import math
from dataclasses import dataclass
from datetime import date, timedelta

from . import config, labels

NIET_BESCHIKBAAR = float("nan")

# (naam, totaalcode, onderdelen). Een '-' betekent dat het onderdeel wordt afgetrokken.
OPBOUW = [
	("activa = passiva", "20/58", ("10/49",)),
	("opbouw activa", "20/58", ("20", "21/28", "29/58")),
	("opbouw vaste activa", "21/28", ("21", "22/27", "28")),
	("opbouw vlottende activa", "29/58", ("29", "3", "40/41", "50/53", "54/58", "490/1")),
	("opbouw vorderingen", "40/41", ("40", "41")),
	("opbouw passiva", "10/49", ("10/15", "16", "17/49")),
	("opbouw schulden", "17/49", ("17", "42/48", "492/3")),
	("opbouw schulden LT", "17", ("170/4", "175", "176", "178/9")),
	("opbouw schulden KT", "42/48", ("42", "43", "44", "45", "46", "47/48")),
	("opbouw fiscale en sociale schulden", "45", ("450/3", "454/9")),
	("opbouw bedrijfswinst", "9901", ("70/76A", "-60/66A")),
	("opbouw bedrijfsopbrengsten", "70/76A", ("70", "71", "72", "74", "76A")),
	("opbouw bedrijfskosten", "60/66A", ("60", "61", "62", "630", "631/4", "635/8", "640/8", "-649", "66A")),
	("opbouw vanuit brutomarge", "9901", ("9900", "-62", "-630", "-631/4", "-635/8", "-640/8", "649", "-66A")),
]
# Deze regels gelden alleen als het schema de genoemde vertrekcode gebruikt
VERTREKCODES = {"9900", "70/76A", "60/66A"}

# Uitsplitsingen uit de toelichting. Micro-schema's hebben die niet: daar bewijzen
# ze alleen dat een code 0 is als het totaal zelf 0 is, en een verschil is geen rekenfout.
BEWIJS_OPBOUW = [
	("uitsplitsing belastingen", "450/3", ("450", "9072", "9073")),
	("uitsplitsing sociale schulden", "454/9", ("9076", "9077")),
]

# Een lege code is ook 0 als een ander cijfer bewijst dat dit deel van het formulier bestaat:
# 76A is een 'waarvan'-regel bij de brutomarge, de andere staan samen in dezelfde toelichting.
TOELICHTING_SCHULDEN = ("450", "9072", "9073", "9076", "9077")
BEKEND_ALS_AANWEZIG = {
	"76A": ("9900",),
	"450": TOELICHTING_SCHULDEN,
	"9072": TOELICHTING_SCHULDEN,
	"9076": TOELICHTING_SCHULDEN,
}

VERPLICHTE_CODES = ("20/58", "10/49", "9901")

# 635/8 wordt teruggeteld omdat de voorzieningen op de balans (code 16) al debt-like zijn.
# 631/4 niet: dubieuze debiteuren en voorraadverliezen zijn een terugkerende bedrijfskost.
EBITDA_CODES = ("9901", "630", "635/8")

# Aanschaffingen uit de staat van de vaste activa. Het volledige schema splitst per
# categorie uit, het verkorte en micro-schema geven alleen het totaal.
# (totaalcode, codes per categorie, begin van de codes van die staat, balansrubriek)
CAPEX_STATEN = [
	("8169", ("8161", "8162", "8163", "8164", "8165", "8166"), "819", "22/27"),
	("8029", ("8021", "8022", "8023", "8024"), "805", "21"),
]

# Zonder deze velden kan het bedrijf niet beoordeeld worden
RESULTAATVELDEN = {
	"Bedrijfswinst_EBIT": ("9901",),
	"Afschrijvingen": ("630",),
	"Voorzieningen_Mutatie": ("635/8",),
	"Personeelskosten": ("62",),
}
BALANSVELDEN = {
	"Financiele_Schulden_LT": ("170/4",),
	"Financiele_Schulden_KT": ("42", "43"),
	"Voorzieningen_en_Uitgestelde_Belastingen": ("16",),
	"Belasting_en_Vervallen_RSZ_Schulden": ("450", "9072", "9076"),
	"Overige_Schulden_LT_en_KT": ("178/9", "47/48"),
	"Voorraden": ("3",),
	"Handelsvorderingen": ("40",),
	"Handelsschulden": ("44",),
	"Ontvangen_Vooruitbetalingen": ("46",),
	"Eigen_Vermogen": ("10/15",),
}
LIQUIDE_CODES = ("50/53", "54/58")


@dataclass
class Neerlegging:
	"""Eén ingelezen CSV: één boekjaar van één bedrijf."""

	bestand: str
	ondernemingsnummer: str
	naam: str
	begin: date
	einde: date
	referentie: str
	valuta: str
	vereffening: bool
	correctie: bool
	codes: dict
	model: str = ""

	@property
	def boekjaar(self):
		return str(self.einde.year)

	@property
	def maanden(self):
		return (self.einde.year - self.begin.year) * 12 + self.einde.month - self.begin.month + 1

	@property
	def schema(self):
		"""VOL, MIC of VKT/MIC als de modelcode onbekend is en het schema brutomarge gebruikt."""
		bekend = config.MODEL_SCHEMAS.get(self.model.split("-")[0])
		if bekend:
			return bekend
		return "VOL" if "70/76A" in self.codes and "9900" not in self.codes else "VKT/MIC"

	def bedrag(self, *codes):
		"""Telt codes op, waarbij een afwezige code 0 is. Alleen voor het narekenen van totalen."""
		return sum(
			-self.codes.get(code[1:], 0.0) if code.startswith("-") else self.codes.get(code, 0.0)
			for code in codes
		)

	def sluit_aan(self, totaal, onderdelen):
		return abs(self.bedrag(totaal) - self.bedrag(*onderdelen)) <= config.CSV_TOLERANTIE_EUR

	def regel_geldt(self, onderdelen):
		return all(code in self.codes for code in onderdelen if code.lstrip("-") in VERTREKCODES)

	def is_bekend(self, code):
		"""True als de code in de CSV staat of als de totalen bewijzen dat ze 0 is."""
		if code in self.codes or any(buur in self.codes for buur in BEKEND_ALS_AANWEZIG.get(code, ())):
			return True
		for _, totaal, onderdelen in OPBOUW + BEWIJS_OPBOUW:
			if (
				code in [onderdeel.lstrip("-") for onderdeel in onderdelen]
				and self.regel_geldt(onderdelen)
				and self.is_bekend(totaal)
				and self.sluit_aan(totaal, onderdelen)
			):
				return True
		return False

	def ontbrekend(self, *codes):
		return [code for code in codes if not self.is_bekend(code)]

	def waarde(self, *codes):
		"""De som van de codes, of NaN als één ervan onbekend is."""
		return NIET_BESCHIKBAAR if self.ontbrekend(*codes) else self.bedrag(*codes)

	def per_jaar(self, *codes):
		"""Resultaatpost omgerekend naar 12 maanden."""
		return self.waarde(*codes) * 12 / self.maanden

	def memo(self, *codes):
		"""Bedragen uit de toelichting: alleen het volledige schema bewijst dat leeg 0 is."""
		if self.schema != "VOL" and not any(code in self.codes for code in codes):
			return NIET_BESCHIKBAAR
		return self.bedrag(*codes)


def lees_neerlegging(pad):
	"""Leest één NBB-CSV. Geeft een ValueError als het bestand niet klopt."""
	with pad.open(encoding="utf-8-sig", newline="") as bestand:
		rijen = [rij for rij in csv.reader(bestand) if rij]
	if any(len(rij) != 2 for rij in rijen):
		raise ValueError(f"{pad.name}: verwacht twee kolommen per rij.")
	velden = dict(rijen)

	codes = {}
	for sleutel, waarde in velden.items():
		if sleutel[0].isdigit():
			try:
				codes[sleutel] = float(waarde)
			except ValueError:
				raise ValueError(f"{pad.name}: code {sleutel} heeft geen geldig bedrag: {waarde!r}") from None

	try:
		return Neerlegging(
			bestand=pad.name,
			ondernemingsnummer=velden["Entity number"],
			naam=velden["Entity name"],
			begin=date.fromisoformat(velden["Accounting period start date"]),
			einde=date.fromisoformat(velden["Accounting period end date"]),
			referentie=velden["Reference number"],
			valuta=velden["Currency"],
			vereffening=velden.get("Liquidation flag", "FALSE") == "TRUE",
			correctie=velden.get("Correction flag", "FALSE") == "TRUE",
			codes=codes,
			model=velden.get("Model code", ""),
		)
	except KeyError as fout:
		raise ValueError(f"{pad.name}: geen NBB-CSV, veld {fout} ontbreekt.") from None


def groepeer_per_bedrijf(neerleggingen):
	"""Geeft per bedrijf een lijst van oud naar recent, met één neerlegging per boekjaar."""
	bedrijven = {}
	for neerlegging in neerleggingen:
		jaren = bedrijven.setdefault(neerlegging.ondernemingsnummer, {})
		bestaande = jaren.get(neerlegging.einde)
		# Bij een verbeterde neerlegging telt de recentste referentie
		if bestaande is None or neerlegging.referentie > bestaande.referentie:
			jaren[neerlegging.einde] = neerlegging
	return [[jaren[einde] for einde in sorted(jaren)] for jaren in bedrijven.values()]


def _controleer(neerlegging):
	"""Rekent de neerlegging na op haar eigen totalen. Geeft een lijst met fouten."""
	fouten = [labels.ERROR_CODE_MISSING.format(code=code) for code in VERPLICHTE_CODES if code not in neerlegging.codes]
	if neerlegging.valuta != "EUR":
		fouten.append(labels.ERROR_CURRENCY.format(currency=neerlegging.valuta))

	for naam, totaal, onderdelen in OPBOUW:
		if totaal in neerlegging.codes and neerlegging.regel_geldt(onderdelen):
			if not neerlegging.sluit_aan(totaal, onderdelen):
				verschil = neerlegging.bedrag(totaal) - neerlegging.bedrag(*onderdelen)
				fouten.append(labels.ERROR_RECONCILIATION.format(name=labels.RECONCILIATION_NAMES[naam], value=verschil))
	return fouten


def _signalen(neerlegging):
	"""Feiten uit de neerlegging die een analist moet zien, maar geen rekenfout zijn."""
	signalen = []
	if neerlegging.maanden != 12:
		signalen.append(labels.SIGNAL_MONTHS.format(year=neerlegging.boekjaar, months=neerlegging.maanden))
	if neerlegging.vereffening:
		signalen.append(labels.FLAG_LIQUIDATION)
	if neerlegging.correctie:
		signalen.append(labels.SIGNAL_CORRECTED.format(year=neerlegging.boekjaar))
	if "9077" in neerlegging.codes and not neerlegging.sluit_aan("454/9", ("9076", "9077")):
		verschil = neerlegging.bedrag("454/9") - neerlegging.bedrag("9076", "9077")
		signalen.append(labels.SIGNAL_SOCIAL_DEBT.format(year=neerlegging.boekjaar, value=verschil))
	return signalen


def _aansluitende_jaren(neerleggingen):
	"""De recentste boekjaren zonder gat ertussen, maximaal config.LBO_MAX_JAREN."""
	reeks = [neerleggingen[-1]]
	for jaar in reversed(neerleggingen[:-1]):
		if len(reeks) == config.LBO_MAX_JAREN or jaar.einde + timedelta(days=1) != reeks[0].begin:
			break
		reeks.insert(0, jaar)
	return reeks


def _vergelijkbaar_vorig_jaar(neerleggingen):
	"""Vorig jaar telt alleen als het boekjaar direct aansluit op het huidige."""
	if len(neerleggingen) < 2:
		return None
	huidig, vorig = neerleggingen[-1], neerleggingen[-2]
	return vorig if vorig.einde + timedelta(days=1) == huidig.begin else None


def _omzet_code(neerlegging):
	"""Bij een verkort of micro-schema is de omzet niet openbaar: dan brutomarge."""
	return "70" if "70" in neerlegging.codes else "9900"


def _brutomarge(neerlegging):
	"""Code 9900, of dezelfde berekening bij een volledig schema: zo is elke marge vergelijkbaar."""
	if "9900" in neerlegging.codes:
		return neerlegging.per_jaar("9900")
	if "70/76A" in neerlegging.codes:
		return neerlegging.per_jaar("70/76A") - neerlegging.per_jaar("60", "61")
	return NIET_BESCHIKBAAR


def _capex_uit_staat(neerlegging, totaal, categorieen, staat, rubriek):
	"""Aanschaffingen van één staat, of NaN als de staat ontbreekt terwijl er activa zijn."""
	if totaal in neerlegging.codes:
		return neerlegging.codes[totaal]
	# Staat aanwezig: lege aanschaffingen zijn echt 0. Geen activa: dan is er ook geen staat nodig.
	staat_aanwezig = any(code.startswith(staat) for code in neerlegging.codes)
	geen_activa = neerlegging.is_bekend(rubriek) and neerlegging.bedrag(rubriek) == 0
	if staat_aanwezig or geen_activa:
		return neerlegging.bedrag(*categorieen)
	return NIET_BESCHIKBAAR


def _capex(neerlegging):
	"""Aanschaffingen van materiële en immateriële vaste activa, inclusief leasing, per 12 maanden."""
	return sum(_capex_uit_staat(neerlegging, *staat) for staat in CAPEX_STATEN) * 12 / neerlegging.maanden


def _gemiddelde_capex(neerleggingen):
	"""Capex schommelt per jaar: het LBO-model rekent met het gemiddelde van de bekende jaren."""
	reeks = [_capex(jaar) for jaar in neerleggingen]
	bekend = [capex for capex in reeks if not math.isnan(capex)]
	if math.isnan(reeks[-1]):
		return NIET_BESCHIKBAAR, 0
	return sum(bekend) / len(bekend), len(bekend)


def _normalisatie(neerlegging):
	"""Positief voor eenmalige kosten (terugtellen), negatief voor eenmalige opbrengsten."""
	return neerlegging.per_jaar("66A") - neerlegging.per_jaar("76A")


def _normalisatie_toelichting(neerlegging):
	if neerlegging.ontbrekend("66A", "76A"):
		return labels.ADJUSTMENTS_UNAVAILABLE
	return labels.ADJUSTMENTS_NOTE.format(expenses=neerlegging.bedrag("66A"), income=neerlegging.bedrag("76A"))


def _liquide_middelen(neerlegging):
	"""Eigen aandelen (code 50) staan bij de geldbeleggingen, maar zijn geen cash."""
	return neerlegging.waarde(*LIQUIDE_CODES) - neerlegging.bedrag("50")


def _vaste_activa(neerlegging):
	"""Oprichtingskosten, immateriële en materiële vaste activa: de basis voor D&A en capex."""
	return neerlegging.waarde("20", "21", "22/27")


def _dagen(saldo, jaarbedrag):
	return saldo / jaarbedrag * 365 if jaarbedrag > 0 else NIET_BESCHIKBAAR


def _werkkapitaal_dagen(neerlegging, omzet_code):
	"""DSO, DIO en DPO. Zonder aankopen (verkort schema) is de omzetbasis de noemer."""
	basis = neerlegging.per_jaar(omzet_code)
	kosten_60 = neerlegging.per_jaar("60") if neerlegging.codes.get("60", 0) > 0 else basis
	kosten_6061 = neerlegging.per_jaar("60", "61") if neerlegging.bedrag("60", "61") > 0 else basis
	return {
		"DSO": _dagen(neerlegging.waarde("40"), basis),
		"DIO": _dagen(neerlegging.waarde("3"), kosten_60),
		"DPO": _dagen(neerlegging.waarde("44"), kosten_6061),
		"Kosten_60": kosten_60,
		"Kosten_6061": kosten_6061,
	}


def _historische_cagr(reeks, basis):
	"""Jaarlijkse groei tussen het eerste bekende en het laatste boekjaar, of None zonder historiek."""
	if len(reeks) < 2 or basis[-1] <= 0:
		return None
	for jaar, bedrag in zip(reeks[:-1], basis[:-1]):
		if bedrag > 0:
			jaren = (reeks[-1].einde - jaar.einde).days / 365.25
			return (basis[-1] / bedrag) ** (1 / jaren) - 1
	return None


def _of_nul(waarde):
	return 0.0 if math.isnan(waarde) else waarde


def _inkoop(neerlegging, omzet_code):
	"""Aankopen (60/61). Op een brutomargebasis zijn die al afgetrokken: dan is er geen inkooplijn."""
	return 0.0 if omzet_code == "9900" else neerlegging.per_jaar("60", "61")


def _genormaliseerde_ebitda(neerlegging):
	return neerlegging.per_jaar(*EBITDA_CODES) + _normalisatie(neerlegging)


def _overige_kosten(neerlegging, omzet_code):
	"""Alles tussen omzet en EBITDA buiten inkoop en personeel, netto na overige opbrengsten (74)."""
	return (
		neerlegging.per_jaar(omzet_code)
		- _inkoop(neerlegging, omzet_code)
		- neerlegging.per_jaar("62")
		- _genormaliseerde_ebitda(neerlegging)
	)


def _doelratio(ratios):
	"""Hoogste van gemiddelde en laatste jaar: een gedaalde kostenratio wordt niet als blijvend gezien."""
	ratios = [ratio for ratio in ratios if not math.isnan(ratio)]
	return max(sum(ratios) / len(ratios), ratios[-1]) if ratios else NIET_BESCHIKBAAR


def _balansregels(neerlegging):
	"""De balans in de lijnen van het model. Actief en passief sluiten op het balanstotaal."""
	liquide = neerlegging.waarde(*LIQUIDE_CODES)
	debt_like = neerlegging.waarde("16", "450", "9072", "9076", "178/9", "47/48")
	overige_activa = (
		neerlegging.waarde("20/58") - _vaste_activa(neerlegging) - neerlegging.waarde("28", "3", "40") - liquide
	)
	overige_passiva = (
		neerlegging.waarde("10/49") - neerlegging.waarde("10/15", "170/4", "42", "43", "44", "46") - debt_like
	)
	# Groepsvorderingen en vorderingen op bestuurders zijn geen werkkapitaal: ze groeien niet mee met de omzet
	niet_operationeel = _of_nul(neerlegging.memo("9291")) + _of_nul(neerlegging.memo("9500"))
	niet_operationeel = min(niet_operationeel, neerlegging.bedrag("41"), max(overige_activa, 0.0))
	# Vervallen sociale schulden (9076) zitten bij de debt-like items
	sociaal = _of_nul(neerlegging.waarde("454/9")) - neerlegging.bedrag("9076")
	sociaal = min(max(sociaal, 0.0), max(overige_passiva, 0.0))
	return {
		"overige_activa": overige_activa,
		"niet_operationeel": niet_operationeel,
		"overige_passiva": overige_passiva,
		"sociaal": sociaal,
		"debt_like": debt_like,
	}


def _bereken_drivers(reeks, omzet_code):
	"""De aannames van het 3-statement model, afgeleid uit de boekjaren zelf."""
	huidig = reeks[-1]
	basis = [jaar.per_jaar(omzet_code) for jaar in reeks]

	cagr = _historische_cagr(reeks, basis)
	groei = config.LBO_GROEI_STANDAARD if cagr is None else cagr
	groei = min(max(groei, config.LBO_GROEI_MIN), config.LBO_GROEI_MAX)

	# Referentie voor de analist: de EBITDA in de forecast is een resultaat van de kostenlijnen.
	marges = [
		(jaar.per_jaar(*EBITDA_CODES) + _normalisatie(jaar)) / omzet
		for jaar, omzet in zip(reeks, basis)
		if omzet > 0
	]
	marges = [marge for marge in marges if not math.isnan(marge)]
	marge = min(sum(marges) / len(marges), marges[-1]) if marges else NIET_BESCHIKBAAR
	ebitda_cagr = _historische_cagr(reeks, [jaar.per_jaar(*EBITDA_CODES) + _normalisatie(jaar) for jaar in reeks])

	# D&A op de openingswaarde van de vaste activa. Met één boekjaar: op de eindwaarde.
	da_ratios = [
		jaar.per_jaar("630") / _vaste_activa(vorig)
		for vorig, jaar in zip(reeks[:-1], reeks[1:])
		if _vaste_activa(vorig) > 0
	]
	if not da_ratios and _vaste_activa(huidig) > 0:
		da_ratios = [huidig.per_jaar("630") / _vaste_activa(huidig)]
	da_ratios = [ratio for ratio in da_ratios if not math.isnan(ratio)]
	da_pct = min(sum(da_ratios) / len(da_ratios), 1.0) if da_ratios else 0.0

	capex_ratios = [capex / omzet for capex, omzet in zip(map(_capex, reeks), basis) if omzet > 0]
	capex_ratios = [ratio for ratio in capex_ratios if not math.isnan(ratio)]

	inkoop_ratios = [_inkoop(jaar, omzet_code) / omzet for jaar, omzet in zip(reeks, basis) if omzet > 0]
	overige_ratios = [_overige_kosten(jaar, omzet_code) / omzet for jaar, omzet in zip(reeks, basis) if omzet > 0]

	dagen = _werkkapitaal_dagen(huidig, omzet_code)
	omzet = huidig.per_jaar(omzet_code)

	return {
		"Driver_Aantal_Jaren": len(reeks),
		"Driver_Historische_CAGR_Pct": cagr * 100 if cagr is not None else NIET_BESCHIKBAAR,
		"Driver_Omzetgroei_Pct": groei * 100,
		"Driver_EBITDA_CAGR_Pct": ebitda_cagr * 100 if ebitda_cagr is not None else NIET_BESCHIKBAAR,
		"Driver_EBITDA_Marge_Gemiddeld_Pct": sum(marges) / len(marges) * 100 if marges else NIET_BESCHIKBAAR,
		"Driver_EBITDA_Marge_Pct": marge * 100,
		"Driver_Inkoop_Pct": _doelratio(inkoop_ratios) * 100,
		"Driver_Overige_Kosten_Pct": _doelratio(overige_ratios) * 100,
		"Driver_DA_Pct_Vaste_Activa": da_pct * 100,
		"Driver_Capex_Pct": (
			sum(capex_ratios) / len(capex_ratios) * 100 if capex_ratios else NIET_BESCHIKBAAR
		),
		"Driver_DSO": dagen["DSO"],
		"Driver_DIO": dagen["DIO"],
		"Driver_DPO": dagen["DPO"],
		"Driver_Dagen_Vooruitbetaling": _dagen(huidig.waarde("46"), omzet),
		"Driver_Kosten_60_Pct": dagen["Kosten_60"] / omzet * 100 if omzet > 0 else NIET_BESCHIKBAAR,
		"Driver_Kosten_6061_Pct": dagen["Kosten_6061"] / omzet * 100 if omzet > 0 else NIET_BESCHIKBAAR,
	}


def _openingsposten(huidig):
	"""Balansposten die het model niet afzonderlijk voorspelt: die blijven constant."""
	regels = _balansregels(huidig)
	return {
		"Open_Vaste_Activa": _vaste_activa(huidig),
		"Open_Financiele_Vaste_Activa": huidig.waarde("28"),
		"Open_Overige_Activa_Operationeel": regels["overige_activa"] - regels["niet_operationeel"],
		"Open_Overige_Activa_Niet_Operationeel": regels["niet_operationeel"],
		"Open_Sociale_Schulden": regels["sociaal"],
		"Open_Overige_Passiva": regels["overige_passiva"] - regels["sociaal"],
	}


def _data_volledigheid(huidig, vorig, omzet_code, aantal_jaren):
	"""'Onvoldoende' blokkeert het LBO-oordeel, 'Gedeeltelijk' alleen een sterke kwalificatie."""
	kerncodes = [
		code
		for velden in (RESULTAATVELDEN, BALANSVELDEN)
		for codes in velden.values()
		for code in codes
	]
	ontbrekend = huidig.ontbrekend(omzet_code, "66A", "76A", *LIQUIDE_CODES, *kerncodes)
	if math.isnan(_capex(huidig)):
		ontbrekend.append(labels.COMPLETENESS_CAPEX)
	if ontbrekend:
		return labels.data_insufficient(labels.COMPLETENESS_NO_DATA.format(codes=", ".join(ontbrekend)))
	if vorig is None:
		return labels.data_partial(labels.COMPLETENESS_NO_PRIOR)
	ontbrekend_vorig = vorig.ontbrekend(omzet_code, *EBITDA_CODES)
	if ontbrekend_vorig:
		return labels.data_partial(labels.COMPLETENESS_PRIOR_CODES.format(codes=", ".join(ontbrekend_vorig)))
	if aantal_jaren < config.LBO_MIN_JAREN:
		return labels.data_partial(labels.COMPLETENESS_FEW_YEARS.format(years=aantal_jaren, minimum=config.LBO_MIN_JAREN))
	return labels.DATA_COMPLETE


def _opmaak_nummer(nummer):
	return f"{nummer[:4]}.{nummer[4:7]}.{nummer[7:]}" if len(nummer) == 10 else nummer


def bouw_cijfers(neerleggingen):
	"""Zet de neerleggingen van één bedrijf (oud naar recent) om in de cijfers voor de LBO-analyse."""
	huidig = neerleggingen[-1]
	vorig = _vergelijkbaar_vorig_jaar(neerleggingen)

	signalen = _signalen(huidig)
	if vorig is None:
		signalen.append(labels.SIGNAL_NO_PRIOR_YEAR.format(year=huidig.boekjaar))
	else:
		signalen.extend(_signalen(vorig))

	omzet_code = _omzet_code(huidig)
	reeks = _aansluitende_jaren(neerleggingen)
	fouten = [fout for jaar in reeks for fout in _controleer(jaar)]
	capex_gemiddeld, capex_jaren = _gemiddelde_capex(reeks)

	return {
		"Bedrijfsnaam": huidig.naam,
		"Ondernemingsnummer": _opmaak_nummer(huidig.ondernemingsnummer),
		"Boekjaar": huidig.boekjaar,
		"Boekjaar_Begin": huidig.begin.isoformat(),
		"Boekjaar_Einde": huidig.einde.isoformat(),
		"Boekjaar_Maanden": huidig.maanden,
		"Boekjaar_Maanden_Vorig_Jaar": vorig.maanden if vorig else NIET_BESCHIKBAAR,
		"Schema_Type": huidig.schema,
		"Omzet_Basis": labels.BASIS_REVENUE if omzet_code == "70" else labels.BASIS_GROSS_MARGIN,
		"Omzet_of_Brutomarge": huidig.per_jaar(omzet_code),
		"Omzet_of_Brutomarge_Vorig_Jaar": vorig.per_jaar(omzet_code) if vorig else NIET_BESCHIKBAAR,
		"Brutomarge": _brutomarge(huidig),
		"Brutomarge_Vorig_Jaar": _brutomarge(vorig) if vorig else NIET_BESCHIKBAAR,
		"Bedrijfswinst_EBIT_Vorig_Jaar": vorig.per_jaar("9901") if vorig else NIET_BESCHIKBAAR,
		"Afschrijvingen_Vorig_Jaar": vorig.per_jaar("630") if vorig else NIET_BESCHIKBAAR,
		"Voorzieningen_Mutatie_Vorig_Jaar": vorig.per_jaar("635/8") if vorig else NIET_BESCHIKBAAR,
		"Waardeverminderingen_Vlottend": huidig.per_jaar("631/4"),
		"Waardeverminderingen_Vlottend_Vorig_Jaar": vorig.per_jaar("631/4") if vorig else NIET_BESCHIKBAAR,
		"Inkoop": _inkoop(huidig, omzet_code),
		"VTE": huidig.codes.get("9087", huidig.codes.get("1003", NIET_BESCHIKBAAR)),
		"Capex_Laatste_Jaar": _capex(huidig),
		"Capex_Gemiddeld": capex_gemiddeld,
		"Capex_Aantal_Jaren": capex_jaren,
		"Normalisatie_Bedrag": _normalisatie(huidig),
		"Normalisatie_Toelichting": _normalisatie_toelichting(huidig),
		**{veld: huidig.per_jaar(*codes) for veld, codes in RESULTAATVELDEN.items()},
		**{veld: huidig.waarde(*codes) for veld, codes in BALANSVELDEN.items()},
		"Liquide_Middelen": _liquide_middelen(huidig),
		"Eigen_Aandelen": huidig.bedrag("50"),
		"Balanstotaal": huidig.waarde("20/58"),
		"Overgedragen_Resultaat": huidig.bedrag("14"),
		"Memo_Sociale_Schulden": huidig.waarde("454/9"),
		"Memo_Zekerheden_Derden": huidig.memo("9149", "9381"),
		"Memo_Vorderingen_Bestuurders": huidig.memo("9500"),
		"Memo_Vorderingen_Verbonden": huidig.memo("9291"),
		**_bereken_drivers(reeks, omzet_code),
		**_openingsposten(huidig),
		"Data_Volledigheid": _data_volledigheid(huidig, vorig, omzet_code, len(reeks)),
		"Check_Data": labels.CHECK_OK if not fouten else labels.check_review(fouten),
		"Cijfer_Flags": "; ".join(signalen),
		"Bronbestand": huidig.bestand,
	}


def _modelregels(jaar, vorig, omzet_code):
	"""Eén boekjaar in dezelfde lijnen als de forecast, zodat elke aanname te toetsen is aan de historiek."""
	omzet = jaar.per_jaar(omzet_code)
	inkoop = _inkoop(jaar, omzet_code)
	personeel = jaar.per_jaar("62")
	overige = _overige_kosten(jaar, omzet_code)
	ebitda = _genormaliseerde_ebitda(jaar)
	afschrijvingen = jaar.per_jaar("630")
	ebit = jaar.per_jaar("9901")
	factor = 12 / jaar.maanden
	winst_voor_belasting = jaar.codes.get("9903", NIET_BESCHIKBAAR) * factor
	nettowinst = jaar.codes.get("9904", NIET_BESCHIKBAAR) * factor
	vte = jaar.codes.get("9087", jaar.codes.get("1003", NIET_BESCHIKBAAR))
	dagen = _werkkapitaal_dagen(jaar, omzet_code)
	regels = _balansregels(jaar)

	def pct(waarde):
		return waarde / omzet * 100 if omzet > 0 else NIET_BESCHIKBAAR

	return {
		"Label": labels.actual_label(jaar.boekjaar),
		"Omzet": omzet,
		"Omzetgroei_Pct": (
			(omzet / vorig.per_jaar(omzet_code) - 1) * 100
			if vorig is not None and vorig.per_jaar(omzet_code) > 0
			else NIET_BESCHIKBAAR
		),
		"Inkoop": inkoop,
		"Personeel": personeel,
		"Overige_Kosten": overige,
		"EBITDA": ebitda,
		"Afschrijvingen": afschrijvingen,
		"Niet_Recurrent": ebitda - afschrijvingen - ebit,
		"EBIT": ebit,
		"Financieel_Resultaat": winst_voor_belasting - ebit,
		"Winst_Voor_Belasting": winst_voor_belasting,
		"Belasting": winst_voor_belasting - nettowinst,
		"Nettowinst": nettowinst,
		"Capex": _capex(jaar),
		"VTE": vte,
		"Kost_Per_VTE": personeel / vte if vte > 0 else NIET_BESCHIKBAAR,
		"Inkoop_Pct": pct(inkoop),
		"Personeel_Pct": pct(personeel),
		"Overige_Pct": pct(overige),
		"EBITDA_Marge_Pct": pct(ebitda),
		"Capex_Pct": pct(_capex(jaar)),
		"DA_Pct": (
			afschrijvingen / _vaste_activa(vorig) * 100
			if vorig is not None and _vaste_activa(vorig) > 0
			else NIET_BESCHIKBAAR
		),
		"Cash_Conversion_Pct": (ebitda - _capex(jaar)) / ebitda * 100 if ebitda > 0 else NIET_BESCHIKBAAR,
		"DSO": dagen["DSO"],
		"DIO": dagen["DIO"],
		"DPO": dagen["DPO"],
		"Advance_Days": _dagen(jaar.waarde("46"), omzet),
		"Vaste_Activa": _vaste_activa(jaar),
		"Financiele_Vaste_Activa": jaar.waarde("28"),
		"Voorraden": jaar.waarde("3"),
		"Handelsvorderingen": jaar.waarde("40"),
		"Overige_Activa_Operationeel": regels["overige_activa"] - regels["niet_operationeel"],
		"Overige_Activa_Niet_Operationeel": regels["niet_operationeel"],
		"Cash": jaar.waarde(*LIQUIDE_CODES),
		"Totaal_Activa": jaar.waarde("20/58"),
		"Eigen_Vermogen": jaar.waarde("10/15"),
		"Senior_Lening": jaar.waarde("170/4", "42", "43"),
		"Handelsschulden": jaar.waarde("44"),
		"Vooruitbetalingen": jaar.waarde("46"),
		"Sociale_Schulden": regels["sociaal"],
		"Overige_Passiva": regels["overige_passiva"] - regels["sociaal"] + regels["debt_like"],
		"Totaal_Passiva": jaar.waarde("10/49"),
	}


def bouw_driver_pack(neerleggingen):
	"""The historical ratios per fiscal year for Gemini: fixed facts, not proposals."""
	reeks = _aansluitende_jaren(neerleggingen)
	omzet_code = _omzet_code(neerleggingen[-1])
	velden = (
		"Omzetgroei_Pct", "Inkoop_Pct", "Personeel_Pct", "Overige_Pct", "EBITDA_Marge_Pct", "VTE", "Kost_Per_VTE",
		"Capex_Pct", "DA_Pct", "DSO", "DIO", "DPO", "Advance_Days", "Cash_Conversion_Pct",
	)
	jaren = []
	for index, jaar in enumerate(reeks):
		regels = _modelregels(jaar, reeks[index - 1] if index else None, omzet_code)
		cijfers = {veld: regels[veld] for veld in velden}
		jaren.append(
			{
				"Fiscal_Year": jaar.boekjaar,
				**{veld: None if isinstance(waarde, float) and math.isnan(waarde) else waarde for veld, waarde in cijfers.items()},
			}
		)
	return {
		"Company": neerleggingen[-1].naam,
		"Omzet_Basis": labels.BASIS_REVENUE if omzet_code == "70" else labels.BASIS_GROSS_MARGIN,
		"Fiscal_Years": jaren,
	}


def bouw_meerjaren(neerleggingen):
	"""Eén rij per boekjaar (oud naar recent) voor de meerjarentab van de bedrijfsfiche."""
	omzet_code = _omzet_code(neerleggingen[-1])
	rijen = []
	for index, jaar in enumerate(neerleggingen):
		omzet = jaar.per_jaar(omzet_code)
		brutomarge = _brutomarge(jaar)
		ebitda = jaar.per_jaar(*EBITDA_CODES)
		genormaliseerd = ebitda + _normalisatie(jaar)
		schuld = jaar.waarde("170/4", "42", "43")
		liquide = _liquide_middelen(jaar)
		dagen = _werkkapitaal_dagen(jaar, omzet_code)
		rijen.append(
			{
				"Boekjaar": jaar.boekjaar,
				"Maanden": jaar.maanden,
				"Omzet": omzet,
				"Brutomarge": brutomarge,
				"EBIT": jaar.per_jaar("9901"),
				"Afschrijvingen": jaar.per_jaar("630"),
				"Voorzieningen": jaar.per_jaar("635/8"),
				"EBITDA": ebitda,
				"Normalisatie": _normalisatie(jaar),
				"Genormaliseerde_EBITDA": genormaliseerd,
				"Genorm_Marge_Pct": round(genormaliseerd / omzet * 100, 2) if omzet > 0 else NIET_BESCHIKBAAR,
				"Marge_Op_Brutomarge_Pct": (
					round(genormaliseerd / brutomarge * 100, 2) if brutomarge > 0 else NIET_BESCHIKBAAR
				),
				"Waardeverminderingen": jaar.per_jaar("631/4"),
				"Capex": _capex(jaar),
				"DSO": dagen["DSO"],
				"DIO": dagen["DIO"],
				"DPO": dagen["DPO"],
				"Financiele_Schuld": schuld,
				"Liquide_Middelen": liquide,
				"Net_Debt": schuld - liquide,
				"Eigen_Vermogen": jaar.waarde("10/15"),
				"Balanstotaal": jaar.waarde("20/58"),
				"VTE": jaar.codes.get("9087", jaar.codes.get("1003")),
				"Model": _modelregels(jaar, neerleggingen[index - 1] if index else None, omzet_code),
			}
		)
	return rijen
