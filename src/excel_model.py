"""The company workbook: a live, formula-driven 3-statement LBO model.

Three tabs: Executive Summary, 3-Statement Model and LBO Analysis. All forecast cells are
Excel formulas that follow lbo_model.py line by line: sweep on excess cash flow, RCF, goodwill,
financing fees and tax rules. Interest runs on opening balances, so there is no circular
reference. The AI proposals are inputs; a user override flows through everything live.

Every row is declared first (key, label, format, formulas) and the row numbers are fixed
before any formula is written, so a formula can name any row on any tab. The returned map
of addresses lets the reconciliation test read the key cells.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from . import assumpties, config, labels
from . import excel_stijl as stijl
from .lbo_model import net_debt_formule

HOOFD = 4  # rows above the data: title, checks, LBO year, fiscal year
ZIJDE_MODEL = "'" + labels.TAB_MODEL + "'!"
ZIJDE_LBO = "'" + labels.TAB_LBO + "'!"
PURE_LINK = re.compile(r"^=-?'[^']+'!\$?[A-Z]+\$?\d+$")
PURE_NAAM = re.compile(r"^=-?[A-Z][A-Za-z]*_[A-Za-z_]+$")  # a named cell, which lives on the LBO tab


class Kolommen:
	"""The same column layout on every tab: label, unit, actuals, closing, five forecast years."""

	def __init__(self, aantal_hist):
		self.hist = list(range(3, 3 + aantal_hist))
		self.closing = 3 + aantal_hist
		self.jaren = list(range(self.closing + 1, self.closing + 1 + assumpties.JAREN))
		self.laatste_jaar = self.jaren[-1]
		self.rationale = self.laatste_jaar + 1
		self.source = self.rationale + 1
		self.confidence = self.source + 1
		self.flag = self.confidence + 1
		self.overrides = self.flag + 1
		self.alle = self.hist + [self.closing] + self.jaren

	def letter(self, kolom):
		return get_column_letter(kolom)


class Ctx:
	"""Cell references for one column, so a formula reads like the Python model."""

	def __init__(self, kol, rijen, blad, kolom, jaar=0):
		self.kol = kol
		self.r = rijen
		self.blad = blad
		self.kolom = kolom
		self.jaar = jaar
		self.k = get_column_letter(kolom)
		self.vk = get_column_letter(kolom - 1)
		self.nul = get_column_letter(kol.closing)
		self.laatste_a = get_column_letter(kol.hist[-1])

	def h(self, sleutel):
		"""This column on this tab."""
		return f"{self.k}{self.r[self.blad][sleutel]}"

	def p(self, sleutel):
		"""Previous column on this tab."""
		return f"{self.vk}{self.r[self.blad][sleutel]}"

	def z(self, sleutel):
		"""The closing column on this tab, fixed."""
		return f"${self.nul}${self.r[self.blad][sleutel]}"

	def a(self, sleutel):
		"""The last actual column on this tab."""
		return f"{self.laatste_a}{self.r[self.blad][sleutel]}"

	def _ander(self, sleutel, kolom):
		if self.blad == "model":
			return f"{ZIJDE_LBO}{kolom}{self.r['lbo'][sleutel]}"
		return f"{ZIJDE_MODEL}{kolom}{self.r['model'][sleutel]}"

	def x(self, sleutel):
		"""This column on the other tab."""
		return self._ander(sleutel, self.k)

	def xp(self, sleutel):
		"""The previous column on the other tab."""
		return self._ander(sleutel, self.vk)

	def xz(self, sleutel):
		"""The closing column on the other tab."""
		return self._ander(sleutel, self.nul)

	def xa(self, sleutel):
		"""The last actual column on the other tab."""
		return self._ander(sleutel, self.laatste_a)


@dataclass
class Rij:
	sleutel: str
	fmt: str = stijl.FMT_BEDRAG
	stijl: str = "normaal"  # normaal, subtotaal or eindtotaal
	hist: Optional[Callable] = None  # value from the historical row: hardcoded, blue
	hist_f: Optional[Callable] = None  # formula in the actual columns
	closing: Optional[Callable] = None
	jaar: Optional[Callable] = None
	label: Optional[str] = None


@dataclass
class Sectie:
	titel: str


def _waarde(regels, sleutel, teken=1):
	waarde = regels.get(sleutel)
	if waarde is None or pd.isna(waarde):
		return None
	return teken * waarde


def _kolom_som(eerste, laatste):
	return lambda c: f"=SUM({c.h(eerste)}:{c.h(laatste)})"


def _rijen_model():
	"""The 3-Statement Model below the assumption block. Costs are negative, as in the statements."""
	def constant(sleutel):
		return lambda c: f"={c.p(sleutel)}"

	def met_omzet(sleutel):
		return lambda c: f"={c.z(sleutel)}*{c.h('rev_ann')}/{c.z('rev_ann')}"

	def mutatie_activa(sleutel):
		return lambda c: f"={c.p(sleutel)}-{c.h(sleutel)}"

	def mutatie_passiva(sleutel):
		return lambda c: f"={c.h(sleutel)}-{c.p(sleutel)}"

	return [
		Sectie(labels.SECTION_BUILD),
		Rij(
			"rev_ann",
			closing=lambda c: f"={c.a('rev')}",
			jaar=lambda c: f"={c.p('rev_ann')}*(1+{c.h('a_volumegroei')})*(1+{c.h('a_prijsgroei')})",
		),
		Rij(
			"pers_ann",
			closing=lambda c: f"=-{c.a('pers')}",
			jaar=lambda c: (
				f"={c.p('pers_ann')}*(1+{c.h('a_volumegroei')}*{c.h('a_vte_elasticiteit')})"
				f"*(1+{c.h('a_loonindexering')})"
			),
		),
		Rij(
			"fte",
			fmt=stijl.FMT_GETAL,
			hist=lambda r: _waarde(r, "VTE"),
			closing=lambda c: f'=IF({c.a("fte")}="","",{c.a("fte")})',
			jaar=lambda c: f'=IF({c.p("fte")}="","",{c.p("fte")}*(1+{c.h("a_volumegroei")}*{c.h("a_vte_elasticiteit")}))',
		),
		Rij(
			"kost_fte",
			hist=lambda r: _waarde(r, "Kost_Per_VTE"),
			jaar=lambda c: f'=IF({c.h("fte")}="","",{c.h("pers_ann")}/{c.h("fte")})',
		),
		Sectie(labels.SECTION_IS),
		Rij("rev", hist=lambda r: _waarde(r, "Omzet"), jaar=lambda c: f"={c.h('rev_ann')}*{c.h('fractie')}"),
		Rij(
			"cogs",
			hist=lambda r: _waarde(r, "Inkoop", -1),
			jaar=lambda c: f"=-{c.h('rev_ann')}*{c.h('a_inkoop_pct')}*{c.h('fractie')}",
		),
		Rij("pers", hist=lambda r: _waarde(r, "Personeel", -1), jaar=lambda c: f"=-{c.h('pers_ann')}*{c.h('fractie')}"),
		Rij(
			"opex",
			hist=lambda r: _waarde(r, "Overige_Kosten", -1),
			jaar=lambda c: f"=-{c.h('rev_ann')}*{c.h('a_overige_kosten_pct')}*{c.h('fractie')}",
		),
		Rij("ebitda", stijl="subtotaal", hist_f=_kolom_som("rev", "opex"), jaar=_kolom_som("rev", "opex")),
		Rij("da", hist=lambda r: _waarde(r, "Afschrijvingen", -1), jaar=lambda c: f"=-{c.h('da_total')}"),
		Rij("gw", jaar=lambda c: f"=-{c.h('gw_amort')}"),
		Rij("nonrec", hist=lambda r: _waarde(r, "Niet_Recurrent", -1)),
		Rij("ebit", stijl="subtotaal", hist_f=_kolom_som("ebitda", "nonrec"), jaar=_kolom_som("ebitda", "nonrec")),
		Rij("int_exp", jaar=lambda c: f"=-{c.x('i_total')}"),
		Rij("fee_am", jaar=lambda c: f"=-{c.h('fee_amort')}"),
		Rij("int_inc", jaar=lambda c: f"={c.x('i_income')}"),
		Rij("fin_res", hist=lambda r: _waarde(r, "Financieel_Resultaat"), jaar=_kolom_som("int_exp", "int_inc")),
		Rij(
			"ebt",
			stijl="subtotaal",
			hist_f=lambda c: f"={c.h('ebit')}+{c.h('fin_res')}",
			jaar=lambda c: f"={c.h('ebit')}+{c.h('fin_res')}",
		),
		Rij("tax", hist=lambda r: _waarde(r, "Belasting", -1), jaar=lambda c: f"=-{c.h('tax_calc')}"),
		Rij(
			"ni",
			stijl="eindtotaal",
			hist_f=lambda c: f"={c.h('ebt')}+{c.h('tax')}",
			jaar=lambda c: f"={c.h('ebt')}+{c.h('tax')}",
		),
		Sectie(labels.SECTION_TAX),
		Rij("fin_cost", jaar=lambda c: f"={c.x('i_total')}+{c.h('fee_amort')}"),
		Rij(
			"deductible",
			jaar=lambda c: (
				f"=IF({c.h('jaar_nr')}<Interest_Deduct_From,0,MIN({c.h('fin_cost')},"
				f"MAX(Interest_Cap_EUR*{c.h('fractie')},{c.h('ebitda')}*Interest_Cap_Pct)+{c.h('int_inc')}))"
			),
		),
		Rij(
			"taxable",
			jaar=lambda c: f"={c.h('ebitda')}-{c.h('da_total')}+{c.h('int_inc')}-{c.h('deductible')}",
		),
		Rij(
			"tax_calc",
			jaar=lambda c: (
				f"=IF({c.h('taxable')}<=0,0,IF(SME_Rate_On=1,MIN({c.h('taxable')},SME_Bracket)*SME_Rate"
				f"+({c.h('taxable')}-MIN({c.h('taxable')},SME_Bracket))*Tax_Rate,{c.h('taxable')}*Tax_Rate))"
			),
		),
		Sectie(labels.SECTION_BS),
		Rij("goodwill", closing=lambda c: "=Goodwill_At_Closing", jaar=lambda c: f"={c.p('goodwill')}-{c.h('gw_amort')}"),
		Rij("fin_fees", closing=lambda c: "=Financing_Fees", jaar=lambda c: f"={c.p('fin_fees')}-{c.h('fee_amort')}"),
		Rij(
			"ppe",
			hist=lambda r: _waarde(r, "Vaste_Activa"),
			closing=lambda c: f"={c.a('ppe')}",
			jaar=lambda c: f"={c.p('ppe')}+{c.h('capex')}-{c.h('da_total')}",
		),
		Rij(
			"fin_fa",
			hist=lambda r: _waarde(r, "Financiele_Vaste_Activa"),
			closing=lambda c: f"={c.a('fin_fa')}",
			jaar=constant("fin_fa"),
		),
		Rij(
			"inv",
			hist=lambda r: _waarde(r, "Voorraden"),
			closing=lambda c: f"={c.a('inv')}",
			jaar=lambda c: f"={c.h('a_dio')}/Days_Year*{c.h('rev_ann')}*Goods_Basis",
		),
		Rij(
			"ar",
			hist=lambda r: _waarde(r, "Handelsvorderingen"),
			closing=lambda c: f"={c.a('ar')}",
			jaar=lambda c: f"={c.h('a_dso')}/Days_Year*{c.h('rev_ann')}",
		),
		Rij(
			"oth_op",
			hist=lambda r: _waarde(r, "Overige_Activa_Operationeel"),
			closing=lambda c: f"={c.a('oth_op')}",
			jaar=met_omzet("oth_op"),
		),
		Rij(
			"oth_nonop",
			hist=lambda r: _waarde(r, "Overige_Activa_Niet_Operationeel"),
			closing=lambda c: f"={c.a('oth_nonop')}-Intercompany_Settled",
			jaar=constant("oth_nonop"),
		),
		Rij(
			"cash",
			hist=lambda r: _waarde(r, "Cash"),
			closing=lambda c: "=Min_Cash",
			jaar=lambda c: f"={c.h('cf_end')}",
		),
		Rij(
			"ta",
			stijl="eindtotaal",
			hist_f=_kolom_som("goodwill", "cash"),
			closing=_kolom_som("goodwill", "cash"),
			jaar=_kolom_som("goodwill", "cash"),
		),
		Rij(
			"equity",
			hist=lambda r: _waarde(r, "Eigen_Vermogen"),
			closing=lambda c: "=Sponsor_Equity",
			jaar=lambda c: f"={c.p('equity')}+{c.h('ni')}-{c.x('w_div')}",
		),
		Rij("exist_debt", hist=lambda r: _waarde(r, "Senior_Lening")),
		Rij("senior", closing=lambda c: f"={c.x('d_senior')}", jaar=lambda c: f"={c.x('d_senior')}"),
		Rij("rcf", closing=lambda c: f"={c.x('d_rcf')}", jaar=lambda c: f"={c.x('d_rcf')}"),
		Rij("vendor", closing=lambda c: f"={c.x('d_vendor')}", jaar=lambda c: f"={c.x('d_vendor')}"),
		Rij(
			"ap",
			hist=lambda r: _waarde(r, "Handelsschulden"),
			closing=lambda c: f"={c.a('ap')}",
			jaar=lambda c: f"={c.h('a_dpo')}/Days_Year*{c.h('rev_ann')}*Purchases_Basis",
		),
		Rij(
			"adv",
			hist=lambda r: _waarde(r, "Vooruitbetalingen"),
			closing=lambda c: f"={c.a('adv')}",
			jaar=lambda c: f"={c.h('a_dagen_vooruitbetaling')}/Days_Year*{c.h('rev_ann')}",
		),
		Rij(
			"soc",
			hist=lambda r: _waarde(r, "Sociale_Schulden"),
			closing=lambda c: f"={c.a('soc')}",
			jaar=lambda c: f"=IF({c.z('pers_ann')}>0,{c.z('soc')}*{c.h('pers_ann')}/{c.z('pers_ann')},{c.z('soc')})",
		),
		Rij(
			"oth_l",
			hist=lambda r: _waarde(r, "Overige_Passiva"),
			closing=lambda c: f"={c.a('oth_l')}-Debt_Like_Items",
			jaar=met_omzet("oth_l"),
		),
		Rij(
			"tl",
			stijl="eindtotaal",
			hist_f=_kolom_som("equity", "oth_l"),
			closing=_kolom_som("equity", "oth_l"),
			jaar=_kolom_som("equity", "oth_l"),
		),
		Rij(
			"bs_check",
			hist_f=lambda c: f"=ABS({c.h('ta')}-{c.h('tl')})",
			closing=lambda c: f"=ABS({c.h('ta')}-{c.h('tl')})",
			jaar=lambda c: f"=ABS({c.h('ta')}-{c.h('tl')})",
		),
		Sectie(labels.SECTION_CF),
		Rij("cf_ni", jaar=lambda c: f"={c.h('ni')}"),
		Rij("cf_da", jaar=lambda c: f"={c.h('da_total')}"),
		Rij("cf_gw", jaar=lambda c: f"={c.h('gw_amort')}"),
		Rij("cf_fee", jaar=lambda c: f"={c.h('fee_amort')}"),
		Rij("cf_inv", jaar=mutatie_activa("inv")),
		Rij("cf_ar", jaar=mutatie_activa("ar")),
		Rij("cf_oth", jaar=mutatie_activa("oth_op")),
		Rij("cf_ap", jaar=mutatie_passiva("ap")),
		Rij("cf_adv", jaar=mutatie_passiva("adv")),
		Rij("cf_soc", jaar=mutatie_passiva("soc")),
		Rij("cf_othl", jaar=mutatie_passiva("oth_l")),
		Rij("cfo", stijl="subtotaal", jaar=_kolom_som("cf_ni", "cf_othl")),
		Rij("cf_capex", jaar=lambda c: f"=-{c.h('capex')}"),
		Rij("cf_pre", stijl="subtotaal", jaar=lambda c: f"={c.h('cfo')}+{c.h('cf_capex')}"),
		Rij("cf_mand", jaar=lambda c: f"=-{c.x('d_mand')}"),
		Rij("cf_sweep", jaar=lambda c: f"=-{c.x('d_sweep')}"),
		Rij("cf_draw", jaar=lambda c: f"={c.x('d_draw')}"),
		Rij("cf_repay", jaar=lambda c: f"=-{c.x('d_repay')}"),
		Rij("cf_div", jaar=lambda c: f"=-{c.x('w_div')}"),
		Rij("cff", stijl="subtotaal", jaar=_kolom_som("cf_mand", "cf_div")),
		Rij("cf_net", stijl="subtotaal", jaar=lambda c: f"={c.h('cf_pre')}+{c.h('cff')}"),
		Rij("cf_open", jaar=lambda c: f"={c.p('cash')}"),
		Rij("cf_end", stijl="eindtotaal", jaar=lambda c: f"={c.h('cf_open')}+{c.h('cf_net')}"),
		Sectie(labels.SECTION_SCHEDULES),
		Rij("capex", hist=lambda r: _waarde(r, "Capex"), jaar=lambda c: f"={c.h('rev')}*{c.h('a_capex_pct')}"),
		Rij(
			"rest",
			closing=lambda c: f"={c.h('ppe')}",
			jaar=lambda c: f"={c.p('rest')}-{c.h('da_exist')}",
		),
		Rij(
			"da_exist",
			jaar=lambda c: f"=MIN({c.p('rest')},{c.z('ppe')}*{c.h('a_da_pct')}*{c.h('fractie')})",
		),
		*[_vintage_rij(jaar) for jaar in range(1, assumpties.JAREN + 1)],
		Rij("da_new", stijl="subtotaal", jaar=_kolom_som("vintage_1", f"vintage_{assumpties.JAREN}")),
		Rij("da_total", stijl="subtotaal", jaar=lambda c: f"={c.h('da_exist')}+{c.h('da_new')}"),
		Rij(
			"gw_amort",
			jaar=lambda c: f"=MIN(MAX({c.p('goodwill')},0),MAX({c.z('goodwill')},0)/Goodwill_Life*{c.h('fractie')})",
		),
		Rij(
			"fee_amort",
			jaar=lambda c: f"=MIN({c.p('fin_fees')},{c.z('fin_fees')}/Senior_Tenor*{c.h('fractie')})",
		),
		Sectie(labels.SECTION_CHECKS),
		Rij("check_cash", jaar=lambda c: f"=ABS({c.h('cf_end')}-{c.x('w_end')})"),
		Rij(
			"senior_rebuilt",
			closing=lambda c: f"={c.xz('d_senior')}",
			jaar=lambda c: f"={c.p('senior_rebuilt')}-{c.x('d_mand')}-{c.x('d_sweep')}",
		),
		Rij(
			"rcf_rebuilt",
			closing=lambda c: f"={c.xz('d_rcf')}",
			jaar=lambda c: f"={c.p('rcf_rebuilt')}+{c.x('d_draw')}-{c.x('d_repay')}",
		),
		Rij(
			"check_debt",
			closing=lambda c: f"=ABS({c.h('senior_rebuilt')}-{c.h('senior')})+ABS({c.h('rcf_rebuilt')}-{c.h('rcf')})",
			jaar=lambda c: f"=ABS({c.h('senior_rebuilt')}-{c.h('senior')})+ABS({c.h('rcf_rebuilt')}-{c.h('rcf')})",
		),
	]


def _vintage_rij(vintage):
	"""Straight-line D&A of the capex of one year, from the year of purchase, never above its cost."""
	def formule(c):
		if c.jaar < vintage:
			return None
		bron = f"${get_column_letter(c.kol.jaren[vintage - 1])}{c.r['model']['capex']}"
		sleutel = f"vintage_{vintage}"
		grens = f"{bron}/Capex_Life*{c.h('fractie')}"
		if c.jaar == vintage:
			return f"=MIN({bron},{grens})"
		eerste = f"${get_column_letter(c.kol.jaren[vintage - 1])}{c.r['model'][sleutel]}"
		return f"=MIN({bron}-SUM({eerste}:{c.p(sleutel)}),{grens})"

	return Rij(f"vintage_{vintage}", jaar=formule, label=labels.ROW_LABELS["vintage"].format(year=vintage))


def _rijen_lbo():
	"""Debt schedule, waterfall, covenants and returns of the LBO Analysis, year by year."""
	return [
		Sectie(labels.SECTION_DEBT),
		Rij("d_senior_open", jaar=lambda c: f"={c.p('d_senior')}"),
		Rij(
			"d_mand",
			jaar=lambda c: f"=MIN({c.h('d_senior_open')},{c.z('d_senior')}/Senior_Tenor*{c.x('fractie')})",
		),
		Rij("d_sweep", jaar=lambda c: f"={c.h('w_sweep')}"),
		Rij(
			"d_senior",
			stijl="subtotaal",
			closing=lambda c: "=Senior_Amount",
			jaar=lambda c: f"=MAX(0,{c.h('d_senior_open')}-{c.h('d_mand')}-{c.h('d_sweep')})",
		),
		Rij("d_rcf_open", jaar=lambda c: f"={c.p('d_rcf')}"),
		Rij("d_draw", jaar=lambda c: f"={c.h('w_draw')}"),
		Rij("d_repay", jaar=lambda c: f"={c.h('w_repay')}"),
		Rij(
			"d_rcf",
			stijl="subtotaal",
			closing=lambda c: "=RCF_At_Closing",
			jaar=lambda c: f"=MAX(0,{c.h('d_rcf_open')}+{c.h('d_draw')}-{c.h('d_repay')})",
		),
		Rij("d_rcf_room", jaar=lambda c: f"=RCF_Limit-{c.h('d_rcf')}"),
		Rij(
			"d_vendor",
			stijl="subtotaal",
			closing=lambda c: "=Vendor_Amount",
			jaar=lambda c: f"={c.p('d_vendor')}",
		),
		Sectie(labels.SECTION_INTEREST),
		Rij("i_senior", jaar=lambda c: f"={c.h('d_senior_open')}*Senior_Rate*{c.x('fractie')}"),
		Rij("i_rcf", jaar=lambda c: f"={c.h('d_rcf_open')}*RCF_Rate*{c.x('fractie')}"),
		Rij("i_commit", jaar=lambda c: f"=(RCF_Limit-{c.h('d_rcf_open')})*RCF_Commitment_Fee*{c.x('fractie')}"),
		Rij("i_vendor", jaar=lambda c: f"={c.p('d_vendor')}*Vendor_Rate*{c.x('fractie')}"),
		Rij("i_total", stijl="subtotaal", jaar=_kolom_som("i_senior", "i_vendor")),
		Rij("i_income", jaar=lambda c: f"=MAX({c.h('w_open')},0)*Cash_Rate*{c.x('fractie')}"),
		Sectie(labels.SECTION_WATERFALL),
		Rij("w_ebitda", jaar=lambda c: f"={c.x('ebitda')}"),
		Rij("w_tax", jaar=lambda c: f"={c.x('tax')}"),
		Rij("w_capex", jaar=lambda c: f"=-{c.x('capex')}"),
		Rij(
			"w_twc",
			jaar=lambda c: f"={c.x('cf_inv')}+{c.x('cf_ar')}+{c.x('cf_ap')}+{c.x('cf_adv')}",
		),
		Rij("w_oth", jaar=lambda c: f"={c.x('cf_oth')}+{c.x('cf_soc')}+{c.x('cf_othl')}"),
		Rij("w_int", jaar=lambda c: f"=-{c.h('i_total')}"),
		Rij("w_inc", jaar=lambda c: f"={c.h('i_income')}"),
		Rij("w_fcf", stijl="subtotaal", jaar=_kolom_som("w_ebitda", "w_inc")),
		Rij("w_mand", jaar=lambda c: f"=-{c.h('d_mand')}"),
		Rij("w_ecf", stijl="subtotaal", jaar=lambda c: f"={c.h('w_fcf')}+{c.h('w_mand')}"),
		Rij("w_open", jaar=lambda c: f"={c.xp('cash')}"),
		Rij("w_pos", jaar=lambda c: f"={c.h('w_open')}+{c.h('w_ecf')}-Min_Cash"),
		Rij("w_draw", jaar=lambda c: f"=MIN(MAX(0,-{c.h('w_pos')}),RCF_Limit-{c.h('d_rcf_open')})"),
		Rij("w_repay", jaar=lambda c: f"=MIN(MAX(0,{c.h('w_pos')}),{c.h('d_rcf_open')})"),
		Rij(
			"w_sweep",
			jaar=lambda c: (
				f"=MIN(MAX(0,{c.h('w_ecf')}-{c.h('w_repay')})*Cash_Sweep_Pct,"
				f"MAX(0,{c.h('w_pos')}-{c.h('w_repay')}),{c.h('d_senior_open')}-{c.h('d_mand')})"
			),
		),
		Rij(
			"w_vrij",
			jaar=lambda c: f"=MIN({c.h('w_ecf')},{c.h('w_pos')})-{c.h('w_repay')}-{c.h('w_sweep')}",
		),
		Rij("w_res", jaar=lambda c: f"=MAX(0,{c.p('res_close')}+{c.x('ni')})"),
		Rij(
			"w_div",
			jaar=lambda c: (
				f"=IF({c.h('d_rcf')}=0,MIN(MAX(0,{c.h('w_vrij')})*Dividend_Pct,{c.h('w_res')}),0)"
			),
		),
		Rij(
			"w_end",
			stijl="eindtotaal",
			jaar=lambda c: (
				f"={c.h('w_open')}+{c.h('w_ecf')}+{c.h('w_draw')}-{c.h('w_repay')}-{c.h('w_sweep')}-{c.h('w_div')}"
			),
		),
		Rij(
			"res_close",
			closing=lambda c: 0,
			jaar=lambda c: f"={c.p('res_close')}+{c.x('ni')}-{c.h('w_div')}",
		),
		Sectie(labels.SECTION_COVENANTS),
		Rij(
			"c_icr",
			fmt=stijl.FMT_MULT_2,
			jaar=lambda c: f'=IF({c.h("i_total")}>0,{c.h("w_ebitda")}/{c.h("i_total")},"")',
		),
		Rij("c_icr_min", fmt=stijl.FMT_MULT_2, jaar=lambda c: "=Min_ICR"),
		Rij("c_icr_room", fmt=stijl.FMT_MULT_2, jaar=lambda c: f'=IF({c.h("c_icr")}="","",{c.h("c_icr")}-{c.h("c_icr_min")})'),
		Rij(
			"c_dscr",
			fmt=stijl.FMT_MULT_2,
			jaar=lambda c: (
				f'=IF({c.h("i_total")}+{c.h("d_mand")}>0,({c.h("w_ebitda")}+{c.h("w_capex")}+{c.h("w_tax")})'
				f'/({c.h("i_total")}+{c.h("d_mand")}),"")'
			),
		),
		Rij("c_dscr_min", fmt=stijl.FMT_MULT_2, jaar=lambda c: "=Min_DSCR"),
		Rij("c_dscr_room", fmt=stijl.FMT_MULT_2, jaar=lambda c: f'=IF({c.h("c_dscr")}="","",{c.h("c_dscr")}-{c.h("c_dscr_min")})'),
		Rij(
			"nd_bank",
			closing=lambda c: _net_debt_formule(c, "Bank"),
			jaar=lambda c: _net_debt_formule(c, "Bank"),
		),
		Rij(
			"nd_val",
			closing=lambda c: _net_debt_formule(c, "Val"),
			jaar=lambda c: _net_debt_formule(c, "Val"),
		),
		Rij(
			"c_lev",
			fmt=stijl.FMT_MULT_2,
			jaar=lambda c: (
				f'=IF({c.h("w_ebitda")}/{c.x("fractie")}>0,{c.h("nd_bank")}/({c.h("w_ebitda")}/{c.x("fractie")}),"")'
			),
		),
		Rij("c_lev_max", fmt=stijl.FMT_MULT_2, jaar=lambda c: "=Max_Leverage"),
		Rij("c_lev_room", fmt=stijl.FMT_MULT_2, jaar=lambda c: f'=IF({c.h("c_lev")}="","",{c.h("c_lev_max")}-{c.h("c_lev")})'),
		Rij(
			"c_status",
			fmt="@",
			jaar=lambda c: (
				f'=IF(OR({c.h("w_ebitda")}<=0,N({c.h("c_icr_room")})<0,N({c.h("c_dscr_room")})<0,N({c.h("c_lev_room")})<0),'
				f'"{labels.COVENANTS_BREACHED}","{labels.COVENANTS_OK}")'
			),
		),
	]


def _net_debt_formule(c, doel):
	"""Same definitions as lbo_model.net_debt: the two switches come from config."""
	cash = c.x("cash")
	return (
		f"={c.h('d_senior')}+{c.h('d_rcf')}+{c.h('d_vendor')}-IF({doel}_Excess_Only=1,{cash}-Min_Cash,{cash})"
	)


def _invoer(rij):
	"""The transaction inputs: (name, value, format). All are blue, all live."""
	bank = config.NET_DEBT_DEFINITIES["bank_covenant"]
	waardering = config.NET_DEBT_DEFINITIES["waardering"]
	return [
		("Entry_Multiple", float(rij["Instap_Multiple"]), stijl.FMT_MULT),
		("Exit_Multiple", float(rij["Instap_Multiple"]), stijl.FMT_MULT),
		("Senior_Multiple", float(rij["Senior_Multiple"]), stijl.FMT_MULT),
		("Senior_Rate", config.LBO_SENIOR_RENTE, stijl.FMT_PCT),
		("Senior_Tenor", config.LBO_SENIOR_LOOPTIJD_JAAR, stijl.FMT_GETAL),
		("Cash_Sweep_Pct", config.LBO_CASH_SWEEP_PCT, stijl.FMT_PCT),
		("Vendor_Pct_EV", config.LBO_VENDOR_LOAN_PCT_EV, stijl.FMT_PCT),
		("Vendor_Rate", config.LBO_VENDOR_LOAN_RENTE, stijl.FMT_PCT),
		("Transaction_Fee_Pct", config.LBO_TRANSACTIEKOSTEN_PCT, stijl.FMT_PCT),
		("Financing_Fee_Pct", config.LBO_FINANCIERINGSKOSTEN_PCT, stijl.FMT_PCT),
		("RCF_Limit_X", config.LBO_RCF_LIMIET_X_EBITDA, stijl.FMT_MULT),
		("RCF_Rate", config.LBO_RCF_RENTE, stijl.FMT_PCT),
		("RCF_Commitment_Fee", config.LBO_RCF_COMMITMENT_FEE, "0.00%"),
		("Cash_Rate", config.LBO_CASH_RENTE, stijl.FMT_PCT),
		("Dividend_Pct", config.LBO_DIVIDEND_PCT, stijl.FMT_PCT),
		("Tax_Rate", config.LBO_TAX_RATE, stijl.FMT_PCT),
		("SME_Rate_On", 1 if config.LBO_KMO_TARIEF_TOEPASSEN else 0, "0"),
		("SME_Rate", config.LBO_KMO_TARIEF, stijl.FMT_PCT),
		("SME_Bracket", config.LBO_KMO_SCHIJF, stijl.FMT_BEDRAG),
		("Interest_Deduct_From", config.LBO_RENTEAFTREK_VANAF_JAAR, "0"),
		("Interest_Cap_EUR", config.LBO_RENTEAFTREK_DREMPEL_EUR, stijl.FMT_BEDRAG),
		("Interest_Cap_Pct", config.LBO_RENTEAFTREK_EBITDA_PCT, stijl.FMT_PCT),
		("Goodwill_Life", config.LBO_GOODWILL_LOOPTIJD_JAAR, stijl.FMT_GETAL),
		("Capex_Life", config.LBO_CAPEX_LEVENSDUUR_JAAR, stijl.FMT_GETAL),
		("Min_DSCR", config.LBO_COVENANT_MIN_DSCR, stijl.FMT_MULT_2),
		("Min_ICR", config.LBO_COVENANT_MIN_RENTEDEKKING, stijl.FMT_MULT_2),
		("Max_Leverage", config.LBO_COVENANT_MAX_LEVERAGE, stijl.FMT_MULT_2),
		("Target_Leverage", config.LBO_TARGET_END_LEVERAGE, stijl.FMT_MULT_2),
		("Days_Year", config.DAGEN_PER_JAAR, "0"),
		("Days_Week", 7, "0"),
		("Months_Year", 12, "0"),
		("Min_Cash_Months", config.MIN_CASH_MAANDEN_PERSONEEL, stijl.FMT_GETAL),
		("Min_Cash_Weeks", config.MIN_CASH_WEKEN_LEVERANCIERS, stijl.FMT_GETAL),
		("Min_Cash_Term", config.MIN_CASH_BETAALTERMIJN_DAGEN, stijl.FMT_GETAL),
		("Goods_Basis", rij["Driver_Kosten_60_Pct"] / 100, stijl.FMT_PCT),
		("Purchases_Basis", rij["Driver_Kosten_6061_Pct"] / 100, stijl.FMT_PCT),
		("Bank_Excess_Only", 1 if bank["alleen_cash_boven_minimum"] else 0, "0"),
		("Bank_Debt_Like", 1 if bank["debt_like_meetellen"] else 0, "0"),
		("Val_Excess_Only", 1 if waardering["alleen_cash_boven_minimum"] else 0, "0"),
		("Val_Debt_Like", 1 if waardering["debt_like_meetellen"] else 0, "0"),
		("Check_Tolerance", 1, "0"),
	]


def _enkelvoudig_lbo(rij):
	"""Single-value blocks of the LBO tab: (key, name, kind, content, format, style, section)."""
	return [
		("entry_ebitda", "Entry_EBITDA", "f", lambda c: f"={c.xa('ebitda')}", stijl.FMT_BEDRAG, "normaal"),
		("entry_ev", "Entry_EV", "f", lambda c: "=Entry_EBITDA*Entry_Multiple", stijl.FMT_BEDRAG, "subtotaal"),
		("fin_debt", "Financial_Debt", "f", lambda c: f"={c.xa('exist_debt')}", stijl.FMT_BEDRAG, "normaal"),
		("cash_br", "Cash_At_Signing", "i", float(rij["Liquide_Middelen"]), stijl.FMT_BEDRAG, "normaal"),
		("debt_like", "Debt_Like_Items", "i", float(rij["Debt_Like_Items"]), stijl.FMT_BEDRAG, "normaal"),
		("ic_cash", "Intercompany_Settled", "i", float(rij["Intercompany_Cash_Like"]), stijl.FMT_BEDRAG, "normaal"),
		(
			"min_req", "Min_Cash_Requirement", "f",
			lambda c: (
				f"=-{c.xa('pers')}*Min_Cash_Months/Months_Year+{c.xa('ap')}*Min_Cash_Weeks*Days_Week/Min_Cash_Term"
			),
			stijl.FMT_BEDRAG, "normaal",
		),
		("min_cash", "Min_Cash", "f", lambda c: "=MAX(0,MIN(Min_Cash_Requirement,Cash_At_Signing))", stijl.FMT_BEDRAG, "normaal"),
		(
			"net_debt_0", "Net_Debt_Target", "f",
			lambda c: (
				"=Financial_Debt+IF(Bank_Debt_Like=1,Debt_Like_Items,0)"
				"-IF(Bank_Excess_Only=1,Cash_At_Signing-Min_Cash,Cash_At_Signing)"
			),
			stijl.FMT_BEDRAG, "normaal",
		),
		(
			"adj_nd", "Adjusted_Net_Debt", "f",
			lambda c: (
				"=Financial_Debt+IF(Val_Debt_Like=1,Debt_Like_Items,0)"
				"-IF(Val_Excess_Only=1,Cash_At_Signing-Min_Cash,Cash_At_Signing)-Intercompany_Settled"
			),
			stijl.FMT_BEDRAG, "subtotaal",
		),
		("eq_price", "Equity_Purchase_Price", "f", lambda c: "=Entry_EV-Adjusted_Net_Debt", stijl.FMT_BEDRAG, "eindtotaal"),
	]


def _bronnen_gebruik():
	return [
		("s_senior", "Senior_Amount", "f", lambda c: "=Entry_EBITDA*Senior_Multiple", stijl.FMT_BEDRAG, "normaal"),
		("s_vendor", "Vendor_Amount", "f", lambda c: "=Entry_EV*Vendor_Pct_EV", stijl.FMT_BEDRAG, "normaal"),
		("s_rcf", "RCF_At_Closing", "i", 0, stijl.FMT_BEDRAG, "normaal"),
		(
			"s_equity", "Sponsor_Equity", "f",
			lambda c: "=Entry_EV+Transaction_Fees+Financing_Fees-Senior_Amount-Vendor_Amount-RCF_At_Closing",
			stijl.FMT_BEDRAG, "normaal",
		),
		("s_total", "Total_Sources", "f", lambda c: "=Senior_Amount+Vendor_Amount+RCF_At_Closing+Sponsor_Equity", stijl.FMT_BEDRAG, "eindtotaal"),
		("u_equity", "Uses_Equity", "f", lambda c: "=Equity_Purchase_Price", stijl.FMT_BEDRAG, "normaal"),
		("u_debt", "Uses_Debt", "f", lambda c: "=Adjusted_Net_Debt", stijl.FMT_BEDRAG, "normaal"),
		("u_trans", "Transaction_Fees", "f", lambda c: "=Entry_EV*Transaction_Fee_Pct", stijl.FMT_BEDRAG, "normaal"),
		("u_fin", "Financing_Fees", "f", lambda c: "=Entry_EV*Financing_Fee_Pct", stijl.FMT_BEDRAG, "normaal"),
		("u_total", "Total_Uses", "f", lambda c: "=Uses_Equity+Uses_Debt+Transaction_Fees+Financing_Fees", stijl.FMT_BEDRAG, "eindtotaal"),
		("su_check", "SU_Check", "f", lambda c: "=ABS(Total_Sources-Total_Uses)", stijl.FMT_BEDRAG, "normaal"),
		(
			"goodwill_0", "Goodwill_At_Closing", "f",
			lambda c: (
				"=Entry_EV+Transaction_Fees-("
				+ "+".join(c.xz(sleutel) for sleutel in ("ppe", "fin_fa", "inv", "ar", "oth_op", "oth_nonop"))
				+ "+Min_Cash-"
				+ "-".join(c.xz(sleutel) for sleutel in ("ap", "adv", "soc", "oth_l"))
				+ ")"
			),
			stijl.FMT_BEDRAG, "normaal",
		),
		("rcf_limit", "RCF_Limit", "f", lambda c: "=Entry_EBITDA*RCF_Limit_X", stijl.FMT_BEDRAG, "normaal"),
	]


class Bouwer:
	"""Writes one company workbook. The row numbers are known before any formula is written."""

	def __init__(self, rij, historiek):
		self.rij = rij
		self.historiek = historiek[-config.LBO_MAX_JAREN:]
		self.kol = Kolommen(len(self.historiek))
		self.pack = rij["LBO_Assumpties"]
		self.r = {"model": {}, "lbo": {}}
		self.namen = {}
		self.wb = Workbook()
		self.ws_samenvatting = self.wb.active
		self.ws_samenvatting.title = labels.TAB_SUMMARY
		self.ws_model = self.wb.create_sheet(labels.TAB_MODEL)
		self.ws_lbo = self.wb.create_sheet(labels.TAB_LBO)
		self.override_cellen = []

	# ------------------------------------------------------------------ row layout
	def _plan_model(self):
		rij_nr = HOOFD + 1
		self.scenario_rij = rij_nr + 1
		rij_nr += 8  # section, selector, index, three-line legend and a blank line
		self.r["model"]["jaar_nr"] = rij_nr + 1
		self.r["model"]["einde"] = rij_nr + 2
		self.r["model"]["fractie"] = rij_nr + 3
		rij_nr += 5
		self.ai_blokken = {}
		for scenario in assumpties.MODEL_SCENARIOS:
			self.ai_blokken[scenario] = rij_nr
			rij_nr += 1
			for driver in assumpties.DRIVERS:
				self.r["model"][f"ai_{scenario}_{driver.sleutel}"] = rij_nr
				self.r["model"][f"ov_{scenario}_{driver.sleutel}"] = rij_nr + 1
				self.r["model"][f"u_{scenario}_{driver.sleutel}"] = rij_nr + 2
				rij_nr += 3
			rij_nr += 1
		self.actief_blok = rij_nr
		rij_nr += 1
		for driver in assumpties.DRIVERS:
			self.r["model"][f"a_{driver.sleutel}"] = rij_nr
			rij_nr += 1
		self.r["model"]["a_groei"] = rij_nr
		self.r["model"]["a_marge"] = rij_nr + 1
		rij_nr += 3

		self.model_specs = _rijen_model()
		self.model_start = rij_nr
		for spec in self.model_specs:
			if isinstance(spec, Sectie):
				rij_nr += 1
				spec_rij = rij_nr
				rij_nr += 1
				self.r["model"][f"sectie_{spec.titel}"] = spec_rij
			else:
				self.r["model"][spec.sleutel] = rij_nr
				rij_nr += 1
		self.model_einde = rij_nr

	def _plan_lbo(self):
		rij_nr = HOOFD + 2
		self.invoer = _invoer(self.rij)
		self.invoer_start = rij_nr
		for naam, _, _ in self.invoer:
			self.namen[naam] = f"{ZIJDE_LBO}$C${rij_nr}"
			rij_nr += 1
		rij_nr += 1
		self.brug = _enkelvoudig_lbo(self.rij)
		self.brug_start = rij_nr
		rij_nr += 1
		for sleutel, naam, *_ in self.brug:
			self.r["lbo"][f"{sleutel}_rij"] = rij_nr
			self.namen[naam] = f"{ZIJDE_LBO}$C${rij_nr}"
			rij_nr += 1
		rij_nr += 1
		self.su = _bronnen_gebruik()
		self.su_start = rij_nr
		rij_nr += 1
		for sleutel, naam, *_ in self.su:
			self.r["lbo"][f"{sleutel}_rij"] = rij_nr
			self.namen[naam] = f"{ZIJDE_LBO}$C${rij_nr}"
			rij_nr += 1

		self.lbo_specs = _rijen_lbo()
		for spec in self.lbo_specs:
			if isinstance(spec, Sectie):
				rij_nr += 1
				self.r["lbo"][f"sectie_{spec.titel}"] = rij_nr
				rij_nr += 1
			else:
				self.r["lbo"][spec.sleutel] = rij_nr
				rij_nr += 1
		rij_nr += 1
		self.exit_start = rij_nr
		rij_nr += 1
		for sleutel in (
			"x_ebitda", "x_mult", "x_ev", "x_nd", "x_equity", "x_lev", "x_duration", "x_dates", "x_flows", "x_irr", "x_moic",
			"x_covenants", "x_peak_lev", "x_min_dscr",
		):
			self.r["lbo"][sleutel] = rij_nr
			rij_nr += 1
		self.lbo_einde = rij_nr

	# ------------------------------------------------------------------ cell helpers
	def _zet(self, ws, rij, kolom, waarde, fmt=None, soort=None, vet=False):
		"""Writes a cell. Blue input, black formula, green link: decided by the content."""
		if waarde is None:
			return None
		cel = ws.cell(row=rij, column=kolom, value=waarde)
		if soort is None:
			if isinstance(waarde, str) and waarde.startswith("="):
				andere_tab = ws is not self.ws_lbo and PURE_NAAM.match(waarde)
				soort = "link" if PURE_LINK.match(waarde) or andere_tab else "formule"
			else:
				soort = "invoer"
		kleur = {"invoer": stijl.BLAUW, "formule": stijl.ZWART, "link": stijl.GROEN, "tekst": stijl.ZWART}[soort]
		cel.font = stijl.lettertype(kleur, vet=vet)
		if fmt:
			cel.number_format = fmt
		if soort != "tekst":
			cel.alignment = Alignment(horizontal="right", vertical="center")
		return cel

	def _label(self, ws, rij, tekst, eenheid=None, vet=False):
		cel = ws.cell(row=rij, column=1, value=tekst)
		cel.font = stijl.lettertype(vet=vet)
		cel.alignment = Alignment(vertical="center")
		if eenheid:
			ws.cell(row=rij, column=2, value=eenheid).font = stijl.lettertype(cursief=True)

	def _sectie(self, ws, rij, titel, tot=None):
		for kolom in range(1, (tot or self.kol.laatste_jaar) + 1):
			stijl.sectiekop(ws.cell(row=rij, column=kolom))
		ws.cell(row=rij, column=1, value=titel)

	def _rij_stijl(self, ws, rij, soort, tot=None):
		if soort == "normaal":
			return
		rand = stijl.RAND_SUBTOTAAL if soort == "subtotaal" else stijl.RAND_EINDTOTAAL
		for kolom in range(1, (tot or self.kol.laatste_jaar) + 1):
			huidig = ws.cell(row=rij, column=kolom)
			huidig.border = rand
			if huidig.value is not None:
				huidig.font = stijl.lettertype(huidig.font.color.rgb[-6:], vet=True)

	def _grijs(self, ws, rij):
		for kolom in self.kol.hist:
			ws.cell(row=rij, column=kolom).fill = stijl.VUL_ACTUAL

	def _ctx(self, blad, kolom, jaar=0):
		return Ctx(self.kol, self.r, blad, kolom, jaar)

	def _kop(self, ws, titel, blad):
		"""Title, checks row, LBO year and fiscal year: the same on every tab."""
		tot = self.kol.laatste_jaar
		for kolom in range(1, (self.kol.overrides if blad == "model" else tot) + 1):
			stijl.sectiekop(ws.cell(row=1, column=kolom))
		ws.cell(row=1, column=1, value=f"{titel}: {self.rij['Bedrijfsnaam']}   ({labels.UNITS_NOTE})")

		eerste = get_column_letter(self.kol.hist[0])
		laatste = get_column_letter(tot)
		rm = self.r["model"]
		tol = "Check_Tolerance"
		checks = [
			(labels.TEST_BALANCE[0], f'MAX({ZIJDE_MODEL}{eerste}{rm["bs_check"]}:{laatste}{rm["bs_check"]})<{tol}'),
			(labels.TEST_CASH[0], f'MAX({ZIJDE_MODEL}{eerste}{rm["check_cash"]}:{laatste}{rm["check_cash"]})<{tol}'),
			(labels.TEST_DEBT[0], f'MAX({ZIJDE_MODEL}{eerste}{rm["check_debt"]}:{laatste}{rm["check_debt"]})<{tol}'),
			(labels.TEST_SOURCES[0], f"SU_Check<{tol}"),
		]
		ws.cell(row=2, column=1, value=labels.CHECKS_TOTAL).font = stijl.lettertype(vet=True)
		cellen = []
		for index, (label, test) in enumerate(checks):
			kolom = 3 + 2 * index
			ws.cell(row=2, column=kolom, value=label).font = stijl.lettertype(grootte=8)
			ws.cell(row=2, column=kolom).alignment = Alignment(wrap_text=True, vertical="center")
			cel = ws.cell(row=2, column=kolom + 1, value=f'=IF({test},"{labels.CHECK_OK}","{labels.CHECK_ERROR}")')
			cel.font = stijl.lettertype()
			cel.alignment = Alignment(horizontal="center", vertical="center")
			cellen.append(cel.coordinate)
		# The total sits in the frozen column, so it stays visible while scrolling
		totaal = ws.cell(
			row=2,
			column=2,
			value='=IF(AND(' + ",".join(f'{cel}="{labels.CHECK_OK}"' for cel in cellen) + f'),"{labels.CHECK_OK}","{labels.CHECK_ERROR}")',
		)
		totaal.font = stijl.lettertype(vet=True)
		totaal.alignment = Alignment(horizontal="center", vertical="center")
		cellen.append(totaal.coordinate)
		self.checks_totaal = totaal.coordinate
		groen = stijl.PatternFill("solid", bgColor=stijl.VULLING_OK)
		rood = stijl.PatternFill("solid", bgColor=stijl.VULLING_FOUT)
		for cel in cellen:
			ws.conditional_formatting.add(cel, CellIsRule(operator="equal", formula=[f'"{labels.CHECK_OK}"'], fill=groen, font=stijl.lettertype(stijl.GROEN, vet=True)))
			ws.conditional_formatting.add(cel, CellIsRule(operator="notEqual", formula=[f'"{labels.CHECK_OK}"'], fill=rood, font=stijl.lettertype(stijl.ROOD, vet=True)))
		ws.row_dimensions[2].height = 26

		ws.cell(row=3, column=1, value=labels.HEADER_LBO_YEAR).font = stijl.lettertype(vet=True)
		ws.cell(row=4, column=1, value=labels.HEADER_FISCAL_YEAR).font = stijl.lettertype(vet=True)
		for index, kolom_nr in enumerate(self.kol.hist):
			ws.cell(row=3, column=kolom_nr, value=labels.HEADER_ACTUAL)
			ws.cell(row=4, column=kolom_nr, value=self.historiek[index]["Label"])
		ws.cell(row=3, column=self.kol.closing, value="Year 0")
		ws.cell(row=4, column=self.kol.closing, value=labels.LABEL_CLOSING)
		for jaar, kolom_nr in enumerate(self.kol.jaren, start=1):
			ws.cell(row=3, column=kolom_nr, value=f"Year {jaar}")
			ws.cell(row=4, column=kolom_nr, value=self.rij["LBO_Jaren"][jaar]["Label"])
		for rij_nr in (3, 4):
			for kolom_nr in self.kol.alle:
				cel = ws.cell(row=rij_nr, column=kolom_nr)
				cel.font = stijl.lettertype(vet=True)
				cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
				if rij_nr == 4:
					cel.border = stijl.RAND_SUBTOTAAL
			self._grijs(ws, rij_nr)

		ws.sheet_view.showGridLines = False
		ws.freeze_panes = ws.cell(row=HOOFD + 1, column=2)
		ws.column_dimensions["A"].width = 52
		ws.column_dimensions["B"].width = 7
		for kolom_nr in self.kol.alle:
			ws.column_dimensions[get_column_letter(kolom_nr)].width = 13

	def _voet(self, ws, rij):
		regels = [
			(labels.FOOTER_DATE, datetime.now().strftime("%Y-%m-%d %H:%M")),
			(labels.FOOTER_VERSION, config.MODEL_VERSIE),
			(labels.FOOTER_GEMINI, self.rij["Gebruikt_Model"] or "-"),
			(labels.FOOTER_SOURCE, self.rij["Bronbestand"]),
			(labels.FOOTER_RUN, self.rij.get("Run_Manifest", "-")),
		]
		for verschuiving, (label, waarde) in enumerate(regels):
			ws.cell(row=rij + verschuiving, column=1, value=label).font = stijl.lettertype(vet=True, grootte=8)
			ws.cell(row=rij + verschuiving, column=3, value=waarde).font = stijl.lettertype(grootte=8)

	def _schrijf_rijen(self, ws, specs, blad):
		for spec in specs:
			if isinstance(spec, Sectie):
				self._sectie(ws, self.r[blad][f"sectie_{spec.titel}"], spec.titel)
				continue
			nr = self.r[blad][spec.sleutel]
			self._label(ws, nr, spec.label or labels.ROW_LABELS[spec.sleutel], vet=spec.stijl != "normaal")
			for index, kolom in enumerate(self.kol.hist):
				waarde = None
				if spec.hist:
					waarde = spec.hist(self.historiek[index])
				elif spec.hist_f:
					waarde = spec.hist_f(self._ctx(blad, kolom))
				self._zet(ws, nr, kolom, waarde, spec.fmt)
			if spec.closing:
				self._zet(ws, nr, self.kol.closing, spec.closing(self._ctx(blad, self.kol.closing)), spec.fmt)
			if spec.jaar:
				for jaar, kolom in enumerate(self.kol.jaren, start=1):
					self._zet(ws, nr, kolom, spec.jaar(self._ctx(blad, kolom, jaar)), spec.fmt)
			self._grijs(ws, nr)
			self._rij_stijl(ws, nr, spec.stijl)

	# ------------------------------------------------------------------ assumption block
	def _driver_fmt(self, driver):
		return {"pct": stijl.FMT_PCT, "factor": stijl.FMT_INDEX, "dagen": stijl.FMT_DAGEN}[driver.eenheid]

	def _driver_waarde(self, driver, waarde):
		"""Percentages go into Excel as fractions (0.05), or the formulas would not work."""
		return waarde / 100 if driver.eenheid == "pct" else waarde

	def _schrijf_scenariokiezer(self, ws):
		nr = HOOFD + 1
		self._sectie(ws, nr, labels.SECTION_SCENARIO, self.kol.overrides)
		namen = [assumpties.scenario_label(scenario) for scenario in assumpties.MODEL_SCENARIOS]

		self._label(ws, self.scenario_rij, labels.SCENARIO_SELECT, vet=True)
		kiezer = ws.cell(row=self.scenario_rij, column=3, value=namen[0])
		kiezer.font = stijl.lettertype(stijl.BLAUW, vet=True)
		kiezer.fill = stijl.VUL_OVERRIDE
		kiezer.border = stijl.RAND_OVERRIDE
		kiezer.alignment = Alignment(horizontal="center")
		keuzelijst = DataValidation(type="list", formula1='"' + ",".join(namen) + '"', allow_blank=False)
		ws.add_data_validation(keuzelijst)
		keuzelijst.add(kiezer)
		self.namen["Scenario"] = f"{ZIJDE_MODEL}$C${self.scenario_rij}"

		lijst_rij = self.scenario_rij + 1
		self._label(ws, lijst_rij, labels.SCENARIO_LIST)
		for index, naam in enumerate(namen):
			self._zet(ws, lijst_rij, 3 + index, naam)
		laatste = get_column_letter(2 + len(namen))
		self.namen["Scenario_List"] = f"{ZIJDE_MODEL}$C${lijst_rij}:${laatste}${lijst_rij}"

		index_rij = lijst_rij + 1
		self._label(ws, index_rij, labels.SCENARIO_INDEX)
		self._zet(ws, index_rij, 3, "=MATCH(Scenario,Scenario_List,0)", "0")
		self.namen["Scenario_Index"] = f"{ZIJDE_MODEL}$C${index_rij}"

		legenda = index_rij + 1
		self._label(ws, legenda, labels.LEGEND, vet=True)
		ws.cell(row=legenda, column=3, value=labels.LEGEND_INPUT).font = stijl.lettertype(stijl.BLAUW)
		ws.cell(row=legenda + 1, column=3, value=labels.LEGEND_FORMULA).font = stijl.lettertype()
		ws.cell(row=legenda + 2, column=3, value=labels.LEGEND_LINK).font = stijl.lettertype(stijl.GROEN)
		cel = ws.cell(row=legenda + 3, column=3, value=labels.LEGEND_OVERRIDE)
		cel.font = stijl.lettertype(stijl.BLAUW)
		for kolom in range(3, 9):
			ws.cell(row=legenda + 3, column=kolom).fill = stijl.VUL_OVERRIDE

	def _schrijf_tijdlijn(self, ws):
		rm = self.r["model"]
		self._sectie(ws, rm["jaar_nr"] - 1, labels.SECTION_TIMELINE, self.kol.overrides)
		self._label(ws, rm["jaar_nr"], labels.ROW_LABELS["jaar_nr"])
		self._label(ws, rm["einde"], labels.ROW_LABELS["einde"])
		self._label(ws, rm["fractie"], labels.ROW_LABELS["fractie"])
		self._zet(ws, rm["einde"], self.kol.closing, datetime.fromisoformat(self.rij["LBO_Closing_Datum"]), stijl.FMT_DATUM)
		for jaar, kolom in enumerate(self.kol.jaren, start=1):
			periode = self.rij["LBO_Jaren"][jaar]
			self._zet(ws, rm["jaar_nr"], kolom, jaar, "0")
			self._zet(ws, rm["einde"], kolom, datetime.fromisoformat(periode["Einde"]), stijl.FMT_DATUM)
			self._zet(ws, rm["fractie"], kolom, periode["Fractie"], "0.000")
		for sleutel in ("jaar_nr", "einde", "fractie"):
			self._grijs(ws, rm[sleutel])

	def _schrijf_tekstkolommen(self, ws, nr, teksten):
		for kolom, tekst in zip((self.kol.rationale, self.kol.source, self.kol.confidence, self.kol.flag), teksten):
			cel = ws.cell(row=nr, column=kolom, value=tekst or None)
			cel.font = stijl.lettertype(stijl.BLAUW, grootte=8)
			cel.alignment = Alignment(wrap_text=False, vertical="center")

	def _schrijf_ai_blokken(self, ws):
		rm = self.r["model"]
		for scenario in assumpties.MODEL_SCENARIOS:
			naam = assumpties.scenario_label(scenario)
			rij_ai = labels.ROW_RULE_BASED if assumpties.is_screening(scenario) else labels.ROW_AI
			kop = self.ai_blokken[scenario]
			self._sectie(ws, kop, labels.SECTION_AI.format(scenario=naam.upper()), self.kol.overrides)
			for kolom, tekst in (
				(self.kol.rationale, labels.HEADER_RATIONALE),
				(self.kol.source, labels.HEADER_SOURCE),
				(self.kol.confidence, labels.HEADER_CONFIDENCE),
				(self.kol.flag, labels.HEADER_FLAG),
				(self.kol.overrides, labels.HEADER_OVERRIDES),
			):
				ws.cell(row=kop, column=kolom, value=tekst)

			for driver in assumpties.DRIVERS:
				voorstel = self.pack[scenario][driver.sleutel]
				fmt = self._driver_fmt(driver)
				ai_rij = rm[f"ai_{scenario}_{driver.sleutel}"]
				ov_rij = rm[f"ov_{scenario}_{driver.sleutel}"]
				used_rij = rm[f"u_{scenario}_{driver.sleutel}"]
				self._label(ws, ai_rij, rij_ai.format(driver=driver.label))
				self._label(ws, ov_rij, labels.ROW_OVERRIDE.format(driver=driver.label))
				self._label(ws, used_rij, labels.ROW_USED.format(driver=driver.label))
				for jaar, kolom in enumerate(self.kol.jaren):
					k = get_column_letter(kolom)
					self._zet(ws, ai_rij, kolom, self._driver_waarde(driver, voorstel["waarden"][jaar]), fmt)
					cel = ws.cell(row=ov_rij, column=kolom)
					cel.fill = stijl.VUL_OVERRIDE
					cel.border = stijl.RAND_OVERRIDE
					cel.font = stijl.lettertype(stijl.BLAUW)
					cel.number_format = fmt
					cel.alignment = Alignment(horizontal="right")
					self._zet(ws, used_rij, kolom, f"=IF(ISBLANK({k}{ov_rij}),{k}{ai_rij},{k}{ov_rij})", fmt)
				self._schrijf_tekstkolommen(
					ws, ai_rij,
					(voorstel["rationale"], voorstel["source"], voorstel["confidence"], "; ".join(voorstel["vlaggen"])),
				)
				eerste = get_column_letter(self.kol.jaren[0])
				laatste = get_column_letter(self.kol.jaren[-1])
				self._zet(ws, ov_rij, self.kol.overrides, f"=COUNTA({eerste}{ov_rij}:{laatste}{ov_rij})", "0")
				self.override_cellen.append(f"{get_column_letter(self.kol.overrides)}{ov_rij}")
				for nr in (ai_rij, ov_rij, used_rij):
					self._grijs(ws, nr)
				ws.row_dimensions.group(ai_rij, used_rij, outline_level=1, hidden=False)

	def _schrijf_actief(self, ws):
		rm = self.r["model"]
		self._sectie(ws, self.actief_blok, labels.SECTION_ACTIVE, self.kol.overrides)
		for kolom, tekst in (
			(self.kol.rationale, labels.HEADER_RATIONALE),
			(self.kol.source, labels.HEADER_SOURCE),
			(self.kol.confidence, labels.HEADER_CONFIDENCE),
			(self.kol.flag, labels.HEADER_FLAG),
		):
			ws.cell(row=self.actief_blok, column=kolom, value=tekst)

		for driver in assumpties.DRIVERS:
			fmt = self._driver_fmt(driver)
			nr = rm[f"a_{driver.sleutel}"]
			self._label(ws, nr, driver.label)
			for index, kolom in enumerate(self.kol.hist):
				if driver.historiek:
					waarde = _waarde(self.historiek[index], driver.historiek)
					if waarde is not None:
						self._zet(ws, nr, kolom, self._driver_waarde(driver, waarde), fmt)
			for kolom in self.kol.jaren:
				k = get_column_letter(kolom)
				keuzes = ",".join(f"{k}{rm[f'u_{scenario}_{driver.sleutel}']}" for scenario in assumpties.MODEL_SCENARIOS)
				self._zet(ws, nr, kolom, f"=CHOOSE(Scenario_Index,{keuzes})", fmt)
			for kolom in (self.kol.rationale, self.kol.source, self.kol.confidence, self.kol.flag):
				k = get_column_letter(kolom)
				keuzes = ",".join(f"{k}{rm[f'ai_{scenario}_{driver.sleutel}']}" for scenario in assumpties.MODEL_SCENARIOS)
				cel = ws.cell(row=nr, column=kolom, value=f'=CHOOSE(Scenario_Index,{keuzes})&""')
				cel.font = stijl.lettertype(grootte=8)
			self._grijs(ws, nr)

		nr = rm["a_groei"]
		self._label(ws, nr, labels.DRIVER_REVENUE_GROWTH)
		for index, kolom in enumerate(self.kol.hist):
			waarde = _waarde(self.historiek[index], "Omzetgroei_Pct")
			if waarde is not None:
				self._zet(ws, nr, kolom, waarde / 100, stijl.FMT_PCT)
		for kolom in self.kol.jaren:
			c = self._ctx("model", kolom)
			self._zet(ws, nr, kolom, f"=(1+{c.h('a_volumegroei')})*(1+{c.h('a_prijsgroei')})-1", stijl.FMT_PCT)
		self._grijs(ws, nr)

		nr = rm["a_marge"]
		self._label(ws, nr, labels.DRIVER_EBITDA_MARGIN)
		for kolom in self.kol.hist + self.kol.jaren:
			c = self._ctx("model", kolom)
			self._zet(ws, nr, kolom, f'=IF({c.h("rev")}=0,"",{c.h("ebitda")}/{c.h("rev")})', stijl.FMT_PCT)
		self._grijs(ws, nr)

	# ------------------------------------------------------------------ tabs
	def schrijf_model(self):
		ws = self.ws_model
		self._kop(ws, labels.TITLE_MODEL, "model")
		self._schrijf_scenariokiezer(ws)
		self._schrijf_tijdlijn(ws)
		self._schrijf_ai_blokken(ws)
		self._schrijf_actief(ws)
		self._schrijf_rijen(ws, self.model_specs, "model")
		self._voet(ws, self.model_einde + 1)
		for kolom in (self.kol.rationale, self.kol.source):
			ws.column_dimensions[get_column_letter(kolom)].width = 60
		ws.column_dimensions[get_column_letter(self.kol.confidence)].width = 10
		ws.column_dimensions[get_column_letter(self.kol.flag)].width = 60
		ws.column_dimensions[get_column_letter(self.kol.overrides)].width = 9
		ws.sheet_properties.outlinePr.summaryBelow = False

	def _enkelvoudig(self, ws, specs, titel, start):
		self._sectie(ws, start, titel)
		for sleutel, naam, soort, inhoud, fmt, opmaak in specs:
			nr = self.r["lbo"][f"{sleutel}_rij"]
			self._label(ws, nr, labels.ROW_LABELS[sleutel], vet=opmaak != "normaal")
			c = self._ctx("lbo", 3)
			self._zet(ws, nr, 3, inhoud(c) if soort == "f" else inhoud, fmt)
			self._rij_stijl(ws, nr, opmaak, 3)

	def schrijf_lbo(self):
		ws = self.ws_lbo
		self._kop(ws, labels.TITLE_LBO, "lbo")
		self._sectie(ws, HOOFD + 1, labels.SECTION_INPUTS)
		for index, (naam, waarde, fmt) in enumerate(self.invoer):
			nr = self.invoer_start + index
			self._label(ws, nr, labels.INPUT_LABELS[naam])
			self._zet(ws, nr, 3, waarde, fmt)

		self._enkelvoudig(ws, self.brug, labels.SECTION_BRIDGE, self.brug_start)
		self._enkelvoudig(ws, self.su, labels.SECTION_SU, self.su_start)
		self._schrijf_rijen(ws, self.lbo_specs, "lbo")
		self._schrijf_exit(ws)
		self._voet(ws, self.lbo_einde + 1)

	def _schrijf_exit(self, ws):
		rl = self.r["lbo"]
		self._sectie(ws, self.exit_start, labels.SECTION_EXIT)
		k5 = get_column_letter(self.kol.laatste_jaar)
		eerste = get_column_letter(self.kol.closing)
		fractie = f"{ZIJDE_MODEL}{k5}{self.r['model']['fractie']}"
		regels = [
			("x_ebitda", f"={k5}{rl['w_ebitda']}/{fractie}", stijl.FMT_BEDRAG),
			("x_mult", "=Exit_Multiple", stijl.FMT_MULT),
			("x_ev", f"=MAX(C{rl['x_ebitda']},0)*C{rl['x_mult']}", stijl.FMT_BEDRAG),
			("x_nd", f"={k5}{rl['nd_val']}", stijl.FMT_BEDRAG),
			("x_equity", f"=C{rl['x_ev']}-C{rl['x_nd']}", stijl.FMT_BEDRAG),
			("x_lev", f'=IF(C{rl["x_ebitda"]}>0,C{rl["x_nd"]}/C{rl["x_ebitda"]},"")', stijl.FMT_MULT_2),
			(
				"x_duration",
				f"=SUM({ZIJDE_MODEL}{get_column_letter(self.kol.jaren[0])}{self.r['model']['fractie']}:{k5}{self.r['model']['fractie']})",
				stijl.FMT_INDEX,
			),
		]
		for sleutel, formule, fmt in regels:
			self._label(ws, rl[sleutel], labels.ROW_LABELS[sleutel])
			self._zet(ws, rl[sleutel], 3, formule, fmt)

		self._label(ws, rl["x_dates"], labels.ROW_LABELS["x_dates"])
		self._label(ws, rl["x_flows"], labels.ROW_LABELS["x_flows"])
		self._zet(ws, rl["x_dates"], self.kol.closing, f"={ZIJDE_MODEL}{eerste}{self.r['model']['einde']}", stijl.FMT_DATUM)
		self._zet(ws, rl["x_flows"], self.kol.closing, "=-Sponsor_Equity", stijl.FMT_BEDRAG)
		for jaar, kolom in enumerate(self.kol.jaren, start=1):
			k = get_column_letter(kolom)
			self._zet(ws, rl["x_dates"], kolom, f"={ZIJDE_MODEL}{k}{self.r['model']['einde']}", stijl.FMT_DATUM)
			exit_deel = f"+C{rl['x_equity']}" if kolom == self.kol.laatste_jaar else ""
			self._zet(ws, rl["x_flows"], kolom, f"={k}{rl['w_div']}{exit_deel}", stijl.FMT_BEDRAG)

		stromen = f"{eerste}{rl['x_flows']}:{k5}{rl['x_flows']}"
		datums = f"{eerste}{rl['x_dates']}:{k5}{rl['x_dates']}"
		met_stub = self.rij["LBO_Jaren"][1]["Fractie"] < 1
		rendement = f"XIRR({stromen},{datums})" if met_stub else f"IRR({stromen})"
		ok = f"AND(Sponsor_Equity>0,C{rl['x_equity']}>0)"
		dividenden = f"SUM({get_column_letter(self.kol.jaren[0])}{rl['w_div']}:{k5}{rl['w_div']})"
		self._label(ws, rl["x_irr"], labels.ROW_LABELS["x_irr"], vet=True)
		self._label(ws, rl["x_moic"], labels.ROW_LABELS["x_moic"], vet=True)
		self._zet(ws, rl["x_irr"], 3, f"=IF({ok},{rendement},-1)", stijl.FMT_PCT, vet=True)
		self._zet(
			ws, rl["x_moic"], 3, f"=IF({ok},(C{rl['x_equity']}+{dividenden})/Sponsor_Equity,0)", stijl.FMT_MULT_2, vet=True
		)
		self._rij_stijl(ws, rl["x_moic"], "eindtotaal", 3)

		jaren_k = f"{get_column_letter(self.kol.jaren[0])}"
		self._label(ws, rl["x_covenants"], labels.ROW_LABELS["x_covenants"])
		self._zet(
			ws, rl["x_covenants"], 3,
			f'=IF(COUNTIF({jaren_k}{rl["c_status"]}:{k5}{rl["c_status"]},"{labels.COVENANTS_BREACHED}")>0,"{labels.COVENANTS_BREACHED}","{labels.COVENANTS_OK}")',
			"@",
		)
		self._label(ws, rl["x_peak_lev"], labels.ROW_LABELS["x_peak_lev"])
		self._zet(ws, rl["x_peak_lev"], 3, f"=MAX({jaren_k}{rl['c_lev']}:{k5}{rl['c_lev']})", stijl.FMT_MULT_2)
		self._label(ws, rl["x_min_dscr"], labels.ROW_LABELS["x_min_dscr"])
		self._zet(ws, rl["x_min_dscr"], 3, f"=MIN({jaren_k}{rl['c_dscr']}:{k5}{rl['c_dscr']})", stijl.FMT_MULT_2)

	def schrijf_samenvatting(self):
		ws = self.ws_samenvatting
		rij = self.rij
		rm, rl = self.r["model"], self.r["lbo"]
		self._kop(ws, labels.TITLE_SUMMARY, "samenvatting")
		nr = HOOFD + 1

		status = ws.cell(row=nr, column=3, value=rij["LBO_Status"])
		self._label(ws, nr, labels.STATUS_LABEL, vet=True)
		ws.merge_cells(start_row=nr, start_column=3, end_row=nr, end_column=7)
		stijl.status_kleur(status, rij["LBO_Status"])
		status.alignment = Alignment(horizontal="center", vertical="center")
		nr += 1

		self._label(ws, nr, labels.OVERRIDES_ACTIVE, vet=True)
		som = "+".join(f"{ZIJDE_MODEL}{cel}" for cel in self.override_cellen)
		self._zet(ws, nr, 3, f'=IF({som}>0,"{labels.YES}","{labels.NO}")', "@")
		ws.cell(row=nr, column=4, value=labels.OVERRIDES_NOTE).font = stijl.lettertype(cursief=True)
		self.overrides_cel = f"C{nr}"
		nr += 1

		self._label(ws, nr, labels.SCENARIO_SELECT)
		self._zet(ws, nr, 3, "=Scenario", "@")
		nr += 1

		status_snapshot = rij.get("LBO_Snapshot_Status", "-")
		for label, waarde in (
			(labels.SNAPSHOT_LABEL, rij.get("LBO_Snapshot_Naam", "-")),
			(labels.SNAPSHOT_DATE, rij.get("LBO_Snapshot_Datum", "-")),
			(labels.SNAPSHOT_STATUS, labels.SNAPSHOT_STATUS_LABELS.get(status_snapshot, status_snapshot)),
		):
			self._label(ws, nr, label)
			ws.cell(row=nr, column=3, value=waarde or "-").font = stijl.lettertype()
			nr += 1
		ws.cell(
			row=nr, column=1,
			value=labels.SUBTITLE_SUMMARY.format(
				number=rij["Ondernemingsnummer"],
				year=rij["Boekjaar"],
				schema=labels.SCHEMA_LABELS.get(rij["Schema_Type"], rij["Schema_Type"]),
				source=rij["LBO_Assumptie_Bron"],
			),
		).font = stijl.lettertype(cursief=True, grootte=8)
		nr += 2

		self._sectie(ws, nr, labels.SECTION_KEY_METRICS)
		nr += 1
		links = [
			("x_irr", f"={ZIJDE_LBO}C{rl['x_irr']}", stijl.FMT_PCT),
			("x_moic", f"={ZIJDE_LBO}C{rl['x_moic']}", stijl.FMT_MULT_2),
			("entry_ebitda", f"={ZIJDE_LBO}C{rl['entry_ebitda_rij']}", stijl.FMT_BEDRAG),
			("entry_ev", f"={ZIJDE_LBO}C{rl['entry_ev_rij']}", stijl.FMT_BEDRAG),
			("eq_price", f"={ZIJDE_LBO}C{rl['eq_price_rij']}", stijl.FMT_BEDRAG),
			("s_equity", f"={ZIJDE_LBO}C{rl['s_equity_rij']}", stijl.FMT_BEDRAG),
			("x_ev", f"={ZIJDE_LBO}C{rl['x_ev']}", stijl.FMT_BEDRAG),
			("x_equity", f"={ZIJDE_LBO}C{rl['x_equity']}", stijl.FMT_BEDRAG),
			("x_covenants", f"={ZIJDE_LBO}C{rl['x_covenants']}", "@"),
			("x_peak_lev", f"={ZIJDE_LBO}C{rl['x_peak_lev']}", stijl.FMT_MULT_2),
			("x_lev", f"={ZIJDE_LBO}C{rl['x_lev']}", stijl.FMT_MULT_2),
			("x_min_dscr", f"={ZIJDE_LBO}C{rl['x_min_dscr']}", stijl.FMT_MULT_2),
		]
		for sleutel, formule, fmt in links:
			self._label(ws, nr, labels.ROW_LABELS[sleutel])
			self._zet(ws, nr, 3, formule, fmt)
			nr += 1
		nr += 1

		self._sectie(ws, nr, labels.SECTION_TREND)
		nr += 1
		trend = [
			("rev", "model", stijl.FMT_BEDRAG),
			("a_groei", "model", stijl.FMT_PCT),
			("ebitda", "model", stijl.FMT_BEDRAG),
			("a_marge", "model", stijl.FMT_PCT),
			("ni", "model", stijl.FMT_BEDRAG),
			("w_fcf", "lbo", stijl.FMT_BEDRAG),
			("cash", "model", stijl.FMT_BEDRAG),
			("senior", "model", stijl.FMT_BEDRAG),
			("rcf", "model", stijl.FMT_BEDRAG),
			("nd_bank", "lbo", stijl.FMT_BEDRAG),
			("c_lev", "lbo", stijl.FMT_MULT_2),
			("c_dscr", "lbo", stijl.FMT_MULT_2),
			("c_icr", "lbo", stijl.FMT_MULT_2),
		]
		for sleutel, blad, fmt in trend:
			zijde = ZIJDE_MODEL if blad == "model" else ZIJDE_LBO
			rijen = self.r[blad]
			self._label(ws, nr, labels.ROW_LABELS[sleutel])
			kolommen = self.kol.alle if blad == "model" and sleutel not in ("rcf", "senior") else self.kol.jaren
			for kolom in kolommen:
				if kolom == self.kol.closing and sleutel not in ("cash", "senior", "rcf"):
					continue
				bron = (self.ws_model if blad == "model" else self.ws_lbo).cell(row=rijen[sleutel], column=kolom)
				if bron.value is not None:
					self._zet(ws, nr, kolom, f"={zijde}{get_column_letter(kolom)}{rijen[sleutel]}", fmt)
			self._grijs(ws, nr)
			nr += 1
		nr += 1

		self._sectie(ws, nr, labels.SECTION_SCENARIOS)
		nr += 1
		for index, scenario in enumerate(assumpties.MODEL_SCENARIOS):
			cel = ws.cell(row=nr, column=3 + index, value=assumpties.scenario_label(scenario))
			cel.font = stijl.lettertype(vet=True)
			cel.alignment = Alignment(horizontal="center", wrap_text=True)
		notitie = 3 + len(assumpties.MODEL_SCENARIOS)
		ws.cell(row=nr, column=notitie, value=labels.SCENARIO_NOTE).font = stijl.lettertype(cursief=True, grootte=8)
		nr += 1
		modellen = [rij["LBO_Scenarios"][scenario] for scenario in assumpties.MODEL_SCENARIOS]
		metrieken = [
			("x_irr", lambda m: m["LBO_IRR_Exact_Pct"] / 100, stijl.FMT_PCT),
			("x_moic", lambda m: m["LBO_MoIC_Exact"], stijl.FMT_MULT_2),
			("x_ebitda", lambda m: m["LBO_EBITDA_Jaar5"], stijl.FMT_BEDRAG),
			("x_min_dscr", lambda m: m["LBO_Laagste_DSCR"], stijl.FMT_MULT_2),
			("x_peak_lev", lambda m: m["LBO_Hoogste_Leverage"], stijl.FMT_MULT_2),
			("d_rcf", lambda m: m["LBO_RCF_Piek"], stijl.FMT_BEDRAG),
		]
		for sleutel, ophalen, fmt in metrieken:
			self._label(ws, nr, labels.ROW_LABELS[sleutel])
			for index, model in enumerate(modellen):
				self._zet(ws, nr, 3 + index, ophalen(model), fmt)
			nr += 1
		self._label(ws, nr, labels.ROW_LABELS["x_covenants"])
		for index, model in enumerate(modellen):
			waarde = model["LBO_Convenanten"].split(":")[0]
			cel = ws.cell(row=nr, column=3 + index, value=waarde)
			cel.font = stijl.lettertype(stijl.BLAUW)
			cel.alignment = Alignment(horizontal="right")
		nr += 2

		nr = self._schrijf_teksten(ws, nr)
		self._voet(ws, nr + 1)

	def _schrijf_teksten(self, ws, nr):
		rij = self.rij
		self._sectie(ws, nr, labels.SECTION_TEXT)
		nr += 1
		thesis = "\n".join(f"\u2022 {punt}" for punt in (rij.get("AI_Investment_Thesis") or []))
		vragen = "\n".join(
			f"{index}. {vraag['vraag']} ({labels.DD_LINKED_TO}: {vraag['gekoppeld_aan']})"
			for index, vraag in enumerate(rij.get("AI_DD_Vragen") or [], start=1)
		)
		blokken = [
			(labels.COLUMN_LABELS["Eigendom"], rij.get("Eigendom", "")),
			(labels.COLUMN_LABELS["AI_Business_Model"], rij.get("AI_Business_Model", "")),
			(labels.COLUMN_LABELS["AI_Investment_Thesis"], thesis),
			(labels.COLUMN_LABELS["AI_DD_Vragen"], vragen),
			(labels.COLUMN_LABELS["Commissaris_Oordeel"], rij.get("Commissaris_Oordeel", "")),
			(labels.COLUMN_LABELS["Normalisatie_Toelichting"], rij.get("Normalisatie_Toelichting", "")),
			(labels.COLUMN_LABELS["Normalisatie_Voorstellen"], rij.get("Normalisatie_Voorstellen", "")),
			(labels.COLUMN_LABELS["Buitenbalans_Verplichtingen"], rij.get("Buitenbalans_Verplichtingen", "")),
			(labels.COLUMN_LABELS["LBO_Convenanten"], rij.get("LBO_Convenanten", "")),
			(labels.COLUMN_LABELS["LBO_Downside_Convenanten"], rij.get("LBO_Downside_Convenanten", "")),
			(labels.COLUMN_LABELS["Red_Flags"], rij.get("Red_Flags", "")),
			(labels.COLUMN_LABELS["Kwalitatief_LBO_Oordeel"], rij.get("Kwalitatief_LBO_Oordeel", "")),
		]
		for doel, definitie in config.NET_DEBT_DEFINITIES.items():
			blokken.append((f"{labels.SECTION_DEFINITIONS.title()}: {definitie['label']}", net_debt_formule(doel)))
		breedte_tekens = 13 * len(self.kol.alle) * 1.15
		for label, tekst in blokken:
			tekst = str(tekst or "").strip() or "-"
			cel = ws.cell(row=nr, column=1, value=label)
			cel.font = stijl.lettertype(vet=True)
			cel.alignment = Alignment(vertical="top", wrap_text=True)
			ws.merge_cells(start_row=nr, start_column=3, end_row=nr, end_column=self.kol.laatste_jaar)
			cel = ws.cell(row=nr, column=3, value=tekst)
			cel.font = stijl.lettertype()
			cel.alignment = Alignment(vertical="top", wrap_text=True)
			regels = sum(max(1, int(len(deel) / breedte_tekens) + 1) for deel in tekst.split("\n"))
			ws.row_dimensions[nr].height = max(16, 14 * regels + 2)
			nr += 1
		return nr

	def schrijf_namen(self):
		for naam, adres in self.namen.items():
			self.wb.defined_names[naam] = DefinedName(naam, attr_text=adres)
		self.wb.calculation.fullCalcOnLoad = True

	def kaart(self):
		"""The addresses of the key cells, for the reconciliation test."""
		return {
			"rijen": self.r,
			"kolommen": {
				"jaren": [get_column_letter(kolom) for kolom in self.kol.jaren],
				"closing": get_column_letter(self.kol.closing),
			},
			"scenario_cel": f"C{self.scenario_rij}",
			"overrides_cel": self.overrides_cel,
			"checks_cel": self.checks_totaal,
		}


def bouw_werkboek(rij, historiek):
	"""Builds the full company workbook. Returns the workbook and the address map."""
	bouwer = Bouwer(rij, historiek)
	bouwer._plan_model()
	bouwer._plan_lbo()
	bouwer.schrijf_model()
	bouwer.schrijf_lbo()
	bouwer.schrijf_samenvatting()
	bouwer.schrijf_namen()
	return bouwer.wb, bouwer.kaart()


def bouw_lege_fiche(rij, historiek):
	"""A company without a calculable LBO: the message, the actuals and the text blocks."""
	bouwer = Bouwer(rij, historiek)
	ws = bouwer.ws_samenvatting
	for naam in (labels.TAB_MODEL, labels.TAB_LBO):
		del bouwer.wb[naam]
	ws.sheet_view.showGridLines = False
	ws.column_dimensions["A"].width = 52
	ws.column_dimensions["B"].width = 7
	for kolom in bouwer.kol.alle:
		ws.column_dimensions[get_column_letter(kolom)].width = 13
	for kolom in range(1, bouwer.kol.laatste_jaar + 1):
		stijl.sectiekop(ws.cell(row=1, column=kolom))
	ws.cell(row=1, column=1, value=f"{labels.TITLE_SUMMARY}: {rij['Bedrijfsnaam']}   ({labels.UNITS_NOTE})")

	status = ws.cell(row=2, column=1, value=rij["LBO_Status"])
	stijl.status_kleur(status, rij["LBO_Status"])
	ws.cell(row=3, column=1, value=labels.NO_PROJECTION.format(reason=rij["LBO_Convenanten"])).font = stijl.lettertype(vet=True)

	nr = 5
	for index, kolom in enumerate(bouwer.kol.hist):
		cel = ws.cell(row=nr, column=kolom, value=bouwer.historiek[index]["Label"])
		cel.font = stijl.lettertype(vet=True)
		cel.alignment = Alignment(horizontal="center")
		cel.fill = stijl.VUL_ACTUAL
	nr += 1
	for sleutel, veld in (
		("rev", "Omzet"), ("ebitda", "EBITDA"), ("ni", "Nettowinst"), ("cash", "Cash"), ("equity", "Eigen_Vermogen"),
	):
		bouwer._label(ws, nr, labels.ROW_LABELS[sleutel])
		for index, kolom in enumerate(bouwer.kol.hist):
			bouwer._zet(ws, nr, kolom, _waarde(bouwer.historiek[index], veld), stijl.FMT_BEDRAG)
			ws.cell(row=nr, column=kolom).fill = stijl.VUL_ACTUAL
		nr += 1
	nr = bouwer._schrijf_teksten(ws, nr + 1)
	bouwer._voet(ws, nr + 1)
	ws.freeze_panes = ws.cell(row=2, column=2)
	return bouwer.wb
