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
# Vastgezette AI-assumpties per bedrijf en boekjaar. Een bestaande snapshot wordt altijd gebruikt;
# alleen 'python main.py --vernieuw-assumpties' vraagt een nieuwe set aan Gemini.
SNAPSHOT_FOLDER = BASIS_MAP / "assumpties"
RUNS_FOLDER = OUTPUT_FOLDER / "runs"

MODEL_VERSIE = "2.0"

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

# Rente. "begin" rekent op het openingssaldo, zonder kringverwijzing: dit is ook wat de Excel-formules doen.
# "gemiddeld" lost de kringverwijzing op met iteraties, maar sluit dan niet meer op de Excel.
LBO_RENTE_BASIS = "begin"        # "begin" of "gemiddeld"
LBO_RENTE_ITERATIES = 10         # Iteraties bij een gemiddeld saldo
LBO_CASH_RENTE = 0.015           # Interestopbrengst op de cash

# Closing en exit. None: closing op de laatste balansdatum, zonder stub. Een datum ("2026-06-30") geeft een
# stub tot het volgende boekjaareinde, gevolgd door volle boekjaren: altijd vijf periodes, jaar 1 t/m 5.
# Een datum later dan 12 maanden na de balansdatum wordt begrensd en krijgt een red flag.
# De openingsbalans blijft de laatste jaarrekening: het model rolt de balans niet door tot de closing.
LBO_CLOSING_DATUM = None

# Boekhoudkundige afschrijvingen (niet-kaskosten)
LBO_GOODWILL_LOOPTIJD_JAAR = 10  # Belgische norm: 5 jaar, langer mits motivering. Fiscaal niet aftrekbaar
LBO_CAPEX_LEVENSDUUR_JAAR = 5    # Lineaire afschrijving per capex-vintage, vanaf het jaar van aankoop

# Dividend: deel van de vrije cash na de sweep, alleen zonder RCF-trekking en binnen de uitkeerbare reserves
LBO_DIVIDEND_PCT = 0.0

# Kostenstructuur: deel van de volumegroei dat extra VTE vraagt. Onder 1 ontstaat operationele hefboom.
LBO_VTE_ELASTICITEIT = 0.75

# Mechanische scenario's: alleen voor de fallback (te weinig historiek of Gemini niet beschikbaar).
# Base: de omzetgroei uit de drivers is de totale groei, volume is wat na de prijsgroei overblijft.
# volume_delta en inkoop_delta zijn afwijkingen op de base.
LBO_SCENARIOS = {
	"base": {"label": "Base", "prijsgroei": 0.02, "volume_delta": 0.0, "indexering": 0.02, "inkoop_delta": 0.0},
	"downside": {"label": "Downside", "prijsgroei": 0.01, "volume_delta": -0.02, "indexering": 0.025, "inkoop_delta": 0.0025},
	"upside": {"label": "Upside", "prijsgroei": 0.025, "volume_delta": 0.01, "indexering": 0.02, "inkoop_delta": -0.0025},
}
# De drie scenario's hierboven vormen de 'Analyst case' (AI-voorstel of mechanische terugval).
# De screening case staat daar los van en wordt altijd berekend, ook als er AI-assumpties zijn:
# - screening_base: de mechanische drivers uit de jaarrekening (scenario 'base' hierboven)
# - screening_stress: dezelfde drivers met een vaste EBITDA-daling per jaar tegenover screening_base.
#   Zo krijgt elk bedrijf exact dezelfde stresstest en zijn bedrijven onderling vergelijkbaar.
LBO_SCREENING_SCENARIOS = {
	"screening_base": {"label": "Screening Base"},
	"screening_stress": {"label": "Screening Stress"},
}
LBO_STRESS_EBITDA_HAIRCUT = [0.20, 0.20, 0.15, 0.10, 0.10]  # EBITDA-daling in jaar 1 t/m 5

# Zachte vlaggen op de AI-assumpties: ze waarschuwen en corrigeren nooit
LBO_VLAG_OMZETGROEI = (-25.0, 25.0)   # Omzetgroei per jaar, in procentpunt
LBO_VLAG_EBITDA_MARGE = (0.0, 60.0)   # EBITDA-marge per jaar, in procentpunt
LBO_VLAG_MARGE_PP = 3.0               # Procentpunt buiten de historische min/max
LBO_VLAG_MARGE_DAGEN = 15.0           # Dagen buiten de historische min/max (DSO, DIO, DPO, vooruitbetalingen)
LBO_VLAG_DOWNSIDE_MIN_DEEL_BASE = 0.50 # AI-downside EBITDA jaar 5 onder dit deel van de AI-base: geen geloofwaardige tegenvaller
LBO_VLAG_EBITDA_CAGR_PP = 10.0        # AI-base EBITDA-CAGR meer dan zoveel pp boven de historische EBITDA-CAGR

# Net debt: één definitie per doel, berekend door lbo_model.net_debt en beschreven in de Excel.
# Financiële schuld is altijd senior + RCF + vendor loan.
NET_DEBT_DEFINITIES = {
	"bank_covenant": {
		"label": "Bank Covenant",
		"gebruik": "the leverage covenant in the forecast and the standard Net Debt of the target",
		"alleen_cash_boven_minimum": False,
		"debt_like_meetellen": False,
	},
	"waardering": {
		# De debt-like items worden bij closing vereffend: in de forecast zijn ze 0
		"label": "Valuation",
		"gebruik": "Adjusted Net Debt at entry, exit equity and the 2.0x target in year 5",
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
DAGEN_PER_JAAR = 365            # Basis van DSO, DIO, DPO en vooruitbetalingen
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
# Groepsvorderingen (9291) die in de overige vorderingen (41) zitten, bv. een cash pool:
# - "cash_like": vereffend vóór closing. De verkoper krijgt ze betaald (aftrek in de Adjusted Net Debt) en ze
#   verdwijnen uit de openingsbalans. Zo werkt een cash pool bij een carve-out.
# - "operationeel": ze blijven in de overige operationele activa en groeien mee met de omzet.
# - "buiten_waarde": ze blijven als niet-operationeel actief staan zonder waarde voor de verkoper (oud gedrag).
# Het deel van 9291 dat niet in 41 past, zit in de handelsvorderingen (40) en blijft werkkapitaal.
# Schulden aan verbonden ondernemingen (9351) worden niet apart debt-like gemaakt: ze zitten al in de
# financiële schulden (170/4, 42, 43), de handelsschulden (44) of de overige schulden (47/48, al debt-like).
INTERCOMPANY_BEHANDELING = "cash_like"

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

# Versies van de AI-input, onderdeel van elke cachesleutel. Verhoog PROMPT_VERSIE bij elke bewuste
# wijziging van een prompt en SCHEMA_VERSIE bij elke wijziging van het antwoordschema
# (assumpties.AssumptieAntwoord). Een pakketupdate (bv. pydantic) verandert de sleutel zo nooit.
PROMPT_VERSIE = "2026-11-b"
SCHEMA_VERSIE = 2

SYSTEEM_PROMPT = """
You are an experienced Belgian M&A and Private Equity analyst. You receive an NBB
annual report as a PDF and the figures from the structured filing. The PDF may be
in Dutch or French. Write every description in English; quotes stay in the language
of the PDF.

Those figures are final. Do not extract amounts from the financial statements again
and do not calculate EBITDA, debt or ratios. The value null means the figure is not
available: do not fill it in yourself. Your task is the text only: the notes, the
valuation rules, the statutory auditor's report, the annual report and the
off-balance-sheet commitments.

The answer follows a fixed JSON schema. For every item give the PDF page number (the
page of the PDF file, starting at 1) and a short literal quote of 5 to 25 words copied
exactly from that page. Python checks every quote against the PDF: an item whose
quote cannot be found is treated as unverified.

Fields:
- ondernemingsnummer, boekjaar: as printed on the PDF (0xxx.xxx.xxx and the year of the
  end date of the fiscal year).
- commissaris_oordeel: the type of opinion in the statutory auditor's report. An opinion
  with an emphasis of matter or a stated uncertainty remains 'Unqualified'. Use
  'No Statutory Auditor' if there is no report.
- normalisaties: the typical SME adjustments to EBITDA, one item each. Categories:
  bestuurdersvergoeding (director pay or management fees versus market level),
  huur_verbonden_partij (rent paid to a property vehicle of the owner), privekosten,
  eenmalig (non-recurring items outside codes 66A and 76A, which are already processed),
  subsidie, overig. richting: '+' if the item is added back to EBITDA, '-' if deducted.
  bedrag_eur: the amount if the PDF states it, else null. nbb_code: the NBB code of the
  amount if there is one (for example 9503 for director remuneration), else null. An
  empty list if there is nothing. These proposals are not added to EBITDA automatically.
- red_flags: points of attention from the text. Categories: governance, verbonden_partijen
  (receivables from and transactions with related parties and directors), going_concern,
  juridisch (disputes, conflicts of interest), klantconcentratie, personeel, overig.
  ernst: hoog (could stop a deal), middel (to price or protect in the SPA), laag (note).
- eigendom: who controls the company. type: zelfstandig, groepsdochter, pe_backed or
  onbekend; the parent company and its enterprise number if stated; consoliderend:
  whether the company is included in consolidated group accounts (ja, nee, onbekend).
- buitenbalans: operating leases, rental commitments, guarantees and other rights and
  commitments not on the balance sheet, with the amount if stated.
- Mention only what is in the PDF. Do not invent anything.
"""

ASSUMPTIE_PROMPT = """
You are an experienced Belgian M&A and Private Equity analyst building the operating
model of a leveraged buyout. You receive the annual report as a PDF and a driver pack
with the historical ratios per fiscal year. The driver pack is final: do not recalculate
it. The PDF may be in Dutch or French. Always answer in English.

Propose the forecast assumptions for the five fiscal years after the last filed year,
for three scenarios:
- base: the most likely case, grounded in the historical trend and the outlook in the PDF.
- downside: a credible setback a lender would underwrite, not a catastrophe.
- upside: a credible outperformance, not a best case.

Rules:
- Return one row for every combination of scenario and driver: 36 rows in total.
- Give exactly five values per row, for year 1 to 5, in the unit stated below.
- A scenario must be coherent: price growth, volume, wage indexation and cost ratios
  should tell one story for that scenario.
- Downside must be no better than Base, and Base no better than Upside, in the
  favourable direction of each driver.
- Belgian wages are indexed by law, also when customers refuse price increases.
- rationale: one or two sentences explaining the values, in English.
- source: the PDF page plus a short quote, for example: p. 12: "new contract signed".
  Write exactly "historical trend" if the value rests on the driver pack alone.
- confidence: low, medium or high.
- On a gross margin basis (Omzet_Basis in the driver pack) inkoop_pct must be 0 in every
  year, because purchases are already deducted from the revenue line.
- Use the Economics block of the driver pack. EBITDA_Sensitivity_Per_1pp_Cost_Pct is the
  share of EBITDA that one percentage point of revenue in costs takes away. A downside
  that removes more than half of the EBITDA is not a credible setback.
- business_model: one sentence on how the company earns its revenue (what it sells, to
  whom, how it is billed), from the PDF.
- Do not invent facts about the company.
"""

ASSUMPTIE_BRON_HISTORIEK = "historical trend"

# Citaatcontrole (citaten.py): een citaat telt als gevonden vanaf deze rapidfuzz-score (0-100)
CITAAT_MIN_SCORE = 90
CITAAT_MIN_LENGTE = 12          # Kortere citaten zijn te algemeen om iets te bewijzen
CITAAT_MIN_TEKST_TEKENS = 200   # Minder tekst in de hele PDF: gescand, dus niet controleerbaar

# De sleutels van het tekstantwoord staan in tekst_schema.TekstAntwoord (afgedwongen schema)

# Tweede pass: na de berekening licht Gemini de resultaten toe. Het oordeel staat al vast.
OORDEEL_PROMPT = """
You are an experienced Belgian M&A and Private Equity analyst. The LBO model has been
run and you receive the results plus the findings from the annual report. Always
answer in English. The answer follows a fixed JSON schema.

Fields:
- kwalitatief_lbo_oordeel: concise commentary on the LBO result.
- investment_thesis: exactly three bullets, each one sentence: why a PE fund would or
  would not want to own this company. Ground each bullet in the figures or findings.
- dd_vragen: exactly five due diligence questions. Each question tests one red flag or
  one assumption from the input; gekoppeld_aan names that red flag or assumption.

Instructions:
- LBO_Status is the conclusion of the model. Explain it: do not contradict it and do
  not replace it with a conclusion of your own.
- Explain the result from the data: cash flow stability, multi-year trend, covenants,
  leverage, use of the RCF and returns. The screening case (rule-based, with a standard
  stress) and the AI case may differ: name the gap when it matters.
- A qualitative concern the model does not measure is named as a point of attention.
- Use only the figures provided. Do not calculate or estimate new ones. The value null
  means the figure is not available.
- Do not invent anything.
"""

# De sleutels van het oordeelantwoord staan in tekst_schema.OordeelAntwoord (afgedwongen schema)

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
	"Eigendom",
	"LBO_Screening_IRR_Pct",
	"LBO_Stress_IRR_Pct",
	"LBO_Stress_Convenanten",
	"LBO_Assumptie_Vlaggen",
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
