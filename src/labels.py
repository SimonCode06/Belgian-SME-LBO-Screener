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

ASSUMPTIONS_AI = "Gemini AI proposal"
ASSUMPTIONS_FALLBACK_HISTORY = "Historical fallback (insufficient history)"
ASSUMPTIONS_FALLBACK_NO_AI = "Historical fallback (Gemini not available)"
ASSUMPTIONS_FALLBACK_NOT_REQUIRED = "Historical fallback (no LBO to calculate)"
ASSUMPTIONS_SCREENING = "Rule-based (filing)"
ASSUMPTIONS_STRESS = "Rule-based (filing) with the standard stress: EBITDA {haircuts} below the Screening Base in Y1-Y5"
ASSUMPTIONS_RULE_BASED = "Filing (rule-based)"

NONE = "None"
OWNERSHIP_TYPES = {
	"zelfstandig": "Independent",
	"groepsdochter": "Group subsidiary",
	"pe_backed": "PE-backed",
	"onbekend": "Ownership unknown",
}
OWNERSHIP_CONSOLIDATED = "consolidated"
YES_NO_UNKNOWN = {"ja": "yes", "nee": "no", "onbekend": "unknown"}
ADJUSTMENT_TYPES = {
	"bestuurdersvergoeding": "Director remuneration",
	"huur_verbonden_partij": "Related-party rent",
	"privekosten": "Private expenses",
	"eenmalig": "Non-recurring item",
	"subsidie": "Subsidy",
	"overig": "Other",
}
FLAG_CATEGORIES = {
	"governance": "Governance",
	"verbonden_partijen": "Related parties",
	"going_concern": "Going concern",
	"juridisch": "Legal",
	"klantconcentratie": "Customer concentration",
	"personeel": "Personnel",
	"overig": "Other",
}
SEVERITIES = {"hoog": "HIGH", "middel": "MEDIUM", "laag": "LOW"}
ASSUMPTION_FLAG_DOWNSIDE_DEPTH = (
	"Downside EBITDA in Y5 (EUR {down:,.0f}) is below {pct:.0f}% of Base (EUR {base:,.0f}): not a credible setback"
)
ASSUMPTION_FLAG_EBITDA_CAGR = (
	"Base EBITDA CAGR {ai:+.1f}% against a historical {hist:+.1f}%: more than {pp:.0f} pp above the trend"
)
DD_LINKED_TO = "tests"
QUOTE_NOT_FOUND = "Quoted source not found in the PDF: confidence set to low"
AMOUNT_FROM_CSV = "CSV code {code}"
AMOUNT_AI_UNVERIFIED = "AI, to be verified"

SNAPSHOT_LABEL = "Assumption Snapshot"
SNAPSHOT_DATE = "Snapshot Date"
SNAPSHOT_STATUS = "Snapshot Status"
SNAPSHOT_STATUS_LABELS = {"voorstel": "Proposal (not reviewed)", "goedgekeurd": "Approved by analyst"}

DRIVER_PRICE = "Price Growth"
DRIVER_VOLUME = "Volume Growth"
DRIVER_INDEXATION = "Wage Indexation"
DRIVER_ELASTICITY = "FTE Elasticity to Volume"
DRIVER_COGS = "Cost of Goods & Services % Revenue"
DRIVER_OPEX = "Other Operating Expenses % Revenue"
DRIVER_DA = "D&A % Opening PP&E & Intangibles"
DRIVER_CAPEX = "Capex % Revenue"
DRIVER_DSO = "DSO"
DRIVER_DIO = "DIO"
DRIVER_DPO = "DPO"
DRIVER_ADVANCES = "Customer Advance Days"
DRIVER_REVENUE_GROWTH = "Revenue Growth"
DRIVER_EBITDA_MARGIN = "EBITDA Margin"

ASSUMPTION_FLAG_BOUNDS = "{years} outside the range {low:g} to {high:g}"
ASSUMPTION_FLAG_HISTORY = "{years} more than {margin:g} outside the historical range {low:.1f} to {high:.1f}"
ASSUMPTION_FLAG_ORDER = "{worse} is better than {better} in {years}"
FLAG_ASSUMPTIONS = "Assumption flag: {detail}"
FLAG_CLOSING_LIMITED = "Closing date limited to {date}: at most 12 months after the last filed accounts"

# ============================================================================
# Workbooks
# ============================================================================
OVERVIEW_FILE = "LBO_Screening_Overview"
COMPANY_FILE = "LBO_Model"
UNKNOWN_COMPANY = "Unknown_Company"

TAB_OVERVIEW = "Executive Summary"
TAB_SUMMARY = "Executive Summary"
TAB_MODEL = "3-Statement Model"
TAB_LBO = "LBO Analysis"

TITLE_MODEL = "3-STATEMENT MODEL"
TITLE_LBO = "LBO ANALYSIS"
TITLE_SUMMARY = "EXECUTIVE SUMMARY"
SUBTITLE_SUMMARY = "Enterprise Number: {number}   |   Fiscal Year: {year}   |   Schema: {schema}   |   Assumptions: {source}"
NO_PROJECTION = "No LBO projection possible: {reason}."

CHECKS_TOTAL = "Model Integrity Checks"
HEADER_LBO_YEAR = "LBO Year"
HEADER_FISCAL_YEAR = "Fiscal Year"
HEADER_ACTUAL = "Actual"
HEADER_RATIONALE = "Rationale"
HEADER_SOURCE = "Source"
HEADER_CONFIDENCE = "Confidence"
HEADER_FLAG = "Flag"
HEADER_OVERRIDES = "Overrides"

SCENARIO_SELECT = "Active Scenario"
SCENARIO_INDEX = "Scenario Index"
SCENARIO_LIST = "Scenarios"
LEGEND = "Colour Code"
LEGEND_INPUT = "Blue: hardcoded input, AI proposal, historical NBB value"
LEGEND_FORMULA = "Black: formula"
LEGEND_LINK = "Green: direct link to another tab"
LEGEND_OVERRIDE = "Yellow: override cell, leave empty to keep the AI proposal"

SECTION_SCENARIO = "SCENARIO SELECTOR"
SECTION_TIMELINE = "TIMELINE"
SECTION_AI = "ASSUMPTIONS: {scenario}"
SECTION_ACTIVE = "ACTIVE ASSUMPTIONS"
SECTION_BUILD = "OPERATING BUILD"
SECTION_IS = "INCOME STATEMENT"
SECTION_TAX = "INCOME TAX CALCULATION"
SECTION_BS = "BALANCE SHEET"
SECTION_CF = "CASH FLOW STATEMENT"
SECTION_SCHEDULES = "FIXED ASSETS, GOODWILL AND FINANCING FEES"
SECTION_CHECKS = "MODEL INTEGRITY CHECKS"
SECTION_INPUTS = "TRANSACTION INPUTS"
SECTION_BRIDGE = "EV-TO-EQUITY BRIDGE"
SECTION_SU = "SOURCES & USES"
SECTION_DEBT = "DEBT SCHEDULE"
SECTION_INTEREST = "INTEREST"
SECTION_WATERFALL = "CASH FLOW WATERFALL"
SECTION_COVENANTS = "COVENANTS"
SECTION_EXIT = "EXIT AND RETURNS"
SECTION_DEFINITIONS = "NET DEBT DEFINITIONS"
SECTION_KEY_METRICS = "KEY METRICS (ACTIVE SCENARIO)"
SECTION_SCENARIOS = "KEY METRICS BY SCENARIO (ANALYST CASE AND SCREENING CASE)"
SECTION_TREND = "MULTI-YEAR OVERVIEW (ACTIVE SCENARIO)"
SECTION_TEXT = "RED FLAGS AND QUALITATIVE ASSESSMENT"

ROW_AI = "{driver}: AI Proposal"
ROW_RULE_BASED = "{driver}: Filing (Rule-Based)"
ROW_OVERRIDE = "{driver}: Override"
ROW_USED = "{driver}: Used"

STATUS_LABEL = "LBO Assessment"
OVERRIDES_ACTIVE = "Overrides active"
OVERRIDES_NOTE = "The assessment reflects the AI case and does not follow overrides."
SCENARIO_NOTE = "Python results on the proposed assumptions: these do not follow overrides."

# Row labels of the workbook, by internal row key
ROW_LABELS = {
	"jaar_nr": "LBO Year Number",
	"einde": "Period End",
	"fractie": "Period Fraction",
	"a_groei": "Revenue Growth",
	"a_marge": "EBITDA Margin",
	"rev_ann": "Annualized Revenue",
	"pers_ann": "Annualized Personnel Costs",
	"fte": "FTEs",
	"kost_fte": "Cost per FTE (Annualized)",
	"rev": "Revenue / Gross Margin",
	"cogs": "Cost of Goods & Services",
	"pers": "Personnel Costs",
	"opex": "Other Operating Expenses",
	"ebitda": "Adjusted EBITDA",
	"da": "Depreciation & Amortization (D&A)",
	"gw": "Goodwill Amortization",
	"nonrec": "EBITDA Adjustments and Provisions (Non-recurring Items)",
	"ebit": "EBIT",
	"int_exp": "Interest Expense and Commitment Fee",
	"fee_am": "Amortization of Financing Fees",
	"int_inc": "Interest Income on Cash",
	"fin_res": "Net Financial Result",
	"ebt": "EBT",
	"tax": "Income Tax",
	"ni": "Net Income",
	"fin_cost": "Financing Costs",
	"deductible": "Deductible Financing Costs",
	"taxable": "Taxable Income",
	"tax_calc": "Income Tax Due",
	"goodwill": "Goodwill",
	"fin_fees": "Capitalized Financing Fees",
	"ppe": "PP&E & Intangibles",
	"fin_fa": "Financial Fixed Assets",
	"inv": "Inventory",
	"ar": "Trade Receivables",
	"oth_op": "Other Assets (Operating)",
	"oth_nonop": "Other Assets (Non-Operating: Group, Directors)",
	"cash": "Cash & Cash Equivalents",
	"ta": "Total Assets",
	"equity": "Shareholders' Equity",
	"exist_debt": "Existing Financial Debt",
	"senior": "Senior Term Loan",
	"rcf": "Revolving Credit Facility (RCF)",
	"vendor": "Vendor Loan (Seller Note)",
	"ap": "Trade Payables",
	"adv": "Customer Advances",
	"soc": "Accrued Payroll & Social Security",
	"oth_l": "Other Liabilities",
	"tl": "Total Liabilities & Equity",
	"bs_check": "Balance Sheet Check",
	"cf_ni": "Net Income",
	"cf_da": "D&A",
	"cf_gw": "Goodwill Amortization",
	"cf_fee": "Amortization of Financing Fees",
	"cf_inv": "Change in Inventory",
	"cf_ar": "Change in Trade Receivables",
	"cf_oth": "Change in Other Assets",
	"cf_ap": "Change in Trade Payables",
	"cf_adv": "Change in Customer Advances",
	"cf_soc": "Change in Accrued Payroll & Social Security",
	"cf_othl": "Change in Other Liabilities",
	"cfo": "Cash Flow from Operations (CFO)",
	"cf_capex": "Capex",
	"cf_pre": "Cash Flow before Financing",
	"cf_mand": "Mandatory Amortization",
	"cf_sweep": "Cash Sweep",
	"cf_draw": "RCF Drawdown",
	"cf_repay": "RCF Repayment",
	"cf_div": "Dividends",
	"cff": "Cash Flow from Financing (CFF)",
	"cf_net": "Net Change in Cash",
	"cf_open": "Opening Cash",
	"cf_end": "Closing Cash",
	"capex": "Capex",
	"rest": "Existing Assets: Remaining Book Value",
	"da_exist": "D&A on Existing Assets",
	"vintage": "D&A on Capex Vintage Year {year}",
	"da_new": "D&A on New Capex",
	"da_total": "Total D&A",
	"gw_amort": "Goodwill Amortization",
	"fee_amort": "Amortization of Financing Fees",
	"check_cash": "Cash Ties: Cash Flow Statement vs Waterfall",
	"check_debt": "Debt Ties: Rebuilt Tranches vs Balance Sheet",
	"senior_rebuilt": "Senior Term Loan Rebuilt from Movements",
	"rcf_rebuilt": "RCF Rebuilt from Movements",
	"entry_ebitda": "Adjusted EBITDA (Entry)",
	"entry_ev": "Entry EV",
	"fin_debt": "Financial Debt",
	"cash_br": "Cash & Cash Equivalents (excl. Treasury Shares)",
	"debt_like": "Debt-Like Items",
	"min_req": "Minimum Cash Requirement",
	"min_cash": "Minimum Operating Cash",
	"net_debt_0": "Net Debt (Bank Covenant Definition)",
	"adj_nd": "Adjusted Net Debt",
	"eq_price": "Equity Purchase Price",
	"s_senior": "Senior Term Loan",
	"s_vendor": "Vendor Loan (Seller Note)",
	"s_rcf": "RCF Drawn at Closing",
	"s_equity": "Sponsor Equity",
	"s_total": "Total Sources",
	"u_equity": "Equity Purchase Price",
	"u_debt": "Settlement of Adjusted Net Debt",
	"u_trans": "Transaction Fees",
	"u_fin": "Financing Fees",
	"u_total": "Total Uses",
	"su_check": "Sources − Uses",
	"goodwill_0": "Goodwill at Closing",
	"rcf_limit": "RCF Limit",
	"d_senior_open": "Senior Term Loan: Opening",
	"d_mand": "Mandatory Amortization",
	"d_sweep": "Cash Sweep",
	"d_senior": "Senior Term Loan: Closing",
	"d_rcf_open": "RCF: Opening",
	"d_draw": "Drawdown",
	"d_repay": "Repayment",
	"d_rcf": "RCF: Closing",
	"d_rcf_room": "RCF: Undrawn Headroom",
	"d_vendor": "Vendor Loan: Closing (Bullet at Exit)",
	"i_senior": "Interest Senior Term Loan",
	"i_rcf": "Interest RCF",
	"i_commit": "Commitment Fee RCF",
	"i_vendor": "Interest Vendor Loan",
	"i_total": "Total Cash Interest",
	"i_income": "Interest Income on Cash",
	"w_ebitda": "Adjusted EBITDA",
	"w_tax": "Income Tax",
	"w_capex": "Capex",
	"w_twc": "Change in Net Working Capital (NWC)",
	"w_oth": "Change in Other Working Capital",
	"w_int": "Cash Interest and Commitment Fee",
	"w_inc": "Interest Income on Cash",
	"w_fcf": "Free Cash Flow (FCF)",
	"w_mand": "Mandatory Amortization",
	"w_ecf": "Excess Cash Flow (ECF)",
	"w_open": "Opening Cash",
	"w_pos": "Cash Position above Minimum",
	"w_draw": "RCF Drawdown",
	"w_repay": "RCF Repayment",
	"w_sweep": "Cash Sweep",
	"w_vrij": "Free Cash after Sweep",
	"w_res": "Distributable Reserves (Before Dividend)",
	"w_div": "Dividends",
	"w_end": "Closing Cash per Waterfall",
	"res_close": "Distributable Reserves (Closing)",
	"c_icr": "Interest Coverage Ratio",
	"c_icr_min": "Minimum Interest Coverage Ratio",
	"c_icr_room": "Interest Coverage Headroom",
	"c_dscr": "DSCR",
	"c_dscr_min": "Minimum DSCR",
	"c_dscr_room": "DSCR Headroom",
	"c_lev": "Net Debt / EBITDA (Bank Covenant)",
	"c_lev_max": "Maximum Net Debt / EBITDA",
	"c_lev_room": "Leverage Headroom",
	"c_status": "Covenant Test",
	"nd_bank": "Net Debt (Bank Covenant)",
	"nd_val": "Net Debt (Valuation)",
	"x_ebitda": "Exit EBITDA",
	"x_mult": "Exit Multiple",
	"x_ev": "Exit EV",
	"x_nd": "Exit Net Debt (Valuation)",
	"x_equity": "Exit Equity",
	"x_lev": "Exit Net Debt / EBITDA",
	"x_flows": "Sponsor Cash Flows",
	"x_dates": "Cash Flow Dates",
	"x_irr": "IRR",
	"x_moic": "MoIC",
	"x_covenants": "Covenants",
	"x_peak_lev": "Peak Net Debt / EBITDA",
	"x_min_dscr": "Minimum DSCR",
	"x_duration": "Holding Period (Years)",
}

INPUT_LABELS = {
	"Entry_Multiple": "Entry Multiple (EV / EBITDA)",
	"Exit_Multiple": "Exit Multiple (EV / EBITDA)",
	"Senior_Multiple": "Senior Term Loan (x EBITDA)",
	"Senior_Rate": "Senior Term Loan Interest Rate",
	"Senior_Tenor": "Senior Term Loan Tenor (Years)",
	"Cash_Sweep_Pct": "Cash Sweep (% of ECF)",
	"Vendor_Pct_EV": "Vendor Loan (% of EV)",
	"Vendor_Rate": "Vendor Loan Interest Rate",
	"Transaction_Fee_Pct": "Transaction Fees (% of EV)",
	"Financing_Fee_Pct": "Financing Fees (% of EV)",
	"RCF_Limit_X": "RCF Limit (x EBITDA)",
	"RCF_Rate": "RCF Interest Rate",
	"RCF_Commitment_Fee": "RCF Commitment Fee (on Undrawn)",
	"Cash_Rate": "Interest Rate on Cash",
	"Dividend_Pct": "Dividend (% of Free Cash after Sweep)",
	"Tax_Rate": "Corporate Income Tax Rate",
	"SME_Rate_On": "Reduced SME Rate Applies (1 = yes)",
	"SME_Rate": "Reduced SME Rate",
	"SME_Bracket": "Reduced SME Rate Bracket",
	"Interest_Deduct_From": "Interest Deductible from LBO Year",
	"Interest_Cap_EUR": "Interest Limitation: Threshold",
	"Interest_Cap_Pct": "Interest Limitation: % of EBITDA",
	"Goodwill_Life": "Goodwill Amortization Period (Years)",
	"Capex_Life": "Capex Useful Life (Years)",
	"Min_DSCR": "Covenant: Minimum DSCR",
	"Min_ICR": "Covenant: Minimum Interest Coverage Ratio",
	"Max_Leverage": "Covenant: Maximum Net Debt / EBITDA",
	"Target_Leverage": "Target Exit Net Debt / EBITDA",
	"Days_Year": "Days per Year",
	"Days_Week": "Days per Week",
	"Months_Year": "Months per Year",
	"Min_Cash_Months": "Minimum Cash: Months of Personnel Costs",
	"Min_Cash_Weeks": "Minimum Cash: Weeks of Supplier Payments",
	"Min_Cash_Term": "Minimum Cash: Supplier Payment Term (Days)",
	"Goods_Basis": "Goods Cost Basis for DIO (% Revenue)",
	"Purchases_Basis": "Purchases Basis for DPO (% Revenue)",
	"Bank_Excess_Only": "Bank Covenant: Only Cash above Minimum (1 = yes)",
	"Bank_Debt_Like": "Bank Covenant: Include Debt-Like Items (1 = yes)",
	"Val_Excess_Only": "Valuation: Only Cash above Minimum (1 = yes)",
	"Val_Debt_Like": "Valuation: Include Debt-Like Items (1 = yes)",
	"Check_Tolerance": "Check Tolerance (EUR)",
}
TAB_DETAIL = "Full Data Detail"

UNITS_NOTE = "EUR in thousands"
FOOTER_DATE = "Date"
FOOTER_VERSION = "Model version"
FOOTER_GEMINI = "Gemini model"
FOOTER_SOURCE = "Source file"
FOOTER_RUN = "Run manifest"

GROUP_IDENTIFICATION = "IDENTIFICATION & ASSESSMENT"
GROUP_TRENDS = "MULTI-YEAR TREND & MARGINS"
GROUP_BRIDGE = "EV-TO-EQUITY BRIDGE & NWC"
GROUP_RETURNS = "LBO VALUATION & RETURNS (5Y)"
GROUP_SCREENING = "SCREENING CASE (RULE-BASED, NOT YET IN THE ASSESSMENT)"

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
	"LBO_Screening_IRR_Pct": "Screening IRR",
	"LBO_Screening_MoIC": "Screening MoIC",
	"LBO_Screening_Convenanten": "Screening Covenants",
	"LBO_Stress_IRR_Pct": "Stress IRR",
	"LBO_Stress_Laagste_DSCR": "Stress Min. DSCR",
	"LBO_Stress_Convenanten": "Stress Covenants",
	"LBO_Snapshot_Naam": "Assumption Snapshot",
	"LBO_Snapshot_Datum": "Snapshot Date",
	"LBO_Snapshot_Status": "Snapshot Status",
	"Run_Manifest": "Run Manifest",
	"Eigendom": "Ownership",
	"AI_Business_Model": "Business Model (AI)",
	"AI_Investment_Thesis": "Investment Thesis (AI)",
	"AI_DD_Vragen": "Due Diligence Questions (AI)",
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
	"LBO_Assumptie_Bron": "Assumption Source",
	"LBO_Forecast_Groei_Pct": "Forecast Revenue CAGR",
	"LBO_IRR_Exact_Pct": "IRR (Unrounded)",
	"LBO_MoIC_Exact": "MoIC (Unrounded)",
}
