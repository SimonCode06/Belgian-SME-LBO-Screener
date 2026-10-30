"""All display text of the project, in English, in one place.

Internal keys ("Financiele_Schulden_LT") stay as they are. Code never compares against a
translated sentence: it compares against the constants below, so a change of wording
cannot silently break a status check.
"""

# ============================================================================
# Status and outcome constants: these are compared in code
# ============================================================================
STATUS_STRONG = "STRONG LBO CANDIDATE"
STATUS_POSSIBLE = "POSSIBLE CANDIDATE"
STATUS_NO_GO = "NO-GO"
STATUS_REVIEW = "REVIEW"
STATUS_INSUFFICIENT = "INSUFFICIENT DATA"

STATUS_POSSIBLE_FLAGS = f"{STATUS_POSSIBLE} (See Red Flags)"
STATUS_POSSIBLE_CASHFLOW = f"{STATUS_POSSIBLE} (Check Cash Flow)"
STATUS_REVIEW_DATA = f"{STATUS_REVIEW} (Data Does Not Reconcile)"
STATUS_REVIEW_MODEL = f"{STATUS_REVIEW} (Model Does Not Reconcile)"
STATUS_NO_GO_EBITDA = f"{STATUS_NO_GO} (Negative/No EBITDA)"
STATUS_NO_GO_SIZE = f"{STATUS_NO_GO} (Too Small for an LBO)"
STATUS_NO_GO_EQUITY = STATUS_NO_GO + " (No Equity for Seller at {multiple}x)"
STATUS_NO_GO_DEBT = f"{STATUS_NO_GO} (New Debt Not Serviceable)"
STATUS_NO_GO_RETURN = f"{STATUS_NO_GO} (Negative Return)"

YES = "YES"
NO = "NO"

CHECK_OK = "OK"
CHECK_ERROR = "ERROR"
CHECK_FLAG = "FLAG"
CHECK_REVIEW = "REVIEW"

COVENANTS_OK = "OK"
COVENANTS_BREACHED = "BREACHED"
NOT_APPLICABLE = "N/A"

DATA_COMPLETE = "Complete"
DATA_PARTIAL = "Partial"
DATA_INSUFFICIENT = "Insufficient"

BASIS_REVENUE = "Revenue (code 70)"
BASIS_GROSS_MARGIN = "Gross Margin (code 9900)"

# Statutory auditor opinion: Gemini returns exactly one of these
OPINION_UNQUALIFIED = "Unqualified"
OPINION_QUALIFIED = "Qualified"
OPINION_DISCLAIMER = "Disclaimer of Opinion"
OPINION_ADVERSE = "Adverse"
OPINION_NO_AUDITOR = "No Statutory Auditor"
OPINION_UNKNOWN = "Unknown"
OPINIONS_HEAVY = (OPINION_QUALIFIED, OPINION_DISCLAIMER, OPINION_ADVERSE)

API_KEY_REFUSED = "API key refused"

# Status colours: first match on the start of the text (background, font)
STATUS_COLOURS = {
	STATUS_STRONG: ("C6EFCE", "006100"),
	STATUS_POSSIBLE: ("FFEB9C", "9C6500"),
	STATUS_NO_GO: ("FFC7CE", "9C0006"),
	STATUS_REVIEW: ("FFC7CE", "9C0006"),
	STATUS_INSUFFICIENT: ("FFEB9C", "9C6500"),
	YES: ("C6EFCE", "006100"),
	NO: ("FFC7CE", "9C0006"),
}

SCHEMA_LABELS = {"VOL": "Full", "MIC": "Micro", "VKT/MIC": "Abbreviated/Micro"}


def not_available(reason):
	return f"{NOT_APPLICABLE} ({reason})"


def covenants_breached(breaches):
	return f"{COVENANTS_BREACHED}: " + "; ".join(breaches)


def data_insufficient(detail):
	return f"{DATA_INSUFFICIENT}: {detail}"


def data_partial(detail):
	return f"{DATA_PARTIAL}: {detail}"


def check_review(errors):
	return f"{CHECK_REVIEW}: " + "; ".join(errors)


def debt_target(ok, leverage):
	return f"{YES} (< 2.0x)" if ok else f"{NO} ({leverage:.2f}x)"


# ============================================================================
# LBO model
# ============================================================================
REASON_INSUFFICIENT_DATA = "Insufficient Data"
REASON_NO_EBITDA = "No EBITDA"

LABEL_CLOSING = "Closing"
PERIOD_STUB_SUFFIX = " (stub)"


def period_label(year, stub=False):
	return f"FY{year}F" + (PERIOD_STUB_SUFFIX if stub else "")


def actual_label(year):
	return f"FY{year}A"


BREACH_DSCR = "Y{year} DSCR {value:.2f}x"
BREACH_INTEREST = "Y{year} Interest Coverage {value:.2f}x"
BREACH_LEVERAGE = "Y{year} Leverage {value:.2f}x"
BREACH_EBITDA = "Y{year} EBITDA negative"

TEST_BALANCE = ("Balance Sheet balances", "Total assets − total liabilities & equity, per period")
TEST_CASH = ("Cash ties", "Ending cash Cash Flow Statement = cash per Cash Flow Waterfall")
TEST_DEBT = ("Debt ties", "Closing balance per tranche rebuilt from its movements = Balance Sheet")
TEST_EQUITY = ("Equity ties", "Opening + net income − dividends + capital = closing")
TEST_SOURCES = ("Sources = Uses", "At closing")
TEST_NEGATIVE_DEBT = ("No negative debt", "Every tranche ≥ 0")
TEST_ITERATION = ("Interest iteration converged", "Residual between the last two iterations")
TEST_MINIMUM_CASH = ("Cash ≥ minimum", "After RCF drawdown (flag, not a calculation error)")

NET_DEBT_FINANCIAL = "financial debt"
NET_DEBT_FINANCIAL_DEBT_LIKE = "financial debt + Debt-Like Items"
NET_DEBT_ALL_CASH = "all cash"
NET_DEBT_EXCESS_CASH = "cash above the minimum operating cash"
NET_DEBT_USED_FOR = "{debt} − {cash}. Used for: {use}."

# ============================================================================
# Red flags and data signals
# ============================================================================
FLAG_NEGATIVE_EQUITY = "Negative Shareholders' Equity (EUR {value:,.0f}): alarm bell procedure (Belgian Companies Code)"
FLAG_ACCUMULATED_LOSS = "Accumulated loss carried forward (EUR {value:,.0f})"
FLAG_AUDITOR = "Statutory Auditor Opinion: {opinion}"
FLAG_LIQUIDATION = "Company in liquidation"
FLAG_DIRECTOR_RECEIVABLE = "Receivable from directors (EUR {value:,.0f}): leakage, to be repaid at closing"
FLAG_GROUP_RECEIVABLES = "Receivables from affiliated companies (EUR {value:,.0f}, {pct:.0f}% of total assets)"
FLAG_EBITDA_TREND = (
	"Historical EBITDA declines ({cagr:+.1f}% p.a.) while the forecast grows ({growth:+.1f}%): return may be overstated"
)
FLAG_DOWNSIDE_COVENANTS = "Downside scenario breaches the Covenants ({detail})"
FLAG_RCF_AT_EXIT = "RCF still drawn EUR {value:,.0f} at exit: the shortfall is structural, not temporary"
FLAG_THIRD_PARTY_GUARANTEES = "Guarantees for third parties or the group (EUR {value:,.0f}) exceed EBITDA"
FLAG_LOW_CASH = "Cash & Cash Equivalents (EUR {cash:,.0f}) below the minimum cash requirement (EUR {need:,.0f})"
FLAG_CASH_BELOW_MINIMUM = "Cash falls EUR {value:,.0f} below the minimum, even after the RCF drawdown"
FLAG_NEGATIVE_NWC = "Negative Net Working Capital (EUR {value:,.0f})"
FLAG_REVENUE_DECLINE = "Revenue/Gross Margin decline ({value:+.1f}%)"
FLAG_MARGIN_DECLINE = "Sharp EBITDA margin decline ({value:+.1f} pp)"
FLAG_LEVERAGE_TARGET = "LBO debt does not fall below 2.0x within 5 years (end: {value:.2f}x)"
FLAG_RCF_NEEDED = "RCF needed: peak EUR {peak:,.0f} of limit EUR {limit:,.0f}"

SIGNAL_MONTHS = "Fiscal year {year} has {months} months: results annualized to 12 months"
SIGNAL_CORRECTED = "Fiscal year {year} is a corrected filing"
SIGNAL_SOCIAL_DEBT = (
	"Fiscal year {year}: EUR {value:,.0f} of social security debt (454/9) is not in the notes (9076, 9077)"
)
SIGNAL_NO_PRIOR_YEAR = "No consecutive CSV for the fiscal year before {year}: no trend calculated"

ERROR_CODE_MISSING = "code {code} missing"
ERROR_CURRENCY = "currency is {currency}"
ERROR_RECONCILIATION = "{name} differs by EUR {value:,.0f}"

RECONCILIATION_NAMES = {
	"activa = passiva": "assets = liabilities",
	"opbouw activa": "build-up of assets",
	"opbouw vaste activa": "build-up of fixed assets",
	"opbouw vlottende activa": "build-up of current assets",
	"opbouw vorderingen": "build-up of receivables",
	"opbouw passiva": "build-up of liabilities",
	"opbouw schulden": "build-up of debt",
	"opbouw schulden LT": "build-up of long-term debt",
	"opbouw schulden KT": "build-up of short-term debt",
	"opbouw fiscale en sociale schulden": "build-up of tax and social debt",
	"opbouw bedrijfswinst": "build-up of EBIT",
	"opbouw bedrijfsopbrengsten": "build-up of operating income",
	"opbouw bedrijfskosten": "build-up of operating expenses",
	"opbouw vanuit brutomarge": "build-up from gross margin",
	"uitsplitsing belastingen": "tax breakdown",
	"uitsplitsing sociale schulden": "social security breakdown",
}

ADJUSTMENTS_NOTE = (
	"Non-recurring expenses (66A) EUR {expenses:,.0f} added back, non-recurring income (76A) EUR {income:,.0f} removed."
)
ADJUSTMENTS_UNAVAILABLE = "Non-recurring items not available (codes 66A and 76A)."

COMPLETENESS_NO_DATA = "no data for {codes}"
COMPLETENESS_CAPEX = "capex (statement of fixed assets)"
COMPLETENESS_NO_PRIOR = "no consecutive prior fiscal year"
COMPLETENESS_PRIOR_CODES = "prior fiscal year lacks code {codes}"
COMPLETENESS_FEW_YEARS = "{years} fiscal years, at least {minimum} needed for the drivers"

# ============================================================================
# Text analysis (Gemini)
# ============================================================================
TEXT_NO_PDF = "No PDF found: no text analysis."
TEXT_NO_GEMINI = "No text analysis: Gemini is not available."
TEXT_FAILED = "Text analysis failed: run the script again."
TEXT_WRONG_COMPANY = "Text ignored: the PDF belongs to enterprise number {pdf}, the figures to {figures}."
TEXT_WRONG_YEAR = "PDF is for fiscal year {pdf}, the figures for {figures}"
TEXT_UNKNOWN = "unknown"
COMMENTARY_NO_GEMINI = "No commentary: Gemini is not available."
COMMENTARY_FAILED = "Commentary failed: run the script again."

# ============================================================================
# Workbooks
# ============================================================================
OVERVIEW_FILE = "LBO_Screening_Overview"
COMPANY_FILE = "LBO_Model"
UNKNOWN_COMPANY = "Unknown_Company"

TAB_OVERVIEW = "Executive Summary"
TAB_DETAIL = "Full Data Detail"

UNITS_NOTE = "EUR in thousands"
FOOTER_DATE = "Date"
FOOTER_VERSION = "Model version"
FOOTER_GEMINI = "Gemini model"
FOOTER_SOURCE = "Source file"

GROUP_IDENTIFICATION = "IDENTIFICATION & ASSESSMENT"
GROUP_TRENDS = "MULTI-YEAR TREND & MARGINS"
GROUP_BRIDGE = "EV-TO-EQUITY BRIDGE & NWC"
GROUP_RETURNS = "LBO VALUATION & RETURNS (5Y)"

# Column headers of the overview workbook, by internal key
COLUMN_LABELS = {
	"Bedrijfsnaam": "Company",
	"Ondernemingsnummer": "Enterprise Number",
	"Boekjaar": "Fiscal Year",
	"Boekjaar_Begin": "Fiscal Year Start",
	"Boekjaar_Einde": "Fiscal Year End",
	"Boekjaar_Maanden": "Months in Fiscal Year",
	"Boekjaar_Maanden_Vorig_Jaar": "Months in Prior Fiscal Year",
	"Schema_Type": "Filing Schema",
	"LBO_Status": "LBO Assessment",
	"Data_Volledigheid": "Data Completeness",
	"Omzet_Basis": "Revenue Basis",
	"Omzet_of_Brutomarge_Vorig_Jaar": "Revenue / Gross Margin (Prior Year)",
	"Omzet_of_Brutomarge": "Revenue / Gross Margin",
	"Omzetgroei_Pct": "Revenue Growth",
	"Brutomarge_Vorig_Jaar": "Gross Margin (Prior Year)",
	"Brutomarge": "Gross Margin",
	"Bedrijfswinst_EBIT_Vorig_Jaar": "EBIT (Prior Year)",
	"Bedrijfswinst_EBIT": "EBIT",
	"Afschrijvingen_Vorig_Jaar": "D&A (Prior Year)",
	"Afschrijvingen": "Depreciation & Amortization (D&A)",
	"Voorzieningen_Mutatie_Vorig_Jaar": "Change in Provisions (Prior Year)",
	"Voorzieningen_Mutatie": "Change in Provisions",
	"Gerapporteerde_EBITDA_Vorig_Jaar": "Reported EBITDA (Prior Year)",
	"Gerapporteerde_EBITDA": "Reported EBITDA",
	"EBITDA_Groei_Pct": "EBITDA Growth",
	"Waardeverminderingen_Vlottend_Vorig_Jaar": "Write-downs Current Assets (Prior Year)",
	"Waardeverminderingen_Vlottend": "Write-downs Current Assets",
	"Inkoop": "Cost of Goods & Services",
	"Personeelskosten": "Personnel Costs",
	"VTE": "FTEs",
	"Normalisatie_Bedrag": "EBITDA Adjustments (Non-recurring Items)",
	"Genormaliseerde_EBITDA": "Adjusted EBITDA",
	"EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct": "EBITDA Margin on Revenue (Prior Year)",
	"EBITDA_Marge_Op_Omzet_Pct": "EBITDA Margin on Revenue",
	"EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct": "EBITDA Margin on Gross Margin (Prior Year)",
	"EBITDA_Marge_Op_Brutomarge_Pct": "EBITDA Margin on Gross Margin",
	"Marge_Verandering_pp": "Margin Change",
	"Check_Data": "Data Check",
	"Financiele_Schulden_LT": "Financial Debt Long-Term",
	"Financiele_Schulden_KT": "Financial Debt Short-Term",
	"Totale_Financiele_Schuld": "Total Financial Debt",
	"Liquide_Middelen": "Cash & Cash Equivalents",
	"Eigen_Aandelen": "Treasury Shares",
	"Net_Debt": "Net Debt",
	"Voorzieningen_en_Uitgestelde_Belastingen": "Provisions & Deferred Taxes",
	"Belasting_en_Vervallen_RSZ_Schulden": "Taxes & Overdue Social Security",
	"Overige_Schulden_LT_en_KT": "Other Debt (Long- and Short-Term)",
	"Debt_Like_Items": "Debt-Like Items",
	"Minimum_Cash_Behoefte": "Minimum Cash Requirement",
	"Minimum_Operationele_Cash": "Minimum Operating Cash",
	"Adjusted_Net_Debt": "Adjusted Net Debt",
	"Memo_Sociale_Schulden": "Memo: Accrued Payroll & Social Security",
	"Memo_Zekerheden_Derden": "Memo: Guarantees for Third Parties",
	"Memo_Vorderingen_Bestuurders": "Memo: Receivables from Directors",
	"Memo_Vorderingen_Verbonden": "Memo: Receivables from Affiliates",
	"Voorraden": "Inventory",
	"Handelsvorderingen": "Trade Receivables",
	"Handelsschulden": "Trade Payables",
	"Ontvangen_Vooruitbetalingen": "Customer Advances",
	"Trade_Working_Capital": "Net Working Capital (NWC)",
	"Capex_Laatste_Jaar": "Capex (Last Year)",
	"Capex_Gemiddeld": "Capex (Average)",
	"Capex_Aantal_Jaren": "Capex Years",
	"Huidige_Net_Debt_to_EBITDA": "Current Net Debt / EBITDA",
	"Driver_Aantal_Jaren": "Fiscal Years in Drivers",
	"Driver_Historische_CAGR_Pct": "Historical Revenue CAGR",
	"Driver_Omzetgroei_Pct": "Mechanical Revenue Growth",
	"Driver_EBITDA_CAGR_Pct": "Historical EBITDA CAGR",
	"Driver_EBITDA_Marge_Gemiddeld_Pct": "Average EBITDA Margin",
	"Driver_EBITDA_Marge_Pct": "Reference EBITDA Margin",
	"Driver_Inkoop_Pct": "Mechanical Cost of Goods & Services Ratio",
	"Driver_Overige_Kosten_Pct": "Mechanical Other Operating Expenses Ratio",
	"Driver_DA_Pct_Vaste_Activa": "D&A % of Opening Fixed Assets",
	"Driver_Capex_Pct": "Capex % of Revenue",
	"Driver_DSO": "DSO",
	"Driver_DIO": "DIO",
	"Driver_DPO": "DPO",
	"Driver_Dagen_Vooruitbetaling": "Customer Advance Days",
	"Driver_Kosten_60_Pct": "Goods Cost Basis for DIO",
	"Driver_Kosten_6061_Pct": "Purchases Basis for DPO",
	"Open_Vaste_Activa": "Opening PP&E & Intangibles",
	"Open_Financiele_Vaste_Activa": "Opening Financial Fixed Assets",
	"Open_Overige_Activa_Operationeel": "Opening Other Assets (Operating)",
	"Open_Overige_Activa_Niet_Operationeel": "Opening Other Assets (Non-Operating)",
	"Open_Sociale_Schulden": "Opening Accrued Payroll & Social Security",
	"Open_Overige_Passiva": "Opening Other Liabilities",
	"Instap_Multiple": "Entry Multiple",
	"Senior_Multiple": "Senior Leverage Multiple",
	"Indicatieve_EV": "Entry EV",
	"Indicatieve_Equity_Value": "Equity Purchase Price",
	"LBO_Instap_EV": "LBO Entry EV",
	"LBO_Transactiekosten": "Transaction Fees",
	"LBO_Financieringskosten": "Financing Fees",
	"LBO_Kosten": "Total Fees",
	"LBO_Senior_Schuld": "Senior Term Loan",
	"LBO_Vendor_Loan": "Vendor Loan (Seller Note)",
	"LBO_Sponsor_Equity_Instap": "Sponsor Equity",
	"LBO_Closing_Datum": "Closing Date",
	"LBO_Duur_Jaren": "Holding Period (Years)",
	"LBO_EBITDA_Jaar5": "Exit EBITDA",
	"LBO_EBITDA_Marge_Exit_Pct": "Exit EBITDA Margin",
	"LBO_FCF_Cumulatief_5J": "Cumulative Free Cash Flow (FCF)",
	"LBO_Dividend_Cumulatief": "Cumulative Dividends",
	"LBO_Eind_Net_Debt_Jaar5": "Exit Net Debt",
	"LBO_Eind_Net_Debt_to_EBITDA": "Exit Net Debt / EBITDA",
	"LBO_Schuld_Onder_2x_5J": "Debt < 2.0x (5Y)",
	"LBO_Laagste_DSCR": "Minimum DSCR",
	"LBO_Laagste_Rentedekking": "Minimum Interest Coverage Ratio",
	"LBO_Hoogste_Leverage": "Peak Net Debt / EBITDA",
	"LBO_Laagste_Cash": "Minimum Cash",
	"LBO_Cash_Onder_Minimum": "Cash Shortfall vs Minimum",
	"LBO_RCF_Limiet": "RCF Limit",
	"LBO_RCF_Piek": "Peak RCF Drawn",
	"LBO_RCF_Eind": "RCF Drawn at Exit",
	"LBO_Convenanten": "Covenants",
	"LBO_Balanscheck": "Model Integrity Checks",
	"LBO_Exit_EV_Jaar5": "Exit EV",
	"LBO_Exit_Equity_Jaar5": "Exit Equity",
	"Indicatieve_MoIC": "MoIC",
	"Indicatieve_IRR_Pct": "IRR",
	"LBO_Downside_IRR_Pct": "Downside IRR",
	"LBO_Downside_MoIC": "Downside MoIC",
	"LBO_Downside_Convenanten": "Downside Covenants",
	"LBO_Upside_IRR_Pct": "Upside IRR",
	"Eigen_Vermogen": "Shareholders' Equity",
	"Balanstotaal": "Total Assets",
	"Overgedragen_Resultaat": "Retained Earnings",
	"Normalisatie_Toelichting": "EBITDA Adjustments Note",
	"Normalisatie_Voorstellen": "Proposed Further Adjustments",
	"Commissaris_Oordeel": "Statutory Auditor Opinion",
	"Buitenbalans_Verplichtingen": "Off-Balance-Sheet Commitments",
	"Red_Flags": "Red Flags",
	"Kwalitatief_LBO_Oordeel": "Qualitative LBO Commentary",
	"Bronbestand": "Source File",
	"Gebruikt_Model": "Gemini Model",
}
