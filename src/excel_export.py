"""Professionele Private Equity & M&A Excel-export (inclusief het 3-statement LBO-model).

Genereert twee soorten output in output/:
1. schrijf_overzicht(df):
   - Tabblad 1 ('Executive_Summary'): Kern-vergelijkingstabel inclusief IRR, MoIC
	 en 5-jaars schuldcheck.
   - Tabblad 2 ('Volledige_Data_Detail'): Alle onderliggende balans-/resultaatposten,
	 LBO-kolommen en kwalitatieve notities.
2. schrijf_per_bedrijf(df):
   - Tabblad 1 ('LBO_Tear_Sheet'): Verticale One-Pager met 5 secties onder elkaar.
   - Tabblad 2 ('3-Statement_Model'): Drivers, bronnen en bestedingen, resultatenrekening,
	 balans, kasstroom, schuldschema en convenanten per jaar.
   - Tabblad 3 ('Meerjarencijfers'): De cijfers per boekjaar uit de NBB-CSV's.
"""
import re
import time
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config, labels
from . import excel_stijl as stijl
from .lbo_model import net_debt_formule

# Kleurenpalet (Investment Banking / PE-stijl)
NAVY_HEADER = "1F3864"
SUB_HEADER = "2F5597"
SECTIE_BLAUW = "D9E1F2"
ZEBRA_TINT = "F9FAFC"
TOTAAL_TINT = "F2F2F2"

DUNNE_LIJN = Side(style="thin", color="D9D9D9")
MEDIUM_ONDER = Side(style="medium", color="1F3864")
DUBBEL_ONDER = Side(style="double", color="1F3864")

RAND_CEL = Border(left=DUNNE_LIJN, right=DUNNE_LIJN, top=DUNNE_LIJN, bottom=DUNNE_LIJN)
RAND_SUBTOTAAL = Border(top=DUNNE_LIJN, bottom=MEDIUM_ONDER, left=DUNNE_LIJN, right=DUNNE_LIJN)
RAND_EINDTOTAAL = Border(top=DUNNE_LIJN, bottom=DUBBEL_ONDER, left=DUNNE_LIJN, right=DUNNE_LIJN)

FMT_EURO = '€ #,##0;[Red]-€ #,##0;"-"'
FMT_PCT_GROEI = '+0.0"%";[Red]-0.0"%";0.0"%"'
FMT_PCT_MARGE = '0.0"%"'
FMT_PP = '+0.0" pp";[Red]-0.0" pp";0.0" pp"'
FMT_MULT = '0.00"x"'
FMT_DAGEN = '0.0" d"'


def veilige_bestandsnaam(naam, fallback=labels.UNKNOWN_COMPANY):
	naam = (naam or "").strip() or fallback
	naam = re.sub(r"[^\w\s-]", "", naam, flags=re.UNICODE)
	naam = re.sub(r"\s+", "_", naam).strip("_")
	return naam[:80] or fallback


def _leeg_als_nan(waarde):
	"""Een ontbrekend cijfer wordt een lege cel."""
	return None if isinstance(waarde, float) and pd.isna(waarde) else waarde


def _pas_status_kleur_toe(cel, tekst):
	waarde = str(tekst or "")
	for sleutel, (bg, fg) in labels.STATUS_COLOURS.items():
		if waarde.startswith(sleutel):
			cel.fill = PatternFill("solid", fgColor=bg)
			cel.font = Font(name="Calibri", size=10, bold=True, color=fg)
			return


def _veilig_opslaan(wb, pad):
	config.OUTPUT_FOLDER.mkdir(exist_ok=True)
	try:
		wb.save(pad)
		return pad
	except PermissionError:
		alt = pad.with_name(f"{pad.stem}_{int(time.time())}{pad.suffix}")
		wb.save(alt)
		return alt


# ============================================================================
# 1. Overview workbook (Executive Summary + Full Data Detail)
# ============================================================================
OVERZICHT_KOLOMMEN = [
	("Bedrijfsnaam", labels.GROUP_IDENTIFICATION, 26),
	("Boekjaar", labels.GROUP_IDENTIFICATION, 10),
	("Schema_Type", labels.GROUP_IDENTIFICATION, 12),
	("LBO_Status", labels.GROUP_IDENTIFICATION, 36),
	("Data_Volledigheid", labels.GROUP_IDENTIFICATION, 34),
	("Omzet_of_Brutomarge", labels.GROUP_TRENDS, 15),
	("Omzetgroei_Pct", labels.GROUP_TRENDS, 11),
	("Genormaliseerde_EBITDA", labels.GROUP_TRENDS, 13),
	("EBITDA_Marge_Op_Omzet_Pct", labels.GROUP_TRENDS, 13),
	("EBITDA_Marge_Op_Brutomarge_Pct", labels.GROUP_TRENDS, 13),
	("Marge_Verandering_pp", labels.GROUP_TRENDS, 11),
	("Net_Debt", labels.GROUP_BRIDGE, 13),
	("Debt_Like_Items", labels.GROUP_BRIDGE, 13),
	("Minimum_Operationele_Cash", labels.GROUP_BRIDGE, 13),
	("Adjusted_Net_Debt", labels.GROUP_BRIDGE, 13),
	("Trade_Working_Capital", labels.GROUP_BRIDGE, 13),
	("Huidige_Net_Debt_to_EBITDA", labels.GROUP_RETURNS, 12),
	("Instap_Multiple", labels.GROUP_RETURNS, 10),
	("Indicatieve_EV", labels.GROUP_RETURNS, 13),
	("Indicatieve_Equity_Value", labels.GROUP_RETURNS, 13),
	("LBO_Laagste_DSCR", labels.GROUP_RETURNS, 10),
	("LBO_Convenanten", labels.GROUP_RETURNS, 28),
	("LBO_Sponsor_Equity_Instap", labels.GROUP_RETURNS, 13),
	("LBO_Exit_Equity_Jaar5", labels.GROUP_RETURNS, 13),
	("LBO_Schuld_Onder_2x_5J", labels.GROUP_RETURNS, 14),
	("Indicatieve_MoIC", labels.GROUP_RETURNS, 9),
	("Indicatieve_IRR_Pct", labels.GROUP_RETURNS, 9),
	("LBO_Downside_IRR_Pct", labels.GROUP_RETURNS, 10),
	("LBO_Downside_Convenanten", labels.GROUP_RETURNS, 28),
]

TEKST_KOLOMMEN = {
	"Data_Volledigheid",
	"Check_Data",
	"Normalisatie_Toelichting",
	"Normalisatie_Voorstellen",
	"Buitenbalans_Verplichtingen",
	"LBO_Convenanten",
	"LBO_Downside_Convenanten",
	"Red_Flags",
	"Kwalitatief_LBO_Oordeel",
}
STATUS_KOLOMMEN = {"LBO_Status", "LBO_Schuld_Onder_2x_5J"}
PCT_KOLOMMEN = {
	"Omzetgroei_Pct",
	"EBITDA_Groei_Pct",
	"EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct",
	"EBITDA_Marge_Op_Omzet_Pct",
	"EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct",
	"EBITDA_Marge_Op_Brutomarge_Pct",
	"Driver_Historische_CAGR_Pct",
	"Driver_Omzetgroei_Pct",
	"Driver_EBITDA_CAGR_Pct",
	"Driver_EBITDA_Marge_Gemiddeld_Pct",
	"Driver_EBITDA_Marge_Pct",
	"Driver_Inkoop_Pct",
	"Driver_Overige_Kosten_Pct",
	"Driver_DA_Pct_Vaste_Activa",
	"Driver_Capex_Pct",
	"Driver_Kosten_60_Pct",
	"Driver_Kosten_6061_Pct",
	"Indicatieve_IRR_Pct",
	"LBO_Downside_IRR_Pct",
	"LBO_Upside_IRR_Pct",
	"LBO_EBITDA_Marge_Exit_Pct",
}
DAGEN_KOLOMMEN = {"Driver_DSO", "Driver_DIO", "Driver_DPO", "Driver_Dagen_Vooruitbetaling"}
GETAL_KOLOMMEN = {"Capex_Aantal_Jaren", "Driver_Aantal_Jaren", "VTE", "LBO_Duur_Jaren", "Boekjaar_Maanden", "Boekjaar_Maanden_Vorig_Jaar"}
MULT_KOLOMMEN = {
	"Instap_Multiple",
	"Senior_Multiple",
	"LBO_Laagste_DSCR",
	"LBO_Laagste_Rentedekking",
	"LBO_Hoogste_Leverage",
	"LBO_Downside_MoIC",
	"Huidige_Net_Debt_to_EBITDA",
	"LBO_Eind_Net_Debt_to_EBITDA",
	"Indicatieve_MoIC",
}
GEEN_BEDRAG_KOLOMMEN = {"Boekjaar", "Boekjaar_Begin", "Boekjaar_Einde", "LBO_Closing_Datum", "Ondernemingsnummer"}
OBJECT_KOLOMMEN = ["LBO_Jaren", "LBO_Integriteit", "LBO_Scenarios"]


def _schrijf_overzichtcel(ws, rij_nr, kolom_nr, kol_naam, rij, numeriek):
	"""One cell of the overview. Amounts stay in full euro; the format shows EUR thousands."""
	waarde = _leeg_als_nan(rij.get(kol_naam, ""))
	if kol_naam == "Schema_Type":
		waarde = labels.SCHEMA_LABELS.get(waarde, waarde)
	cel = ws.cell(row=rij_nr, column=kolom_nr, value=waarde)
	cel.font = stijl.lettertype()
	if kol_naam in STATUS_KOLOMMEN:
		cel.alignment = Alignment(horizontal="center", vertical="center")
		stijl.status_kleur(cel, waarde)
	elif kol_naam in TEKST_KOLOMMEN:
		cel.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
	elif waarde is not None and numeriek and kol_naam not in GEEN_BEDRAG_KOLOMMEN:
		cel.font = stijl.lettertype(stijl.BLAUW)
		cel.alignment = Alignment(horizontal="right", vertical="center")
		if kol_naam in PCT_KOLOMMEN:
			cel.value = waarde / 100
			cel.number_format = stijl.FMT_PCT
		elif kol_naam == "Marge_Verandering_pp":
			cel.number_format = stijl.FMT_PP
		elif kol_naam in MULT_KOLOMMEN:
			cel.number_format = stijl.FMT_MULT
		elif kol_naam in DAGEN_KOLOMMEN:
			cel.number_format = stijl.FMT_DAGEN
		elif kol_naam in GETAL_KOLOMMEN:
			cel.number_format = stijl.FMT_GETAL
		else:
			cel.number_format = stijl.FMT_BEDRAG
	else:
		cel.alignment = Alignment(horizontal="left", vertical="center")


def _voetblok(ws, rij_nr, df):
	"""Date, model version, Gemini model and source file."""
	modellen = sorted({str(model) for model in df["Gebruikt_Model"] if model and model != "-"})
	bestanden = sorted({str(bestand) for bestand in df["Bronbestand"]})
	regels = [
		(labels.FOOTER_DATE, datetime.now().strftime("%Y-%m-%d %H:%M")),
		(labels.FOOTER_VERSION, config.MODEL_VERSIE),
		(labels.FOOTER_GEMINI, ", ".join(modellen) or "-"),
		(labels.FOOTER_SOURCE, ", ".join(bestanden) or "-"),
	]
	for verschuiving, (label, waarde) in enumerate(regels):
		ws.cell(row=rij_nr + verschuiving, column=1, value=label).font = stijl.lettertype(vet=True)
		ws.cell(row=rij_nr + verschuiving, column=2, value=waarde).font = stijl.lettertype()


def _vul_executive_summary(ws, df):
	ws.sheet_view.showGridLines = False
	ws.cell(row=1, column=1, value=labels.UNITS_NOTE).font = stijl.lettertype(cursief=True)

	groepen = {}
	for index, (_, groep, _) in enumerate(OVERZICHT_KOLOMMEN, start=1):
		groepen.setdefault(groep, []).append(index)
	for groep, kolommen in groepen.items():
		if len(kolommen) > 1:
			ws.merge_cells(start_row=2, start_column=kolommen[0], end_row=2, end_column=kolommen[-1])
		for kolom in kolommen:
			stijl.sectiekop(ws.cell(row=2, column=kolom))
		ws.cell(row=2, column=kolommen[0], value=groep).alignment = Alignment(horizontal="center", vertical="center")

	for index, (kol_naam, _, breedte) in enumerate(OVERZICHT_KOLOMMEN, start=1):
		cel = ws.cell(row=3, column=index, value=labels.COLUMN_LABELS[kol_naam])
		cel.font = stijl.lettertype(vet=True)
		cel.fill = stijl.VUL_ACTUAL
		cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cel.border = stijl.RAND_SUBTOTAAL
		ws.column_dimensions[get_column_letter(index)].width = breedte
	ws.row_dimensions[3].height = 42
	ws.freeze_panes = "B4"

	for rij_nr, (_, rij) in enumerate(df.iterrows(), start=4):
		ws.row_dimensions[rij_nr].height = 22
		for index, (kol_naam, _, _) in enumerate(OVERZICHT_KOLOMMEN, start=1):
			_schrijf_overzichtcel(ws, rij_nr, index, kol_naam, rij, pd.api.types.is_numeric_dtype(df[kol_naam]))
	_voetblok(ws, 5 + len(df), df)


def _vul_detail_tabblad(ws, df):
	ws.sheet_view.showGridLines = False
	# Yearly figures, checks and scenarios are in the company workbook
	df = df.drop(columns=OBJECT_KOLOMMEN)
	ws.cell(row=1, column=1, value=labels.UNITS_NOTE).font = stijl.lettertype(cursief=True)

	for index, kol_naam in enumerate(df.columns, start=1):
		stijl.sectiekop(ws.cell(row=2, column=index), labels.COLUMN_LABELS[kol_naam])
		ws.cell(row=2, column=index).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		breedte = 45 if kol_naam in TEKST_KOLOMMEN else 34 if kol_naam == "LBO_Status" else 15
		ws.column_dimensions[get_column_letter(index)].width = breedte
	ws.row_dimensions[2].height = 42
	ws.freeze_panes = "B3"

	for rij_nr, (_, rij) in enumerate(df.iterrows(), start=3):
		ws.row_dimensions[rij_nr].height = 48
		for index, kol_naam in enumerate(df.columns, start=1):
			_schrijf_overzichtcel(ws, rij_nr, index, kol_naam, rij, pd.api.types.is_numeric_dtype(df[kol_naam]))


def schrijf_overzicht(df):
	"""Writes the comparison workbook: Executive Summary + Full Data Detail."""
	tijdstempel = datetime.now().strftime("%Y%m%d_%H%M")
	pad = config.OUTPUT_FOLDER / f"{labels.OVERVIEW_FILE}_{tijdstempel}.xlsx"

	wb = Workbook()
	ws_exec = wb.active
	ws_exec.title = labels.TAB_OVERVIEW
	_vul_executive_summary(ws_exec, df)

	ws_detail = wb.create_sheet(title=labels.TAB_DETAIL)
	_vul_detail_tabblad(ws_detail, df)

	return _veilig_opslaan(wb, pad)


# ============================================================================
# 2. INDIVIDUELE BEDRIJFSFICHE (Verticale Tear Sheet + 5-Jaars Kasstroomtab)
# ============================================================================
def _bouw_tear_sheet(wb, rij):
	ws = wb.active
	ws.title = "LBO_Tear_Sheet"
	ws.views.sheetView[0].showGridLines = True

	ws.column_dimensions["A"].width = 3
	ws.column_dimensions["B"].width = 50
	ws.column_dimensions["C"].width = 22
	ws.column_dimensions["D"].width = 22
	ws.column_dimensions["E"].width = 24

	naam = rij.get("Bedrijfsnaam", "Onbekend")
	ond_nr = rij.get("Ondernemingsnummer", "-")
	boekjaar = rij.get("Boekjaar", "-")
	status = rij.get("LBO_Status", "-")

	ws.merge_cells("B2:D2")
	ws["B2"] = f"LBO FEASIBILITY TEAR SHEET — {naam.upper()}"
	ws["B2"].font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
	ws["B2"].fill = PatternFill("solid", fgColor=NAVY_HEADER)
	ws["B2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

	ws["E2"] = status
	ws["E2"].alignment = Alignment(horizontal="center", vertical="center")
	_pas_status_kleur_toe(ws["E2"], status)
	ws.row_dimensions[2].height = 28

	ws.merge_cells("B3:E3")
	ws["B3"] = (
		f"Ondernemingsnummer: {ond_nr}   |   Boekjaar: {boekjaar}   |   "
		f"Schema: {rij.get('Schema_Type', '-')} ({rij.get('Boekjaar_Maanden', '-')} maanden)   |   "
		f"Bronbestand: {rij.get('Bronbestand', '-')}   |   AI-Model: {rij.get('Gebruikt_Model', '-')}"
	)
	ws["B3"].font = Font(name="Calibri", size=9, italic=True, color="333333")
	ws["B3"].fill = PatternFill("solid", fgColor=TOTAAL_TINT)
	ws["B3"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
	ws.row_dimensions[3].height = 19

	huidige_rij = 5

	def voeg_sectiekop_toe(titel, kol_c="", kol_d="", kol_e=""):
		nonlocal huidige_rij
		ws.row_dimensions[huidige_rij].height = 23
		headers = [("B", titel), ("C", kol_c), ("D", kol_d), ("E", kol_e)]
		for letter, tekst in headers:
			cel = ws[f"{letter}{huidige_rij}"]
			cel.value = tekst
			cel.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
			cel.fill = PatternFill("solid", fgColor=SUB_HEADER)
			cel.alignment = Alignment(
				horizontal="left" if letter == "B" else "center",
				vertical="center",
				indent=1 if letter == "B" else 0,
			)
		huidige_rij += 1

	def voeg_rij_toe(label, c=None, d=None, e=None, fmt_c=None, fmt_d=None, fmt_e=None, stijl="normaal"):
		"""Eén dataregel. stijl: 'normaal', 'subtotaal' of 'eindtotaal'."""
		nonlocal huidige_rij
		ws.row_dimensions[huidige_rij].height = 19
		rand = {"normaal": RAND_CEL, "subtotaal": RAND_SUBTOTAAL, "eindtotaal": RAND_EINDTOTAAL}[stijl]
		vet = stijl != "normaal"
		achtergrond = PatternFill("solid", fgColor=TOTAAL_TINT) if vet else None

		cel = ws[f"B{huidige_rij}"]
		cel.value = label
		cel.font = Font(name="Calibri", size=10, bold=vet)
		cel.alignment = Alignment(horizontal="left", vertical="center", indent=1)
		cel.border = rand
		if achtergrond:
			cel.fill = achtergrond

		for letter, waarde, fmt in (("C", c, fmt_c), ("D", d, fmt_d), ("E", e, fmt_e)):
			waarde = _leeg_als_nan(waarde)
			cel = ws[f"{letter}{huidige_rij}"]
			cel.value = waarde
			cel.font = Font(name="Calibri", size=10, bold=vet)
			cel.alignment = Alignment(horizontal="right", vertical="center")
			cel.border = rand
			if achtergrond:
				cel.fill = achtergrond
			if fmt and waarde is not None and waarde != "":
				cel.number_format = fmt
		huidige_rij += 1
		return huidige_rij - 1

	def voeg_tekstblok_toe(label, tekst):
		"""Label links, lange tekst (gewrapt) over C:E."""
		nonlocal huidige_rij
		tekst = str(tekst or "").strip() or "-"
		regels = max(1, -(-len(tekst) // 62))
		ws.row_dimensions[huidige_rij].height = max(30, 14 * regels + 6)

		cel = ws[f"B{huidige_rij}"]
		cel.value = label
		cel.font = Font(name="Calibri", size=10, bold=True)
		cel.alignment = Alignment(horizontal="left", vertical="top", indent=1, wrap_text=True)
		cel.border = RAND_CEL

		ws.merge_cells(start_row=huidige_rij, start_column=3, end_row=huidige_rij, end_column=5)
		cel = ws[f"C{huidige_rij}"]
		cel.value = tekst
		cel.font = Font(name="Calibri", size=10)
		cel.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
		for letter in "CDE":
			ws[f"{letter}{huidige_rij}"].border = RAND_CEL
		huidige_rij += 1

	def witruimte():
		nonlocal huidige_rij
		huidige_rij += 1

	def pct_groei(huidig, vorig):
		"""Groei in %, op basis van abs(vorig) zodat een negatieve basis het teken niet omdraait."""
		try:
			if vorig in (0, None) or pd.isna(vorig):
				return None
			return round((huidig - vorig) / abs(vorig) * 100, 2)
		except (TypeError, ValueError):
			return None

	# ---------------------------------------------------------------- Sectie 1
	voeg_sectiekop_toe("1. RESULTATEN, NORMALISATIE & MEERJARENTREND", "Vorig boekjaar", "Huidig boekjaar", "Evolutie")
	voeg_rij_toe(
		"Omzet / Brutomarge",
		rij["Omzet_of_Brutomarge_Vorig_Jaar"], rij["Omzet_of_Brutomarge"], rij["Omzetgroei_Pct"],
		FMT_EURO, FMT_EURO, FMT_PCT_GROEI,
	)
	voeg_rij_toe(
		"Bedrijfswinst (EBIT)",
		rij["Bedrijfswinst_EBIT_Vorig_Jaar"], rij["Bedrijfswinst_EBIT"],
		pct_groei(rij["Bedrijfswinst_EBIT"], rij["Bedrijfswinst_EBIT_Vorig_Jaar"]),
		FMT_EURO, FMT_EURO, FMT_PCT_GROEI,
	)
	voeg_rij_toe(
		"Afschrijvingen (630)",
		rij["Afschrijvingen_Vorig_Jaar"], rij["Afschrijvingen"],
		pct_groei(rij["Afschrijvingen"], rij["Afschrijvingen_Vorig_Jaar"]),
		FMT_EURO, FMT_EURO, FMT_PCT_GROEI,
	)
	voeg_rij_toe(
		"Voorzieningen: toevoeging/terugneming (635/8)",
		rij["Voorzieningen_Mutatie_Vorig_Jaar"], rij["Voorzieningen_Mutatie"], None,
		FMT_EURO, FMT_EURO, None,
	)
	voeg_rij_toe(
		"Gerapporteerde EBITDA",
		rij["Gerapporteerde_EBITDA_Vorig_Jaar"], rij["Gerapporteerde_EBITDA"], rij["EBITDA_Groei_Pct"],
		FMT_EURO, FMT_EURO, FMT_PCT_GROEI, stijl="subtotaal",
	)
	voeg_rij_toe("Normalisatie (eenmalige posten)", None, rij["Normalisatie_Bedrag"], None, None, FMT_EURO, None)
	voeg_rij_toe(
		"Genormaliseerde EBITDA", None, rij["Genormaliseerde_EBITDA"], None,
		None, FMT_EURO, None, stijl="eindtotaal",
	)
	voeg_rij_toe(
		"Waardeverminderingen vlottend (631/4), niet teruggeteld",
		rij["Waardeverminderingen_Vlottend_Vorig_Jaar"], rij["Waardeverminderingen_Vlottend"], None,
		FMT_EURO, FMT_EURO, None,
	)
	voeg_rij_toe(
		"EBITDA-marge op omzet",
		rij["EBITDA_Marge_Op_Omzet_Vorig_Jaar_Pct"], rij["EBITDA_Marge_Op_Omzet_Pct"], rij["Marge_Verandering_pp"],
		FMT_PCT_MARGE, FMT_PCT_MARGE, FMT_PP,
	)
	voeg_rij_toe(
		"EBITDA-marge op brutomarge (vergelijkbaar)",
		rij["EBITDA_Marge_Op_Brutomarge_Vorig_Jaar_Pct"], rij["EBITDA_Marge_Op_Brutomarge_Pct"], None,
		FMT_PCT_MARGE, FMT_PCT_MARGE, None,
	)
	voeg_tekstblok_toe("Controle NBB-cijfers", rij["Check_Data"])
	voeg_tekstblok_toe("Data-volledigheid", rij["Data_Volledigheid"])
	voeg_tekstblok_toe("Toelichting normalisatie", rij.get("Normalisatie_Toelichting", ""))
	voeg_tekstblok_toe("AI-voorstellen (niet verwerkt in EBITDA)", rij.get("Normalisatie_Voorstellen", ""))
	witruimte()

	# ---------------------------------------------------------------- Sectie 2
	voeg_sectiekop_toe("2. EQUITY BRIDGE (NET DEBT → ADJUSTED NET DEBT)", "", "Bedrag", "")
	voeg_rij_toe("Financiële schulden lange termijn", None, rij["Financiele_Schulden_LT"], None, None, FMT_EURO, None)
	voeg_rij_toe("Financiële schulden korte termijn", None, rij["Financiele_Schulden_KT"], None, None, FMT_EURO, None)
	voeg_rij_toe("Totale financiële schuld", None, rij["Totale_Financiele_Schuld"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe("Af: liquide middelen", None, -rij["Liquide_Middelen"], None, None, FMT_EURO, None)
	voeg_rij_toe("Net Debt (standaard)", None, rij["Net_Debt"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe("Voorzieningen & uitgestelde belastingen", None, rij["Voorzieningen_en_Uitgestelde_Belastingen"], None, None, FMT_EURO, None)
	voeg_rij_toe("Geraamde & vervallen belastingen, vervallen RSZ", None, rij["Belasting_en_Vervallen_RSZ_Schulden"], None, None, FMT_EURO, None)
	voeg_rij_toe("Overige schulden (R/C, dividenden)", None, rij["Overige_Schulden_LT_en_KT"], None, None, FMT_EURO, None)
	voeg_rij_toe("Debt-like items (totaal)", None, rij["Debt_Like_Items"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe(
		f"Minimum operationele cash ({config.MIN_CASH_MAANDEN_PERSONEEL} maand personeel + "
		f"{config.MIN_CASH_WEKEN_LEVERANCIERS} weken leveranciers, max. liquide middelen)",
		None, rij["Minimum_Operationele_Cash"], None, None, FMT_EURO, None,
	)
	voeg_rij_toe("Memo: minimum cash-behoefte", None, rij["Minimum_Cash_Behoefte"], None, None, FMT_EURO, None)
	voeg_rij_toe("Adjusted Net Debt", None, rij["Adjusted_Net_Debt"], None, None, FMT_EURO, None, stijl="eindtotaal")
	voeg_rij_toe("Bestaande schuldgraad (Adj. Net Debt / EBITDA)", None, rij["Huidige_Net_Debt_to_EBITDA"], None, None, FMT_MULT, None)
	for doel, definitie in config.NET_DEBT_DEFINITIES.items():
		voeg_tekstblok_toe(f"Definitie Net Debt: {definitie['label']}", net_debt_formule(doel))
	voeg_rij_toe("Memo: eigen aandelen, niet als cash geteld (50)", None, rij["Eigen_Aandelen"], None, None, FMT_EURO, None)
	voeg_rij_toe("Memo: sociale schulden, onderhandelbaar (454/9)", None, rij["Memo_Sociale_Schulden"], None, None, FMT_EURO, None)
	voeg_rij_toe("Memo: zekerheden voor derden en groep (9149, 9381)", None, rij["Memo_Zekerheden_Derden"], None, None, FMT_EURO, None)
	voeg_rij_toe("Memo: vorderingen op bestuurders (9500)", None, rij["Memo_Vorderingen_Bestuurders"], None, None, FMT_EURO, None)
	voeg_rij_toe("Memo: vorderingen op verbonden ondernemingen (9291)", None, rij["Memo_Vorderingen_Verbonden"], None, None, FMT_EURO, None)
	voeg_tekstblok_toe("Buitenbalans volgens AI (niet in bridge)", rij.get("Buitenbalans_Verplichtingen", ""))
	witruimte()

	# ---------------------------------------------------------------- Sectie 3
	voeg_sectiekop_toe("3. TRADE WORKING CAPITAL", "", "Bedrag", "")
	voeg_rij_toe("Voorraden", None, rij["Voorraden"], None, None, FMT_EURO, None)
	voeg_rij_toe("Handelsvorderingen", None, rij["Handelsvorderingen"], None, None, FMT_EURO, None)
	voeg_rij_toe("Af: handelsschulden", None, -rij["Handelsschulden"], None, None, FMT_EURO, None)
	voeg_rij_toe("Af: ontvangen vooruitbetalingen (46)", None, -rij["Ontvangen_Vooruitbetalingen"], None, None, FMT_EURO, None)
	voeg_rij_toe("Trade working capital", None, rij["Trade_Working_Capital"], None, None, FMT_EURO, None, stijl="eindtotaal")
	witruimte()

	# ---------------------------------------------------------------- Sectie 4
	voeg_sectiekop_toe(
		f"4. LBO-STRUCTUUR & RENDEMENT ({config.LBO_HOLDING_PERIOD_YEARS} JAAR)", "", "Bedrag", ""
	)
	voeg_rij_toe("Instapmultiple (volgens grootte)", None, rij["Instap_Multiple"], None, None, FMT_MULT, None)
	voeg_rij_toe("Indicatieve EV", None, rij["Indicatieve_EV"], None, None, FMT_EURO, None)
	voeg_rij_toe("Equity value verkoper (EV − Adj. Net Debt)", None, rij["Indicatieve_Equity_Value"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe("Transactie- en financieringskosten", None, rij["LBO_Kosten"], None, None, FMT_EURO, None)
	voeg_rij_toe(f"Senior lening ({rij['Senior_Multiple']}x)", None, rij["LBO_Senior_Schuld"], None, None, FMT_EURO, None)
	voeg_rij_toe("Vendor loan", None, rij["LBO_Vendor_Loan"], None, None, FMT_EURO, None)
	voeg_rij_toe("PE eigen inbreng (J0)", None, rij["LBO_Sponsor_Equity_Instap"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe("EBITDA jaar 5", None, rij["LBO_EBITDA_Jaar5"], None, None, FMT_EURO, None)
	voeg_rij_toe("Cumulatieve vrije kasstroom (5J)", None, rij["LBO_FCF_Cumulatief_5J"], None, None, FMT_EURO, None)
	voeg_rij_toe("Laagste DSCR", None, rij["LBO_Laagste_DSCR"], None, None, FMT_MULT, None)
	voeg_rij_toe("Laagste rentedekking", None, rij["LBO_Laagste_Rentedekking"], None, None, FMT_MULT, None)
	voeg_rij_toe("Hoogste Net Debt / EBITDA (bank-covenant)", None, rij["LBO_Hoogste_Leverage"], None, None, FMT_MULT, None)
	voeg_rij_toe("Laagste cash", None, rij["LBO_Laagste_Cash"], None, None, FMT_EURO, None)
	voeg_rij_toe(f"RCF-limiet ({config.LBO_RCF_LIMIET_X_EBITDA}x EBITDA)", None, rij["LBO_RCF_Limiet"], None, None, FMT_EURO, None)
	voeg_rij_toe("Hoogste RCF-trekking", None, rij["LBO_RCF_Piek"], None, None, FMT_EURO, None)
	voeg_rij_toe("RCF getrokken bij exit", None, rij["LBO_RCF_Eind"], None, None, FMT_EURO, None)
	voeg_tekstblok_toe("Convenanten", rij["LBO_Convenanten"])
	voeg_tekstblok_toe("Balanscheck model", rij["LBO_Balanscheck"])
	voeg_rij_toe("Net Debt jaar 5 (waardering)", None, rij["LBO_Eind_Net_Debt_Jaar5"], None, None, FMT_EURO, None)
	voeg_rij_toe("Net Debt / EBITDA jaar 5 (waardering)", None, rij["LBO_Eind_Net_Debt_to_EBITDA"], None, None, FMT_MULT, None)
	schuld_rij = voeg_rij_toe("Schuld < 2,0x binnen 5 jaar?", None, rij["LBO_Schuld_Onder_2x_5J"], None)
	_pas_status_kleur_toe(ws[f"D{schuld_rij}"], rij["LBO_Schuld_Onder_2x_5J"])
	ws[f"D{schuld_rij}"].alignment = Alignment(horizontal="center", vertical="center")
	voeg_rij_toe("Exit-EV (jaar 5)", None, rij["LBO_Exit_EV_Jaar5"], None, None, FMT_EURO, None)
	voeg_rij_toe("PE exit equity (jaar 5)", None, rij["LBO_Exit_Equity_Jaar5"], None, None, FMT_EURO, None, stijl="subtotaal")
	voeg_rij_toe("Indicatieve MoIC", None, rij["Indicatieve_MoIC"], None, None, FMT_MULT, None, stijl="eindtotaal")
	voeg_rij_toe("Indicatieve IRR", None, rij["Indicatieve_IRR_Pct"], None, None, FMT_PCT_MARGE, None, stijl="eindtotaal")
	voeg_rij_toe("Downside IRR", None, rij["LBO_Downside_IRR_Pct"], None, None, FMT_PCT_MARGE, None)
	voeg_rij_toe("Upside IRR", None, rij["LBO_Upside_IRR_Pct"], None, None, FMT_PCT_MARGE, None)
	voeg_tekstblok_toe("Convenanten in de downside", rij["LBO_Downside_Convenanten"])
	witruimte()

	# ---------------------------------------------------------------- Sectie 5
	voeg_sectiekop_toe("5. RED FLAGS & KWALITATIEF OORDEEL", "", "", "")
	voeg_tekstblok_toe("Verklaring commissaris", rij.get("Commissaris_Oordeel", ""))
	voeg_tekstblok_toe("Red flags", rij.get("Red_Flags", ""))
	voeg_tekstblok_toe("Kwalitatief LBO-oordeel", rij.get("Kwalitatief_LBO_Oordeel", ""))

	ws.freeze_panes = "A4"
	ws.sheet_view.zoomScale = 100


# ============================================================================
# 3-statement model
# ============================================================================
def _bouw_model_tab(wb, rij, historiek):
	ws = wb.create_sheet(title="3-Statement_Model")
	ws.views.sheetView[0].showGridLines = True

	jaren = rij["LBO_Jaren"]
	# Historiek (A) en forecast (F) in dezelfde lijnen: elke aanname is te toetsen aan de historiek
	kolommen = historiek[-config.LBO_MAX_JAREN:] + jaren
	laatste_kolom = get_column_letter(max(2 + len(kolommen), 8))

	naam = rij.get("Bedrijfsnaam", "Onbekend") or "Onbekend"
	ws.column_dimensions["A"].width = 3
	ws.column_dimensions["B"].width = 52

	ws.merge_cells(f"B2:{laatste_kolom}2")
	ws["B2"] = f"3-STATEMENT LBO-MODEL — {str(naam).upper()}"
	ws["B2"].font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
	ws["B2"].fill = PatternFill("solid", fgColor=NAVY_HEADER)
	ws["B2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
	ws.row_dimensions[2].height = 28

	if not jaren:
		ws.merge_cells(f"B4:{laatste_kolom}4")
		ws["B4"] = f"Geen LBO-projectie mogelijk: {rij['LBO_Convenanten']}."
		ws["B4"].font = Font(name="Calibri", size=11, bold=True, color="9C0006")
		ws["B4"].fill = PatternFill("solid", fgColor="FFC7CE")
		ws["B4"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
		ws.row_dimensions[4].height = 26
		return ws

	ws.merge_cells(f"B3:{laatste_kolom}3")
	ws["B3"] = (
		f"Aannames: instap en exit {rij['Instap_Multiple']}x | senior {rij['Senior_Multiple']}x, "
		f"{config.LBO_SENIOR_LOOPTIJD_JAAR} jaar, {config.LBO_SENIOR_RENTE:.1%} | "
		f"vendor loan {config.LBO_VENDOR_LOAN_PCT_EV:.0%} van EV, {config.LBO_VENDOR_LOAN_RENTE:.1%} | "
		f"RCF {config.LBO_RCF_LIMIET_X_EBITDA}x EBITDA, {config.LBO_RCF_RENTE:.1%}, commitment fee {config.LBO_RCF_COMMITMENT_FEE:.2%} | "
		f"cash sweep {config.LBO_CASH_SWEEP_PCT:.0%} van de excess cash flow | "
		f"rente op {config.LBO_RENTE_BASIS} saldo, cash {config.LBO_CASH_RENTE:.1%} | "
		f"goodwill {config.LBO_GOODWILL_LOOPTIJD_JAAR} jaar | closing {rij['LBO_Closing_Datum']}, duur {rij['LBO_Duur_Jaren']} jaar"
	)
	ws["B3"].font = Font(name="Calibri", size=9, italic=True, color="333333")
	ws["B3"].fill = PatternFill("solid", fgColor=TOTAAL_TINT)
	ws["B3"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
	ws.row_dimensions[3].height = 19

	rand_per_stijl = {"normaal": RAND_CEL, "subtotaal": RAND_SUBTOTAAL, "eindtotaal": RAND_EINDTOTAAL}
	regel_nr = 5

	def kop(titel, koppen):
		nonlocal regel_nr
		ws.row_dimensions[regel_nr].height = 23
		for k, tekst in enumerate([titel, *koppen]):
			letter = get_column_letter(2 + k)
			cel = ws[f"{letter}{regel_nr}"]
			cel.value = tekst
			cel.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
			cel.fill = PatternFill("solid", fgColor=SUB_HEADER)
			cel.alignment = Alignment(
				horizontal="left" if k == 0 else "center", vertical="center", indent=1 if k == 0 else 0
			)
			if k > 0:
				ws.column_dimensions[letter].width = 15
		regel_nr += 1

	def regel(label, waarden, fmt=FMT_EURO, stijl="normaal"):
		nonlocal regel_nr
		ws.row_dimensions[regel_nr].height = 19
		vet = stijl != "normaal"
		achtergrond = PatternFill("solid", fgColor=TOTAAL_TINT) if vet else None
		for k, waarde in enumerate([label, *waarden]):
			cel = ws[f"{get_column_letter(2 + k)}{regel_nr}"]
			cel.value = _leeg_als_nan(waarde)
			cel.font = Font(name="Calibri", size=10, bold=vet)
			cel.border = rand_per_stijl[stijl]
			if k == 0:
				cel.alignment = Alignment(horizontal="left", vertical="center", indent=1)
			else:
				cel.number_format = fmt
				cel.alignment = Alignment(horizontal="right", vertical="center")
			if achtergrond:
				cel.fill = achtergrond
		regel_nr += 1

	def tekstregel(label, tekst):
		nonlocal regel_nr
		ws.row_dimensions[regel_nr].height = 32
		ws.merge_cells(f"C{regel_nr}:{laatste_kolom}{regel_nr}")
		for kolom, waarde in (("B", label), ("C", tekst)):
			cel = ws[f"{kolom}{regel_nr}"]
			cel.value = waarde
			cel.font = Font(name="Calibri", size=10)
			cel.alignment = Alignment(horizontal="left", vertical="center", indent=1, wrap_text=True)
		regel_nr += 1

	def reeks(sleutel):
		return [kolom.get(sleutel) for kolom in kolommen]

	groei_base = config.LBO_SCENARIOS["base"]

	kop("KERNCIJFERS PER SCENARIO", [config.LBO_SCENARIOS[naam]["label"] for naam in config.LBO_SCENARIOS])
	scenarios = list(rij["LBO_Scenarios"].values())
	regel("Prijsgroei", [config.LBO_SCENARIOS[naam]["prijsgroei"] * 100 for naam in config.LBO_SCENARIOS], FMT_PCT_GROEI)
	regel("Loonindexering", [config.LBO_SCENARIOS[naam]["indexering"] * 100 for naam in config.LBO_SCENARIOS], FMT_PCT_GROEI)
	regel("Indicatieve IRR", [model["Indicatieve_IRR_Pct"] for model in scenarios], FMT_PCT_MARGE, stijl="subtotaal")
	regel("Indicatieve MoIC", [model["Indicatieve_MoIC"] for model in scenarios], FMT_MULT, stijl="subtotaal")
	regel("EBITDA exit", [model["LBO_EBITDA_Jaar5"] for model in scenarios])
	regel("EBITDA-marge exit", [model["LBO_EBITDA_Marge_Exit_Pct"] for model in scenarios], FMT_PCT_MARGE)
	regel("Laagste DSCR", [model["LBO_Laagste_DSCR"] for model in scenarios], FMT_MULT)
	regel("Hoogste Net Debt / EBITDA (bank-covenant)", [model["LBO_Hoogste_Leverage"] for model in scenarios], FMT_MULT)
	regel("Hoogste RCF-trekking", [model["LBO_RCF_Piek"] for model in scenarios])
	regel("Laagste cash", [model["LBO_Laagste_Cash"] for model in scenarios])
	regel("Integriteitstesten", [model["LBO_Balanscheck"] for model in scenarios], "@")
	for naam, model in rij["LBO_Scenarios"].items():
		tekstregel(f"Convenanten {config.LBO_SCENARIOS[naam]['label'].lower()}", model["LBO_Convenanten"])
	regel_nr += 1

	kop(f"DRIVERS (uit {rij['Driver_Aantal_Jaren']} boekjaren)", ["Waarde"])
	regel("Historische omzet-CAGR", [rij["Driver_Historische_CAGR_Pct"]], FMT_PCT_GROEI)
	regel("Historische EBITDA-CAGR", [rij["Driver_EBITDA_CAGR_Pct"]], FMT_PCT_GROEI)
	regel("Omzetgroei in de base (begrensd, volume × prijs)", [rij["Driver_Omzetgroei_Pct"]], FMT_PCT_GROEI)
	regel("Prijsgroei in de base", [groei_base["prijsgroei"] * 100], FMT_PCT_GROEI)
	regel("VTE-elasticiteit op volume", [config.LBO_VTE_ELASTICITEIT], "0.00")
	regel(f"Inkoop: doelratio na {config.LBO_KOSTEN_GLIDE_JAREN} jaar (hoogste van gemiddelde en laatste)", [rij["Driver_Inkoop_Pct"]], FMT_PCT_MARGE)
	regel(f"Overige kosten: doelratio na {config.LBO_KOSTEN_GLIDE_JAREN} jaar (hoogste van gemiddelde en laatste)", [rij["Driver_Overige_Kosten_Pct"]], FMT_PCT_MARGE)
	regel("Referentie: gemiddelde historische EBITDA-marge", [rij["Driver_EBITDA_Marge_Gemiddeld_Pct"]], FMT_PCT_MARGE)
	regel("D&A bestaande activa als % van openingswaarde", [rij["Driver_DA_Pct_Vaste_Activa"]], FMT_PCT_MARGE)
	regel(f"Capex als % van omzet/brutomarge ({config.LBO_CAPEX_LEVENSDUUR_JAAR} jaar lineair)", [rij["Driver_Capex_Pct"]], FMT_PCT_MARGE)
	regel_nr += 1

	kop("BRONNEN EN BESTEDINGEN", ["Bedrag"])
	regel("Senior lening", [rij["LBO_Senior_Schuld"]])
	regel("Vendor loan", [rij["LBO_Vendor_Loan"]])
	regel("Sponsor equity", [rij["LBO_Sponsor_Equity_Instap"]])
	regel("Totaal bronnen", [rij["LBO_Senior_Schuld"] + rij["LBO_Vendor_Loan"] + rij["LBO_Sponsor_Equity_Instap"]], stijl="subtotaal")
	regel("Aankoop aandelen (equity value verkoper)", [rij["Indicatieve_Equity_Value"]])
	regel("Vereffening Adjusted Net Debt", [rij["Adjusted_Net_Debt"]])
	regel("Transactiekosten (in de goodwill)", [rij["LBO_Transactiekosten"]])
	regel("Financieringskosten (geactiveerd)", [rij["LBO_Financieringskosten"]])
	regel(
		"Totaal bestedingen",
		[rij["Indicatieve_Equity_Value"] + rij["Adjusted_Net_Debt"] + rij["LBO_Kosten"]],
		stijl="subtotaal",
	)
	regel("Memo: RCF-limiet (niet getrokken bij closing)", [rij["LBO_RCF_Limiet"]])
	regel_nr += 1

	koppen = [kolom["Label"] for kolom in kolommen]
	kop("RESULTATENREKENING (BASE)", koppen)
	regel("Omzet / brutomarge", reeks("Omzet"))
	regel("Af: handelsgoederen en diensten (60/61)", reeks("Inkoop"))
	regel("Af: personeelskost (62)", reeks("Personeel"))
	regel("Af: overige bedrijfskosten, netto", reeks("Overige_Kosten"))
	regel("EBITDA (genormaliseerd)", reeks("EBITDA"), stijl="subtotaal")
	regel("Af: afschrijvingen op vaste activa", reeks("Afschrijvingen"))
	regel("Af: goodwillafschrijving", reeks("Goodwill_Afschrijving"))
	regel("Af: niet-recurrent en voorzieningen (historiek)", reeks("Niet_Recurrent"))
	regel("EBIT", reeks("EBIT"), stijl="subtotaal")
	regel("Financieel resultaat", reeks("Financieel_Resultaat"))
	regel("Winst vóór belasting", reeks("Winst_Voor_Belasting"), stijl="subtotaal")
	regel("Af: belasting", reeks("Belasting"))
	regel("Nettowinst", reeks("Nettowinst"), stijl="eindtotaal")
	regel_nr += 1

	kop("KERNRATIO'S", koppen)
	regel("Omzetgroei (op jaarbasis)", reeks("Omzetgroei_Pct"), FMT_PCT_GROEI)
	regel("Inkoop / omzet", reeks("Inkoop_Pct"), FMT_PCT_MARGE)
	regel("Personeel / omzet", reeks("Personeel_Pct"), FMT_PCT_MARGE)
	regel("Overige kosten / omzet", reeks("Overige_Pct"), FMT_PCT_MARGE)
	regel("EBITDA-marge", reeks("EBITDA_Marge_Pct"), FMT_PCT_MARGE, stijl="subtotaal")
	regel("VTE", reeks("VTE"), "0.0")
	regel("Kost per VTE (op jaarbasis)", reeks("Kost_Per_VTE"))
	regel("Capex / omzet", reeks("Capex_Pct"), FMT_PCT_MARGE)
	regel("DSO", reeks("DSO"), FMT_DAGEN)
	regel("DIO", reeks("DIO"), FMT_DAGEN)
	regel("DPO", reeks("DPO"), FMT_DAGEN)
	regel_nr += 1

	kop("BALANS (BASE)", koppen)
	regel("Goodwill", reeks("Goodwill"))
	regel("Geactiveerde financieringskosten", reeks("Geactiveerde_Financieringskosten"))
	regel("Vaste activa", reeks("Vaste_Activa"))
	regel("Financiële vaste activa", reeks("Financiele_Vaste_Activa"))
	regel("Voorraden", reeks("Voorraden"))
	regel("Handelsvorderingen", reeks("Handelsvorderingen"))
	regel("Overige activa, operationeel", reeks("Overige_Activa_Operationeel"))
	regel("Overige activa, niet-operationeel (groep, bestuurders)", reeks("Overige_Activa_Niet_Operationeel"))
	regel("Cash", reeks("Cash"))
	regel("Totaal activa", reeks("Totaal_Activa"), stijl="eindtotaal")
	regel("Eigen vermogen", reeks("Eigen_Vermogen"))
	regel("Senior lening (historiek: bestaande financiële schuld)", reeks("Senior_Lening"))
	regel("RCF", reeks("RCF"))
	regel("Vendor loan", reeks("Vendor_Loan"))
	regel("Handelsschulden", reeks("Handelsschulden"))
	regel("Ontvangen vooruitbetalingen", reeks("Vooruitbetalingen"))
	regel("Sociale schulden", reeks("Sociale_Schulden"))
	regel("Overige passiva (historiek: incl. debt-like items)", reeks("Overige_Passiva"))
	regel("Totaal passiva", reeks("Totaal_Passiva"), stijl="eindtotaal")
	regel("Balanscheck (activa − passiva)", reeks("Balansverschil"), '€ #,##0;[Red]-€ #,##0;"OK"')
	regel_nr += 1

	kop("KASSTROOMTABEL (INDIRECTE METHODE)", koppen)
	regel("Nettowinst", reeks("Nettowinst"))
	regel("Bij: afschrijvingen op vaste activa", reeks("Afschrijvingen"))
	regel("Bij: goodwillafschrijving", reeks("Goodwill_Afschrijving"))
	regel("Bij: afschrijving financieringskosten", reeks("Afschrijving_Financieringskosten"))
	regel("Mutatie voorraden", reeks("KS_Voorraden"))
	regel("Mutatie handelsvorderingen", reeks("KS_Handelsvorderingen"))
	regel("Mutatie overige activa", reeks("KS_Overige_Activa_Operationeel"))
	regel("Mutatie handelsschulden", reeks("KS_Handelsschulden"))
	regel("Mutatie ontvangen vooruitbetalingen", reeks("KS_Vooruitbetalingen"))
	regel("Mutatie sociale schulden", reeks("KS_Sociale_Schulden"))
	regel("Mutatie overige passiva", reeks("KS_Overige_Passiva"))
	regel("Operationele kasstroom", reeks("KS_Operationeel"), stijl="subtotaal")
	regel("Af: capex", reeks("Capex"))
	regel("Kasstroom vóór financiering", reeks("KS_Voor_Financiering"), stijl="subtotaal")
	regel("Af: verplichte aflossing", reeks("Verplichte_Aflossing"))
	regel("Af: cash sweep", reeks("Cash_Sweep"))
	regel("Bij: opname RCF", reeks("RCF_Opname"))
	regel("Af: terugbetaling RCF", reeks("RCF_Aflossing"))
	regel("Af: dividend", reeks("Dividend"))
	regel("Financieringskasstroom", reeks("KS_Financiering"), stijl="subtotaal")
	regel("Netto kasstroom", reeks("KS_Netto"), stijl="subtotaal")
	regel("Cash einde periode (naar de balans)", reeks("Cash"), stijl="eindtotaal")
	regel_nr += 1

	kop("SCHULDWATERVAL (DIRECTE METHODE)", koppen)
	regel("EBITDA", [kolom.get("EBITDA") if "Fractie" in kolom else None for kolom in kolommen])
	regel("Af: belasting", [kolom.get("Belasting") if "Fractie" in kolom else None for kolom in kolommen])
	regel("Af: capex", [kolom.get("Capex") if "Fractie" in kolom else None for kolom in kolommen])
	regel("Af: toename trade working capital", reeks("Delta_TWC"))
	regel("Af: toename overig werkkapitaal", reeks("Delta_Overig"))
	regel("Af: rente en commitment fee", reeks("Rente"))
	regel("Bij: renteopbrengst op cash", reeks("Rente_Opbrengst"))
	regel("Vrije kasstroom", reeks("FCF"), stijl="subtotaal")
	regel("Af: verplichte aflossing", reeks("Verplichte_Aflossing"))
	regel("Excess cash flow", reeks("Excess_Cash_Flow"), stijl="subtotaal")
	regel("Bij: opname RCF", reeks("RCF_Opname"))
	regel("Af: terugbetaling RCF", reeks("RCF_Aflossing"))
	regel(f"Af: cash sweep ({config.LBO_CASH_SWEEP_PCT:.0%} van de excess cash flow)", reeks("Cash_Sweep"))
	regel("Af: dividend", reeks("Dividend"))
	regel("Cash einde periode volgens de waterval", reeks("Cash_Waterval"), stijl="eindtotaal")
	regel_nr += 1

	kop("SCHULDSCHEMA PER TRANCHE", koppen)
	regel("Senior: begin", reeks("Senior_Begin"))
	regel("Af: verplichte aflossing", reeks("Verplichte_Aflossing"))
	regel("Af: cash sweep", reeks("Cash_Sweep"))
	regel("Senior: einde", [kolom.get("Senior_Lening") if "Jaar" in kolom else None for kolom in kolommen], stijl="subtotaal")
	regel("RCF: begin", reeks("RCF_Begin"))
	regel("Bij: opname", reeks("RCF_Opname"))
	regel("Af: terugbetaling", reeks("RCF_Aflossing"))
	regel("RCF: einde", reeks("RCF"), stijl="subtotaal")
	regel("RCF: ongebruikte ruimte", reeks("RCF_Ruimte"))
	regel("Vendor loan: einde (bullet bij exit)", reeks("Vendor_Loan"), stijl="subtotaal")
	regel("Rente senior", reeks("Rente_Senior"))
	regel("Rente RCF", reeks("Rente_RCF"))
	regel("Commitment fee RCF", reeks("Commitment_Fee"))
	regel("Rente vendor loan", reeks("Rente_Vendor"))
	regel("Totaal cash-rente", reeks("Rente"), stijl="subtotaal")
	regel("Renteopbrengst op cash", reeks("Rente_Opbrengst"))
	regel("Afschrijving financieringskosten (niet-kas)", reeks("Afschrijving_Financieringskosten"))
	regel_nr += 1

	kop("BANKABILITEIT EN CONVENANTEN", koppen)
	regel(f"Rentedekking EBITDA / rente (min. {config.LBO_COVENANT_MIN_RENTEDEKKING:.1f}x)", reeks("Rentedekking"), FMT_MULT)
	regel(f"DSCR (min. {config.LBO_COVENANT_MIN_DSCR:.2f}x)", reeks("DSCR"), FMT_MULT)
	regel(f"Net Debt / EBITDA op jaarbasis, bank-covenant (max. {config.LBO_COVENANT_MAX_LEVERAGE:.1f}x)", reeks("Leverage"), FMT_MULT)
	regel("Net Debt (bank-covenant)", reeks("Net_Debt_Bank_Covenant"))
	regel("Net Debt (waardering)", reeks("Net_Debt_Waardering"))
	regel_nr += 1

	kop("INTEGRITEITSTESTEN (BASE)", ["Uitkomst", "Afwijking", "Tolerantie"])
	for test in rij["LBO_Integriteit"]:
		tolerantie = f"< € {test['Tolerantie']}" if test["Tolerantie"] else "Exact"
		regel(f"{test['Test']}: {test['Definitie']}", [test["Uitkomst"], test["Afwijking"], tolerantie])
	regel_nr += 1

	kop("DEFINITIES NET DEBT", ["Definitie"])
	for doel, definitie in config.NET_DEBT_DEFINITIES.items():
		tekstregel(definitie["label"].capitalize(), net_debt_formule(doel))

	ws.freeze_panes = "C5"
	return ws


# ============================================================================
# Meerjarentab
# ============================================================================
def _bouw_meerjaren_tab(wb, rij, jaren):
	ws = wb.create_sheet(title="Meerjarencijfers")
	ws.views.sheetView[0].showGridLines = True

	naam = rij.get("Bedrijfsnaam", "Onbekend") or "Onbekend"
	laatste_kolom = get_column_letter(2 + len(jaren))
	ws.column_dimensions["A"].width = 3
	ws.column_dimensions["B"].width = 44

	ws.merge_cells(f"B2:{laatste_kolom}2")
	ws["B2"] = f"MEERJARENCIJFERS — {str(naam).upper()}"
	ws["B2"].font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
	ws["B2"].fill = PatternFill("solid", fgColor=NAVY_HEADER)
	ws["B2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
	ws.row_dimensions[2].height = 28

	ws.merge_cells(f"B3:{laatste_kolom}3")
	ws["B3"] = f"Bron: NBB-CSV per boekjaar | {rij['Omzet_Basis']}"
	ws["B3"].font = Font(name="Calibri", size=9, italic=True, color="333333")
	ws["B3"].fill = PatternFill("solid", fgColor=TOTAAL_TINT)
	ws["B3"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
	ws.row_dimensions[3].height = 19

	ws.row_dimensions[5].height = 23
	cel = ws["B5"]
	cel.value = "Post (in €)"
	cel.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
	cel.fill = PatternFill("solid", fgColor=SUB_HEADER)
	cel.alignment = Alignment(horizontal="left", vertical="center", indent=1)
	for k, jaar in enumerate(jaren):
		letter = get_column_letter(3 + k)
		ws.column_dimensions[letter].width = 17
		cel = ws[f"{letter}5"]
		cel.value = jaar["Boekjaar"]
		cel.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
		cel.fill = PatternFill("solid", fgColor=SUB_HEADER)
		cel.alignment = Alignment(horizontal="center", vertical="center")

	# (sleutel, label, formaat, stijl)
	regels = [
		("Maanden", "Lengte boekjaar (maanden)", "0", "normaal"),
		("Omzet", "Omzet / brutomarge (per 12 maanden)", FMT_EURO, "normaal"),
		("Brutomarge", "Brutomarge (vergelijkbaar)", FMT_EURO, "normaal"),
		("EBIT", "Bedrijfswinst (EBIT)", FMT_EURO, "normaal"),
		("Afschrijvingen", "Afschrijvingen (630)", FMT_EURO, "normaal"),
		("Voorzieningen", "Voorzieningen (635/8)", FMT_EURO, "normaal"),
		("EBITDA", "Gerapporteerde EBITDA", FMT_EURO, "subtotaal"),
		("Normalisatie", "Normalisatie (66A − 76A)", FMT_EURO, "normaal"),
		("Genormaliseerde_EBITDA", "Genormaliseerde EBITDA", FMT_EURO, "eindtotaal"),
		("Genorm_Marge_Pct", "Genorm. EBITDA-marge op omzet", FMT_PCT_MARGE, "normaal"),
		("Marge_Op_Brutomarge_Pct", "Genorm. EBITDA-marge op brutomarge", FMT_PCT_MARGE, "normaal"),
		("Waardeverminderingen", "Waardeverminderingen (631/4), niet teruggeteld", FMT_EURO, "normaal"),
		("Capex", "Capex (aanschaffingen MVA/IVA)", FMT_EURO, "normaal"),
		("DSO", "DSO (klantentermijn)", FMT_DAGEN, "normaal"),
		("DIO", "DIO (voorraadrotatie)", FMT_DAGEN, "normaal"),
		("DPO", "DPO (leverancierstermijn)", FMT_DAGEN, "normaal"),
		("Financiele_Schuld", "Financiële schuld", FMT_EURO, "normaal"),
		("Liquide_Middelen", "Liquide middelen", FMT_EURO, "normaal"),
		("Net_Debt", "Net Debt (financiële schuld − liquide middelen)", FMT_EURO, "subtotaal"),
		("Eigen_Vermogen", "Eigen vermogen", FMT_EURO, "normaal"),
		("Balanstotaal", "Balanstotaal", FMT_EURO, "normaal"),
		("VTE", "Gemiddeld aantal VTE", "0.0", "normaal"),
	]
	rand_per_stijl = {"normaal": RAND_CEL, "subtotaal": RAND_SUBTOTAAL, "eindtotaal": RAND_EINDTOTAAL}

	for r_idx, (sleutel, label, fmt, stijl) in enumerate(regels, start=6):
		ws.row_dimensions[r_idx].height = 19
		vet = stijl != "normaal"
		achtergrond = PatternFill("solid", fgColor=TOTAAL_TINT) if vet else None

		cel = ws[f"B{r_idx}"]
		cel.value = label
		cel.font = Font(name="Calibri", size=10, bold=vet)
		cel.alignment = Alignment(horizontal="left", vertical="center", indent=1)
		cel.border = rand_per_stijl[stijl]
		if achtergrond:
			cel.fill = achtergrond

		for k, jaar in enumerate(jaren):
			cel = ws[f"{get_column_letter(3 + k)}{r_idx}"]
			cel.value = _leeg_als_nan(jaar[sleutel])
			cel.number_format = fmt
			cel.font = Font(name="Calibri", size=10, bold=vet)
			cel.alignment = Alignment(horizontal="right", vertical="center")
			cel.border = rand_per_stijl[stijl]
			if achtergrond:
				cel.fill = achtergrond

	ws.freeze_panes = "C6"
	return ws


# ============================================================================
# Publieke functie: één Excel-fiche per bedrijf
# ============================================================================
def schrijf_per_bedrijf(df, meerjaren):
	"""Schrijft per bedrijf een apart bestand (Tear Sheet, 3-Statement Model, Meerjaren). Geeft lijst van paden."""
	tijdstempel = datetime.now().strftime("%Y%m%d_%H%M")
	gebruikte_namen = set()
	paden = []

	for _, rij in df.iterrows():
		basis = veilige_bestandsnaam(rij.get("Bedrijfsnaam"))
		naam, teller = basis, 2
		while naam in gebruikte_namen:  # twee PDF's met dezelfde bedrijfsnaam overschrijven elkaar niet
			naam = f"{basis}_{teller}"
			teller += 1
		gebruikte_namen.add(naam)

		pad = config.OUTPUT_FOLDER / f"LBO_Fiche_{naam}_{tijdstempel}.xlsx"
		wb = Workbook()
		_bouw_tear_sheet(wb, rij)
		jaren = meerjaren[rij["Ondernemingsnummer"]]
		_bouw_model_tab(wb, rij, [jaar["Model"] for jaar in jaren])
		_bouw_meerjaren_tab(wb, rij, jaren)
		paden.append(_veilig_opslaan(wb, pad))

	return paden
