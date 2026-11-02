"""Writes the three NBB-CSV files of the fictitious demo company (run once; the CSV files are in git).

Demo Industries NV does not exist: the enterprise number 0999.999.999 fails the Belgian check digit,
so it can never belong to a real company. Every total reconciles (assets = liabilities, the
subtotals add up), so the tool reads the files exactly like a real NBB download.

    python examples/demo/maak_demo.py
"""
from pathlib import Path

MAP = Path(__file__).resolve().parent / "input"
NUMMER = "0999999999"
NAAM = "Demo Industries NV"

# Year: revenue, purchases, personnel, other opex, D&A, non-recurring cost (66A), director pay (9503), capex, FTE
JAREN = {
	2022: (30_000_000, 13_500_000, 9_000_000, 2_600_000, 650_000, 0, 360_000, 650_000, 118),
	2023: (33_000_000, 14_850_000, 9_600_000, 2_800_000, 680_000, 0, 370_000, 700_000, 124),
	2024: (36_000_000, 16_200_000, 10_200_000, 3_000_000, 720_000, 180_000, 380_000, 760_000, 130),
}


def codes(omzet, inkoop, personeel, overige, afschrijving, eenmalig, bestuurders, capex, vte):
	ebit = omzet - inkoop - personeel - overige - afschrijving - eenmalig
	vaste_activa = 6_000_000.0
	vorderingen = omzet * 0.16
	voorraad = inkoop * 0.09
	cash = 3_200_000.0
	handelsschulden = inkoop * 0.13
	sociaal = personeel * 0.11
	belasting = max(ebit, 0) * 0.25
	totaal_activa = vaste_activa + voorraad + vorderingen + cash
	schulden = handelsschulden + sociaal
	eigen_vermogen = totaal_activa - schulden
	return {
		"20/58": totaal_activa, "22/27": vaste_activa, "21/28": vaste_activa, "29/58": voorraad + vorderingen + cash,
		"3": voorraad, "40": vorderingen, "40/41": vorderingen, "54/58": cash,
		"10/49": totaal_activa, "10/15": eigen_vermogen, "14": eigen_vermogen - 250_000.0, "17/49": schulden,
		"42/48": schulden, "44": handelsschulden, "45": sociaal, "454/9": sociaal, "9077": sociaal,
		"450": 0.0, "9072": 0.0, "9073": 0.0, "9076": 0.0,
		"70": omzet, "70/76A": omzet, "60": inkoop, "61": 0.0, "62": personeel, "630": afschrijving, "640/8": overige,
		"60/66A": inkoop + personeel + afschrijving + overige + eenmalig, "9901": ebit,
		"66A": eenmalig, "76A": 0.0, "635/8": 0.0, "631/4": 0.0, "9903": ebit, "9904": ebit - belasting,
		"9087": vte, "8169": capex, "9503": bestuurders,
	}


def schrijf(jaar, waarden):
	velden = {
		"Entity number": NUMMER,
		"Entity name": NAAM,
		"Accounting period start date": f"{jaar}-01-01",
		"Accounting period end date": f"{jaar}-12-31",
		"Reference number": f"DEMO{jaar}",
		"Currency": "EUR",
		"Model code": "m02-f",
		**{code: repr(float(bedrag)) for code, bedrag in codes(*waarden).items()},
	}
	pad = MAP / f"Demo_Industries_JR{jaar}.csv"
	pad.write_text("\n".join(f'"{k}","{v}"' for k, v in velden.items()), encoding="utf-8-sig")
	return pad


if __name__ == "__main__":
	MAP.mkdir(parents=True, exist_ok=True)
	for jaar, waarden in JAREN.items():
		print(schrijf(jaar, waarden))
