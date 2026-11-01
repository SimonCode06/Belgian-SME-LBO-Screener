"""Phase 6.6: the sensitivity tables (Python, static) and their tab in the workbook."""
import pytest

from src import config, excel_model, labels, sensitiviteit
from src.calculations import bouw_dataframe
from src.nbb_csv import bouw_meerjaren


@pytest.fixture
def rij(cijfers):
	return bouw_dataframe([cijfers]).iloc[0]


def test_the_middle_cell_is_the_screening_base(rij):
	tabellen = sensitiviteit.analyseer(rij)
	verwacht = rij["LBO_Scenarios"]["screening_base"]["LBO_IRR_Exact_Pct"] / 100
	for tabel in tabellen.values():
		assert tabel.irr[2][2] == pytest.approx(verwacht, abs=1e-9)


def test_irr_moves_the_right_way(rij):
	tabellen = sensitiviteit.analyseer(rij)
	multiples, ebitda = tabellen["instap_exit"], tabellen["ebitda_senior"]
	assert multiples.irr[2] == sorted(multiples.irr[2])  # higher exit multiple, higher IRR
	assert [r[2] for r in multiples.irr] == sorted((r[2] for r in multiples.irr), reverse=True)  # higher entry, lower IRR
	assert [r[2] for r in ebitda.irr] == sorted(r[2] for r in ebitda.irr)  # more EBITDA, higher IRR
	assert ebitda.rijen == list(sensitiviteit.EBITDA_STAPPEN)


def test_more_senior_debt_breaks_covenants_first_in_the_low_ebitda_row(rij):
	ebitda = sensitiviteit.analyseer(rij)["ebitda_senior"]
	# A covenant that fails at some debt level also fails with more debt and with less EBITDA
	for i, rij_breuk in enumerate(ebitda.breuk):
		assert rij_breuk == sorted(rij_breuk)
		if i:
			assert all(boven <= onder for boven, onder in zip(rij_breuk, ebitda.breuk[i - 1]))


def test_workbook_tab_with_disclaimer_colour_scale_and_base_cell(rij, filings):
	wb, kaart = excel_model.bouw_werkboek(rij, [jaar["Model"] for jaar in bouw_meerjaren(filings)])
	ws = wb[labels.TAB_SENSITIVITIES]
	assert wb.sheetnames.index(labels.TAB_SENSITIVITIES) == wb.sheetnames.index(labels.TAB_LBO) + 1
	assert "do not update dynamically with Excel overrides" in ws["A3"].value
	verwacht = rij["LBO_Scenarios"]["screening_base"]["LBO_IRR_Exact_Pct"] / 100
	assert len(kaart["sens_basis"]) == 2
	for adres in kaart["sens_basis"]:
		cel = ws[adres]
		assert cel.value == pytest.approx(verwacht)
		assert cel.font.color.rgb.endswith("0000FF") and cel.border.left.style == "medium"
	regels = [regel for bereik in ws.conditional_formatting for regel in bereik.rules if regel.colorScale]
	assert len(regels) == 2
	assert float(regels[0].colorScale.cfvo[1].val) == pytest.approx(config.LBO_MIN_IRR_PCT / 100)
