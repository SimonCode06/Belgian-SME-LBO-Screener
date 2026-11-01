"""The formatting standard of every workbook: colours, number formats, borders and page setup."""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import labels

LETTERTYPE = "Calibri"
GROOTTE = 10

BLAUW = "0000FF"   # hardcoded input, AI proposal, historical NBB value
ZWART = "000000"   # formula
GROEN = "006100"   # direct link to another tab
WIT = "FFFFFF"
ROOD = "9C0006"

KOP_DONKER = "1F3864"
VULLING_OVERRIDE = "FFF2CC"
VULLING_ACTUAL = "F2F2F2"
VULLING_OK = "C6EFCE"
VULLING_FOUT = "FFC7CE"

FMT_BEDRAG = '#,##0,_);(#,##0,);"-"_)'
FMT_PCT = "0.0%"
FMT_MULT = '0.0"x"'
FMT_MULT_2 = '0.00"x"'
FMT_DAGEN = '0.0 "d"'
FMT_PP = '0.0 "pp"'
FMT_GETAL = "0.0"
FMT_INDEX = "0.00"
FMT_DATUM = "yyyy-mm-dd"

DUN = Side(style="thin", color="000000")
DUN_GRIJS = Side(style="thin", color="BFBFBF")
DUBBEL = Side(style="double", color="000000")

RAND_SUBTOTAAL = Border(top=DUN)
RAND_EINDTOTAAL = Border(top=DUN, bottom=DUBBEL)
RAND_OVERRIDE = Border(left=DUN_GRIJS, right=DUN_GRIJS, top=DUN_GRIJS, bottom=DUN_GRIJS)

VUL_SECTIE = PatternFill("solid", fgColor=KOP_DONKER)
VUL_OVERRIDE = PatternFill("solid", fgColor=VULLING_OVERRIDE)
VUL_ACTUAL = PatternFill("solid", fgColor=VULLING_ACTUAL)


def lettertype(kleur=ZWART, vet=False, cursief=False, grootte=GROOTTE, onderstreept=False):
	return Font(
		name=LETTERTYPE, size=grootte, bold=vet, italic=cursief, color=kleur, underline="single" if onderstreept else None
	)


def sectiekop(cel, tekst=None):
	"""Dark blue section header with white text."""
	if tekst is not None:
		cel.value = tekst
	cel.font = lettertype(WIT, vet=True)
	cel.fill = VUL_SECTIE
	cel.alignment = Alignment(vertical="center")


def status_kleur(cel, tekst):
	"""Colours a status or YES/NO cell by the start of its text."""
	waarde = str(tekst or "")
	for sleutel, (achtergrond, voorgrond) in labels.STATUS_COLOURS.items():
		if waarde.startswith(sleutel):
			cel.fill = PatternFill("solid", fgColor=achtergrond)
			cel.font = lettertype(voorgrond, vet=True)
			return
