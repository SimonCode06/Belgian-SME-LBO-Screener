"""Phase 6: the workbook standard, checked without Excel (openpyxl only, so it runs in CI on Linux)."""
import pytest

from src import excel_model, labels
from src import excel_stijl as stijl
from src.calculations import bouw_dataframe
from src.nbb_csv import bouw_meerjaren


@pytest.fixture
def boek(cijfers, filings):
	rij = bouw_dataframe([cijfers]).iloc[0]
	return excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(filings)])


def test_value_creation_bridge_and_waterfall_chart(boek):
	"""Stacked bar waterfall: four series (base, total, increase, decrease), the base series without fill."""
	wb, kaart = boek
	lbo = wb[labels.TAB_LBO]
	rl = kaart["rijen"]["lbo"]
	assert lbo[f"C{rl['vc_start']}"].value == "=Sponsor_Equity"
	assert lbo[f"C{rl['vc_end']}"].value == f"=SUM(C{rl['vc_start']}:C{rl['vc_div']})"
	assert lbo[f"C{rl['vc_check']}"].value.startswith(f"=C{rl['vc_end']}-")
	grafiek = lbo._charts[0]
	assert grafiek.grouping == "stacked" and grafiek.overlap == 100 and len(grafiek.series) == 4
	assert grafiek.series[0].graphicalProperties.noFill


def test_risks_tab_lists_every_flag_with_a_filter_and_reads_the_ledger(cijfers, filings):
	from tests.test_correcties import ledger_item

	rij = bouw_dataframe([{**cijfers, "LBO_Adjustments": [ledger_item()]}]).iloc[0]
	wb, _ = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(filings)])
	ws = wb[labels.TAB_RISKS]
	assert ws.auto_filter.ref.startswith("A5:F")
	ernst = [ws.cell(row=r, column=1).value for r in range(6, 6 + len(rij["Red_Flag_Lijst"]))]
	assert ernst == [labels.SEVERITIES[vlag["ernst"]] for vlag in rij["Red_Flag_Lijst"]]
	links = [cel.value for regel in ws.iter_rows() for cel in regel if isinstance(cel.value, str) and cel.value.startswith("='Inputs")]
	assert [link.split("!")[1][0] for link in links] == ["C", "F", "G"]  # amount, switch and effect on the inputs tab
	assert any(cel.value == "=Ledger_Total" for regel in ws.iter_rows() for cel in regel)
