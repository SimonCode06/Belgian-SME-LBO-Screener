"""The Excel output in output/.

schrijf_overzicht: the comparison workbook over all companies (Python results).
schrijf_per_bedrijf: one live, formula-driven workbook per company (see excel_model.py).
"""
import re
import time
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from . import config, labels
from . import excel_stijl as stijl
from .excel_model import bouw_lege_fiche, bouw_werkboek

def veilige_bestandsnaam(naam, fallback=labels.UNKNOWN_COMPANY):
	naam = (naam or "").strip() or fallback
	naam = re.sub(r"[^\w\s-]", "", naam, flags=re.UNICODE)
	naam = re.sub(r"\s+", "_", naam).strip("_")
	return naam[:80] or fallback


def _leeg_als_nan(waarde):
	"""Een ontbrekend cijfer wordt een lege cel."""
	return None if isinstance(waarde, float) and pd.isna(waarde) else waarde


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
	("Eigendom", labels.GROUP_IDENTIFICATION, 34),
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
	("LBO_Screening_IRR_Pct", labels.GROUP_SCREENING, 10),
	("LBO_Screening_Convenanten", labels.GROUP_SCREENING, 22),
	("LBO_Stress_IRR_Pct", labels.GROUP_SCREENING, 10),
	("LBO_Stress_Laagste_DSCR", labels.GROUP_SCREENING, 10),
	("LBO_Stress_Convenanten", labels.GROUP_SCREENING, 28),
	("Debt_Capacity_Multiple", labels.GROUP_STRUCTURE, 11),
	("Debt_Capacity_Bindend", labels.GROUP_STRUCTURE, 14),
	("ATP_Max_Entry_Multiple", labels.GROUP_STRUCTURE, 11),
	("ATP_Headroom_Pct", labels.GROUP_STRUCTURE, 11),
	("ATP_AI_Max_Entry_Multiple", labels.GROUP_STRUCTURE, 11),
]

TEKST_KOLOMMEN = {
	"Data_Volledigheid",
	"Check_Data",
	"Normalisatie_Toelichting",
	"Normalisatie_Voorstellen",
	"Buitenbalans_Verplichtingen",
	"LBO_Convenanten",
	"LBO_Downside_Convenanten",
	"LBO_Screening_Convenanten",
	"LBO_Stress_Convenanten",
	"Debt_Capacity_Bindend",
	"Debt_Capacity_Status",
	"ATP_Status",
	"ATP_AI_Status",
	"Red_Flags",
	"Eigendom",
	"Kwalitatief_LBO_Oordeel",
	"AI_Business_Model",
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
	"NWC_Peg_Pct",
	"Indicatieve_IRR_Pct",
	"LBO_Downside_IRR_Pct",
	"LBO_Upside_IRR_Pct",
	"LBO_Screening_IRR_Pct",
	"LBO_Stress_IRR_Pct",
	"ATP_IRR_Pct",
	"ATP_Headroom_Pct",
	"ATP_AI_Headroom_Pct",
	"LBO_IRR_Exact_Pct",
	"LBO_Forecast_Groei_Pct",
	"LBO_EBITDA_Marge_Exit_Pct",
}
DAGEN_KOLOMMEN = {"Driver_DSO_Excl_BTW", "Driver_DSO", "Driver_DIO", "Driver_DPO", "Driver_Dagen_Vooruitbetaling"}
GETAL_KOLOMMEN = {"NWC_Peg_Jaren", "Capex_Aantal_Jaren", "Driver_Aantal_Jaren", "VTE", "LBO_Duur_Jaren", "Boekjaar_Maanden", "Boekjaar_Maanden_Vorig_Jaar"}
MULT_KOLOMMEN = {
	"Instap_Multiple",
	"Senior_Multiple",
	"LBO_Laagste_DSCR",
	"LBO_Laagste_Rentedekking",
	"LBO_Hoogste_Leverage",
	"LBO_Downside_MoIC",
	"LBO_Screening_MoIC",
	"Debt_Capacity_Multiple",
	"ATP_Senior_Multiple",
	"ATP_Max_Entry_Multiple",
	"ATP_AI_Max_Entry_Multiple",
	"LBO_Stress_Laagste_DSCR",
	"LBO_MoIC_Exact",
	"Huidige_Net_Debt_to_EBITDA",
	"LBO_Eind_Net_Debt_to_EBITDA",
	"Indicatieve_MoIC",
}
GEEN_BEDRAG_KOLOMMEN = {"Boekjaar", "Boekjaar_Begin", "Boekjaar_Einde", "LBO_Closing_Datum", "Ondernemingsnummer"}
OBJECT_KOLOMMEN = [
	"LBO_Jaren", "LBO_Integriteit", "LBO_Scenarios", "LBO_Assumpties", "LBO_Assumptie_Vlaggen", "LBO_Driver_Pack",
	"AI_Normalisaties", "LBO_Adjustments", "AI_Red_Flags", "AI_Eigendom", "AI_Buitenbalans", "AI_Investment_Thesis", "AI_DD_Vragen",
]


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
		(labels.FOOTER_RUN, str(df["Run_Manifest"].iloc[0]) if "Run_Manifest" in df else "-"),
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
# 2. Company workbooks: the live model per company
# ============================================================================
def schrijf_per_bedrijf(df, meerjaren):
	"""Writes one workbook per company (Executive Summary, 3-Statement Model, LBO Analysis). Returns the paths."""
	tijdstempel = datetime.now().strftime("%Y%m%d_%H%M")
	gebruikte_namen = set()
	paden = []

	for _, rij in df.iterrows():
		basis = veilige_bestandsnaam(rij.get("Bedrijfsnaam"))
		naam, teller = basis, 2
		while naam in gebruikte_namen:  # two companies with the same name do not overwrite each other
			naam = f"{basis}_{teller}"
			teller += 1
		gebruikte_namen.add(naam)

		pad = config.OUTPUT_FOLDER / f"{labels.COMPANY_FILE}_{naam}_{tijdstempel}.xlsx"
		historiek = [jaar["Model"] for jaar in meerjaren[rij["Ondernemingsnummer"]]]
		if rij["LBO_Jaren"]:
			wb, _ = bouw_werkboek(rij, historiek)
		else:
			wb = bouw_lege_fiche(rij, historiek)
		paden.append(_veilig_opslaan(wb, pad))

	return paden
