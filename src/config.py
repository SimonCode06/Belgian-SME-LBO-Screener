"""Centrale configuratie: paden, instellingen, LBO-parameters, systeemprompt en API-sleutel.

Pas hier de knoppen aan (multiples, rentevoet, groeivoet, modellen, timeouts) —
de andere modules lezen alles uit dit bestand, zodat je nooit in meerdere
bestanden tegelijk hoeft te zoeken.
"""
import os
from pathlib import Path

# ============================================================================
# Paden (project-root = één niveau boven deze src/-map)
# ============================================================================
BASIS_MAP = Path(__file__).resolve().parent.parent
INPUT_FOLDER = BASIS_MAP / "input_pdfs"  # NBB-CSV's (cijfers) en NBB-PDF's (tekst)
CACHE_FOLDER = BASIS_MAP / "cache_json"
OUTPUT_FOLDER = BASIS_MAP / "output"

# ============================================================================
# LBO- & Trend-parameters (Fase 1 t/m 4)
# ============================================================================
# Multiples hangen af van de grootte: een KMO met € 300k EBITDA krijgt geen 6x.
# (EBITDA tot, instapmultiple EV/EBITDA, senior schuld/EBITDA). Exit = instap: geen multiple expansion.
# Dit zijn aannames: vervang ze door je eigen marktdata. Sectoren ontbreken omdat de NACE-code
# niet in de CSV of PDF staat.
LBO_MULTIPLE_TABEL = [
	(500_000, 4.0, 1.5),
	(1_000_000, 4.5, 2.0),
	(2_500_000, 5.0, 2.5),
	(5_000_000, 6.0, 3.0),
	(float("inf"), 7.0, 3.5),
]
LBO_MIN_EBITDA = 250_000         # Daaronder is een LBO niet realistisch

# Financiering
LBO_SENIOR_RENTE = 0.065         # Rente op de amortiserende senior lening (6,5% p.j.)
LBO_SENIOR_LOOPTIJD_JAAR = 7     # Lineaire aflossing van de senior lening
LBO_CASH_SWEEP_PCT = 0.50        # Deel van de excess cash flow van het jaar dat extra aflost op de senior lening
LBO_VENDOR_LOAN_PCT_EV = 0.10    # Vendor loan als deel van de EV, in één keer terugbetaald bij exit
LBO_VENDOR_LOAN_RENTE = 0.08     # Rente op de vendor loan, jaarlijks in cash betaald
LBO_RCF_LIMIET_X_EBITDA = 0.5    # Limiet van de RCF: vast bedrag bij closing, als veelvoud van de EBITDA (bij closing niet getrokken)
LBO_RCF_RENTE = 0.065            # Rente op het getrokken deel, zoals de senior lening
LBO_RCF_COMMITMENT_FEE = 0.01    # Jaarlijkse vergoeding op het niet-getrokken deel van de limiet
LBO_TRANSACTIEKOSTEN_PCT = 0.03  # Advies, due diligence en notaris als deel van de EV
LBO_FINANCIERINGSKOSTEN_PCT = 0.01  # Bankkosten als deel van de EV

# Rente. Op het gemiddelde saldo ontstaat een kringverwijzing (rente -> kasstroom -> aflossing -> saldo),
# die Python oplost met iteraties. "begin" rekent op het beginsaldo, zonder kringverwijzing.
LBO_RENTE_BASIS = "gemiddeld"    # "gemiddeld" of "begin"
LBO_RENTE_ITERATIES = 10         # Iteraties bij een gemiddeld saldo
LBO_CASH_RENTE = 0.015           # Interestopbrengst op de cash

# Closing en exit. None: closing op de laatste balansdatum, zonder stub. Een datum ("2026-06-30") geeft een
# stub tot het volgende boekjaareinde; de exit valt op het boekjaareinde het dichtst bij de holding period.
# De openingsbalans blijft de laatste jaarrekening: het model rolt de balans niet door tot de closing.
LBO_CLOSING_DATUM = None

# Boekhoudkundige afschrijvingen (niet-kaskosten)
LBO_GOODWILL_LOOPTIJD_JAAR = 10  # Belgische norm: 5 jaar, langer mits motivering. Fiscaal niet aftrekbaar
LBO_CAPEX_LEVENSDUUR_JAAR = 5    # Lineaire afschrijving per capex-vintage, vanaf het jaar van aankoop

# Dividend: deel van de vrije cash na de sweep, alleen zonder RCF-trekking en binnen de uitkeerbare reserves
LBO_DIVIDEND_PCT = 0.0

# Kostenstructuur: deel van de volumegroei dat extra VTE vraagt. Onder 1 ontstaat operationele hefboom.
LBO_VTE_ELASTICITEIT = 0.75

# Scenario's. Base: de omzetgroei uit de drivers is de totale groei, volume is wat na de prijsgroei overblijft.
# volume_delta en inkoop_delta zijn afwijkingen op de base. De indexering volgt de wet en niet de klantprijs:
# de prijs moet ze dus terugverdienen, anders krimpt de marge.
LBO_SCENARIOS = {
	"base": {"label": "Base", "prijsgroei": 0.02, "volume_delta": 0.0, "indexering": 0.02, "inkoop_delta": 0.0},
	"downside": {"label": "Downside", "prijsgroei": 0.01, "volume_delta": -0.02, "indexering": 0.025, "inkoop_delta": 0.0025},
	"upside": {"label": "Upside", "prijsgroei": 0.025, "volume_delta": 0.01, "indexering": 0.02, "inkoop_delta": -0.0025},
}

# Net debt: één definitie per doel, berekend door lbo_model.net_debt en beschreven in de Excel.
# Financiële schuld is altijd senior + RCF + vendor loan.
NET_DEBT_DEFINITIES = {
	"bank_covenant": {
		"label": "bank-covenant",
		"gebruik": "Leverage-convenant in de forecast en Net Debt (standaard) van de doelonderneming",
		"alleen_cash_boven_minimum": False,
		"debt_like_meetellen": False,
	},
	"waardering": {
		# De debt-like items worden bij closing vereffend: in de forecast zijn ze 0
		"label": "waardering",
		"gebruik": "Adjusted Net Debt bij instap, exit equity en de doelstelling van 2,0x in jaar 5",
		"alleen_cash_boven_minimum": True,
		"debt_like_meetellen": True,
	},
}

# Convenanten: worden elk jaar getest
LBO_COVENANT_MIN_DSCR = 1.20     # (EBITDA - capex - belasting) / (rente + verplichte aflossing)
LBO_COVENANT_MIN_RENTEDEKKING = 3.0  # EBITDA / rente
LBO_COVENANT_MAX_LEVERAGE = 4.0  # Net Debt (definitie bank_covenant) / EBITDA

# Fiscaliteit
LBO_TAX_RATE = 0.25              # Belgische vennootschapsbelasting (25,0%)
LBO_KMO_TARIEF_TOEPASSEN = False # Standaard uit: de voorwaarden veranderen en een BidCo als aandeelhouder kan het tarief raken
LBO_KMO_TARIEF = 0.20            # Verlaagd tarief op de eerste schijf
LBO_KMO_SCHIJF = 100_000         # Eerste schijf van de winst
# De rente zit op BidCo. Groepsbijdrage vereist 5 jaar verbondenheid, dus in de praktijk pas
# aftrekbaar na een fusie van BidCo en OpCo. Dit is het eerste jaar waarin de rente aftrekbaar is.
LBO_RENTEAFTREK_VANAF_JAAR = 2
LBO_RENTEAFTREK_DREMPEL_EUR = 3_000_000  # Renteaftrekbeperking: de hoogste van deze drempel...
LBO_RENTEAFTREK_EBITDA_PCT = 0.30        # ...en 30% van de EBITDA

# Forecast
LBO_HOLDING_PERIOD_YEARS = 5     # Investeringshorizon van het PE-fonds (5 jaar)
LBO_MIN_JAREN = 3                # Minder boekjaren: drivers zijn zwak, dus geen sterke kandidaat
LBO_MAX_JAREN = 5                # Meer boekjaren gebruikt het model niet
LBO_GROEI_STANDAARD = 0.02       # Groei als er geen historiek is (één boekjaar)
LBO_GROEI_MIN = -0.05            # De historische CAGR wordt begrensd tussen dit minimum...
LBO_GROEI_MAX = 0.05             # ...en dit maximum: een piekjaar mag niet 5 jaar doorlopen
LBO_KOSTEN_GLIDE_JAREN = 3       # In zoveel jaren lopen de kostenratio's van het laatste boekjaar naar hun doelniveau
LBO_TARGET_END_LEVERAGE = 2.0    # Doeldrempel: schuld binnen 5 jaar onder 2,0x EBITDA
LBO_MIN_IRR_PCT = 15.0           # Minimale IRR voor een sterke kandidaat

# Screening
MAX_MARGE_DALING_PP = 2.0        # Red flag als EBITDA-marge meer dan 2,0 procentpunt daalt
CSV_TOLERANTIE_EUR = 5           # Toegestaan afrondingsverschil bij het narekenen van de CSV-totalen
# Minimum operationele cash: gebaseerd op kosten die in elk schema bestaan. Aankopen (60/61) ontbreken in
# verkorte en micro-schema's, dus die raming loopt via de handelsschulden (44) op de balans.
MIN_CASH_MAANDEN_PERSONEEL = 1   # Maanden loon en RSZ (code 62)
MIN_CASH_WEKEN_LEVERANCIERS = 2  # Weken leveranciersbetalingen
MIN_CASH_BETAALTERMIJN_DAGEN = 60  # Handelsschulden = aankopen van zoveel dagen (wettelijk maximum B2B)
MAX_GROEPSVORDERINGEN_PCT = 25.0 # Red flag als vorderingen op verbonden ondernemingen dit % van de balans overschrijden

# Modelcode in de CSV -> schema. Alleen codes die in echte neerleggingen zijn vastgesteld;
# andere modellen worden herkend aan hun rubrieken (zie Neerlegging.schema).
MODEL_SCHEMAS = {"m02": "VOL", "m82": "VOL", "m87": "MIC"}

# ============================================================================
# Gemini-instellingen
# ============================================================================
MODELLEN = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
MAX_POGINGEN_PER_MODEL = 5
MAX_WACHTTIJD_SEC = 60
REQUEST_TIMEOUT_MS = 180_000  # 3 minuten per request
PAUZE_TUSSEN_PDFS_SEC = 4
INLINE_LIMIET_BYTES = 15 * 1024 * 1024  # groter => via Files API uploaden
RETRYABLE_CODES = {429, 500, 502, 503, 504}

SYSTEEM_PROMPT = """
Je bent een ervaren Belgische M&A- en Private Equity-analist. Je krijgt een
NBB-jaarrekening als PDF en de cijfers uit de gestructureerde neerlegging.

Die cijfers zijn definitief. Haal geen bedragen opnieuw uit de financiële staten
en bereken geen EBITDA, schuld of ratio's. De waarde null betekent dat het cijfer
niet beschikbaar is: vul het niet zelf in. Jouw taak is alleen de tekst: de
toelichtingen, waarderingsregels, het verslag van de commissaris, het
jaarverslag en de buitenbalansverplichtingen.

Geef uitsluitend een geldig JSON-object terug met exact deze sleutels:
{
  "Ondernemingsnummer": "Ondernemingsnummer op de PDF, als 0xxx.xxx.xxx",
  "Boekjaar": "Jaartal van de einddatum van het boekjaar op de PDF",
  "Normalisatie_Voorstellen": "Mogelijke extra normalisaties",
  "Commissaris_Oordeel": "Exact één van: Zonder voorbehoud, Met voorbehoud, Onthoudend, Afkeurend, Geen commissaris, Onbekend",
  "Buitenbalans_Verplichtingen": "Verplichtingen die niet op de balans staan",
  "Red_Flags": "Aandachtspunten uit de tekst"
}

Instructies:
- Normalisatie_Voorstellen: dit zijn de typische KMO-normalisaties. Benoem per
  voorstel de post, het bedrag als dat in de PDF staat en de vindplaats (bijvoorbeeld
  de rubriek over bestuurders of verbonden partijen). Denk aan de bezoldiging of
  managementvergoeding van bestuurders ten opzichte van de markt, huur aan een
  vastgoedvehikel van de eigenaar, privékosten en eenmalige posten die niet in
  codes 66A en 76A staan. De codes 66A en 76A zijn al verwerkt: stel ze niet opnieuw
  voor. Schrijf 'Geen' als er niets is. Deze voorstellen worden niet automatisch
  in de EBITDA opgenomen; een analist beoordeelt ze.
- Commissaris_Oordeel: het type verklaring in het verslag van de commissaris.
  Een verklaring met een toelichting of benadrukking van een onzekerheid blijft
  'Zonder voorbehoud'. Schrijf 'Geen commissaris' als er geen verslag is.
- Buitenbalans_Verplichtingen: operationele leasing, huurverplichtingen,
  borgstellingen, waarborgen en andere posten uit de rubriek 'niet in de balans
  opgenomen rechten en verplichtingen', met bedrag. Schrijf 'Geen' als er niets is.
- Red_Flags: denk aan vorderingen op en transacties met verbonden partijen en
  bestuurders, een onzekere continuïteit, fusies of vereffening, geschillen en
  afhankelijkheid van klanten of personen.
- Noem alleen wat in de PDF staat. Verzin niets.
"""

VERWACHTE_SLEUTELS = [
	"Ondernemingsnummer",
	"Boekjaar",
	"Normalisatie_Voorstellen",
	"Commissaris_Oordeel",
	"Buitenbalans_Verplichtingen",
	"Red_Flags",
]

# Tweede pass: na de berekening licht Gemini de resultaten toe. Het oordeel staat al vast.
OORDEEL_PROMPT = """
Je bent een ervaren Belgische M&A- en Private Equity-analist. Het LBO-model is
doorgerekend en je krijgt de resultaten plus de bevindingen uit de jaarrekening.

Geef uitsluitend een geldig JSON-object terug met exact deze sleutel:
{
  "Kwalitatief_LBO_Oordeel": "Beknopte toelichting op het LBO-resultaat"
}

Instructies:
- LBO_Status is de conclusie van het model. Licht die toe: spreek ze niet tegen en
  vervang ze niet door een eigen conclusie.
- Verklaar het resultaat vanuit de gegevens: kasstroomstabiliteit, meerjarentrend,
  convenanten, leverage, gebruik van de RCF en rendement.
- Een kwalitatief bezwaar dat het model niet meet, benoem je als aandachtspunt.
- Gebruik alleen de gegeven cijfers. Bereken of schat er geen nieuwe. De waarde null
  betekent dat het cijfer niet beschikbaar is.
- Verzin niets.
"""

OORDEEL_SLEUTELS = ["Kwalitatief_LBO_Oordeel"]

OORDEEL_VELDEN = [
	"LBO_Status",
	"Data_Volledigheid",
	"Schema_Type",
	"Omzet_of_Brutomarge",
	"Omzetgroei_Pct",
	"Genormaliseerde_EBITDA",
	"Marge_Verandering_pp",
	"Driver_Omzetgroei_Pct",
	"Driver_EBITDA_Marge_Pct",
	"Instap_Multiple",
	"Indicatieve_EV",
	"Indicatieve_Equity_Value",
	"LBO_Sponsor_Equity_Instap",
	"LBO_Senior_Schuld",
	"LBO_Laagste_DSCR",
	"LBO_Laagste_Rentedekking",
	"LBO_Hoogste_Leverage",
	"LBO_Laagste_Cash",
	"LBO_RCF_Limiet",
	"LBO_RCF_Piek",
	"LBO_RCF_Eind",
	"LBO_Convenanten",
	"LBO_Eind_Net_Debt_to_EBITDA",
	"LBO_Schuld_Onder_2x_5J",
	"Indicatieve_MoIC",
	"Indicatieve_IRR_Pct",
	"LBO_Downside_IRR_Pct",
	"LBO_Downside_MoIC",
	"LBO_Downside_Convenanten",
	"LBO_Upside_IRR_Pct",
	"Commissaris_Oordeel",
	"Buitenbalans_Verplichtingen",
	"Normalisatie_Voorstellen",
	"Red_Flags",
]


def laad_api_key():
	"""Volgorde: omgevingsvariabele -> bestand 'api_key.txt' naast de projectroot."""
	for naam in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
		waarde = os.environ.get(naam, "").strip()
		if waarde:
			return waarde
	key_bestand = BASIS_MAP / "api_key.txt"
	if key_bestand.exists():
		waarde = key_bestand.read_text(encoding="utf-8").strip()
		if waarde:
			return waarde
	raise RuntimeError(
		"Geen API-sleutel gevonden. Doe één van deze twee:\n"
		'  1) PowerShell:  setx GEMINI_API_KEY "jouw_sleutel"  (daarna VS Code herstarten)\n'
		"  2) Maak een bestand 'api_key.txt' in de projectroot met enkel de sleutel erin."
	)
