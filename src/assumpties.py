"""The forecast assumptions of the model: one definition per driver, per scenario, per year.

Gemini proposes the values and the model uses them unchanged. The checks here only add
soft flags: they never correct a value. With too little history, or when Gemini is not
available, the mechanical drivers from the filing fill the same structure and are labelled
as a fallback, so the model and the Excel always read one format.

Percentages are in percentage points (5.0 = 5%), days in days, elasticity as a factor.
"""
import hashlib
import json
import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import config, labels

JAREN = config.LBO_HOLDING_PERIOD_YEARS
SCENARIOS = tuple(config.LBO_SCENARIOS)  # the analyst case: what Gemini proposes
SCREENING_SCENARIOS = tuple(config.LBO_SCREENING_SCENARIOS)  # rule-based, always calculated
MODEL_SCENARIOS = SCENARIOS + SCREENING_SCENARIOS


def scenario_label(scenario):
	return {**config.LBO_SCENARIOS, **config.LBO_SCREENING_SCENARIOS}[scenario]["label"]


def is_screening(scenario):
	return scenario in config.LBO_SCREENING_SCENARIOS


class Driver:
	"""richting: +1 higher is better, -1 higher is worse, 0 no favourable direction."""

	def __init__(self, sleutel, label, eenheid, richting, grenzen, beschrijving, historiek=None):
		self.sleutel = sleutel
		self.label = label
		self.eenheid = eenheid
		self.richting = richting
		self.grenzen = grenzen
		self.beschrijving = beschrijving
		self.historiek = historiek  # key in the driver pack, None if the filing does not show it


DRIVERS = [
	Driver(
		"prijsgroei", labels.DRIVER_PRICE, "pct", 1, (-5.0, 10.0),
		"Annual price growth in percentage points (2.0 means 2%).",
	),
	Driver(
		"volumegroei", labels.DRIVER_VOLUME, "pct", 1, (-25.0, 25.0),
		"Annual volume growth in percentage points. Revenue grows by (1 + volume) x (1 + price).",
	),
	Driver(
		"loonindexering", labels.DRIVER_INDEXATION, "pct", -1, (0.0, 10.0),
		"Annual wage indexation in percentage points. Belgian indexation follows the law, not customer prices.",
	),
	Driver(
		"vte_elasticiteit", labels.DRIVER_ELASTICITY, "factor", -1, (0.0, 1.5),
		"Share of volume growth that needs extra FTEs: 1.0 means FTEs follow volume, below 1 gives operating leverage.",
	),
	Driver(
		"inkoop_pct", labels.DRIVER_COGS, "pct", -1, (0.0, 100.0),
		"Cost of Goods & Services (codes 60/61) as percentage points of revenue. Must be 0 on a gross margin basis.",
		"Inkoop_Pct",
	),
	Driver(
		"overige_kosten_pct", labels.DRIVER_OPEX, "pct", -1, (-20.0, 60.0),
		"Other Operating Expenses, net of other operating income, as percentage points of revenue. Can be negative.",
		"Overige_Pct",
	),
	Driver(
		"da_pct", labels.DRIVER_DA, "pct", 0, (0.0, 100.0),
		"Annual D&A on the existing PP&E & Intangibles, in percentage points of their opening value at closing.",
		"DA_Pct",
	),
	Driver(
		"capex_pct", labels.DRIVER_CAPEX, "pct", -1, (0.0, 30.0),
		"Capex as percentage points of revenue.",
		"Capex_Pct",
	),
	Driver("dso", labels.DRIVER_DSO, "dagen", -1, (0.0, 180.0), "Days Sales Outstanding, in days of revenue.", "DSO"),
	Driver("dio", labels.DRIVER_DIO, "dagen", -1, (0.0, 365.0), "Days Inventory Outstanding, in days of goods cost.", "DIO"),
	Driver("dpo", labels.DRIVER_DPO, "dagen", 1, (0.0, 180.0), "Days Payable Outstanding, in days of purchases.", "DPO"),
	Driver(
		"dagen_vooruitbetaling", labels.DRIVER_ADVANCES, "dagen", 1, (0.0, 180.0),
		"Customer advances, in days of revenue.",
		"Advance_Days",
	),
]
DRIVER_PER_SLEUTEL = {driver.sleutel: driver for driver in DRIVERS}


def driver_uitleg():
	"""The driver definitions for the prompt."""
	return "\n".join(f"- {driver.sleutel}: {driver.beschrijving}" for driver in DRIVERS)


DriverSleutel = Literal[
	"prijsgroei",
	"volumegroei",
	"loonindexering",
	"vte_elasticiteit",
	"inkoop_pct",
	"overige_kosten_pct",
	"da_pct",
	"capex_pct",
	"dso",
	"dio",
	"dpo",
	"dagen_vooruitbetaling",
]


class AssumptieRegel(BaseModel):
	"""One driver in one scenario."""

	scenario: Literal["base", "downside", "upside"]
	driver: DriverSleutel
	waarden: list[float] = Field(min_length=JAREN, max_length=JAREN, description="Exactly five values: year 1 to 5.")
	rationale: str = Field(description="One or two sentences, in English.")
	source: str = Field(description='PDF page plus a short quote, or exactly "historical trend".')
	confidence: Literal["low", "medium", "high"]


class AssumptieAntwoord(BaseModel):
	"""The full response of Gemini: a flat list, because the API refuses a schema nested per scenario."""

	regels: list[AssumptieRegel]

	@model_validator(mode="after")
	def elke_combinatie_precies_een_keer(self):
		gevonden = sorted((regel.scenario, regel.driver) for regel in self.regels)
		verwacht = sorted((scenario, driver.sleutel) for scenario in SCENARIOS for driver in DRIVERS)
		if gevonden != verwacht:
			raise ValueError(f"Expected every scenario and driver exactly once, got {len(gevonden)} rows")
		return self


def pack_uit_antwoord(antwoord):
	"""Turns a validated response into the structure the model reads. The values stay untouched."""
	pack = {scenario: {} for scenario in SCENARIOS}
	for regel in antwoord.regels:
		pack[regel.scenario][regel.driver] = {
			"waarden": list(regel.waarden),
			"rationale": regel.rationale,
			"source": regel.source,
			"confidence": regel.confidence,
			"vlaggen": [],
		}
	return {scenario: {driver.sleutel: pack[scenario][driver.sleutel] for driver in DRIVERS} for scenario in SCENARIOS}


def _glide(start, doel, jaar):
	"""Linear glide path: the last fiscal year is the start, after LBO_KOSTEN_GLIDE_JAREN the target."""
	aandeel = min(jaar / config.LBO_KOSTEN_GLIDE_JAREN, 1.0)
	return start + (doel - start) * aandeel


def mechanische_assumpties(rij, bron):
	"""The rule-based drivers from the filing, in the same structure as the AI proposal."""
	groei = rij["Driver_Omzetgroei_Pct"] / 100
	omzet_0 = float(rij["Omzet_of_Brutomarge"])
	inkoop_start = float(rij["Inkoop"]) / omzet_0 * 100 if omzet_0 > 0 else float("nan")
	overige_start = (
		(omzet_0 - float(rij["Inkoop"]) - float(rij["Personeelskosten"]) - float(rij["Genormaliseerde_EBITDA"]))
		/ omzet_0 * 100
		if omzet_0 > 0
		else float("nan")
	)

	pack = {}
	for scenario, aannames in config.LBO_SCENARIOS.items():
		volume = (1 + groei) / (1 + config.LBO_SCENARIOS["base"]["prijsgroei"]) - 1 + aannames["volume_delta"]
		reeksen = {
			"prijsgroei": [aannames["prijsgroei"] * 100] * JAREN,
			"volumegroei": [volume * 100] * JAREN,
			"loonindexering": [aannames["indexering"] * 100] * JAREN,
			"vte_elasticiteit": [config.LBO_VTE_ELASTICITEIT] * JAREN,
			"inkoop_pct": [
				# On a gross margin basis there is no purchases line to shift
				_glide(inkoop_start, rij["Driver_Inkoop_Pct"] + (aannames["inkoop_delta"] * 100 if inkoop_start else 0.0), jaar)
				for jaar in range(1, JAREN + 1)
			],
			"overige_kosten_pct": [
				_glide(overige_start, rij["Driver_Overige_Kosten_Pct"], jaar) for jaar in range(1, JAREN + 1)
			],
			"da_pct": [rij["Driver_DA_Pct_Vaste_Activa"]] * JAREN,
			"capex_pct": [rij["Driver_Capex_Pct"]] * JAREN,
			"dso": [rij["Driver_DSO"]] * JAREN,
			"dio": [rij["Driver_DIO"]] * JAREN,
			"dpo": [rij["Driver_DPO"]] * JAREN,
			"dagen_vooruitbetaling": [rij["Driver_Dagen_Vooruitbetaling"]] * JAREN,
		}
		pack[scenario] = {
			sleutel: {
				"waarden": [float(waarde) for waarde in waarden],
				"rationale": bron,
				"source": bron,
				"confidence": "low",
				"vlaggen": [],
			}
			for sleutel, waarden in reeksen.items()
		}
	return pack


def screening_assumpties(rij):
	"""The screening case: the drivers from the filing, and the same drivers under the standard stress.

	The stress raises Other Operating Expenses in year t by haircut_t x |EBITDA margin_t| of the
	screening base. Revenue, purchases, personnel and working capital stay the same, so EBITDA is
	exactly (1 - haircut) x the screening base EBITDA (and never improves when it is negative).
	"""
	base = mechanische_assumpties(rij, labels.ASSUMPTIONS_SCREENING)["base"]
	_, marges = impliciete_groei_en_marge(base, float(rij["Omzet_of_Brutomarge"]), float(rij["Personeelskosten"]))
	stress = {sleutel: {**voorstel, "waarden": list(voorstel["waarden"]), "vlaggen": []} for sleutel, voorstel in base.items()}
	stress["overige_kosten_pct"]["waarden"] = [
		waarde + haircut * abs(marge)
		for waarde, haircut, marge in zip(base["overige_kosten_pct"]["waarden"], config.LBO_STRESS_EBITDA_HAIRCUT, marges)
	]
	tekst = labels.ASSUMPTIONS_STRESS.format(
		haircuts=" / ".join(f"{haircut * 100:.0f}%" for haircut in config.LBO_STRESS_EBITDA_HAIRCUT)
	)
	stress["overige_kosten_pct"]["rationale"] = tekst
	return {"screening_base": base, "screening_stress": stress}


def heeft_lege_waarden(pack):
	return any(
		math.isnan(waarde)
		for drivers in pack.values()
		for voorstel in drivers.values()
		for waarde in voorstel["waarden"]
	)


def impliciete_groei_en_marge(drivers, omzet_0, personeel_0):
	"""Revenue growth and EBITDA margin (in pp) per year that follow from the drivers of one scenario."""
	omzet, personeel = omzet_0, personeel_0
	groei, marges = [], []
	for jaar in range(JAREN):
		volume = drivers["volumegroei"]["waarden"][jaar] / 100
		prijs = drivers["prijsgroei"]["waarden"][jaar] / 100
		elasticiteit = drivers["vte_elasticiteit"]["waarden"][jaar]
		index = drivers["loonindexering"]["waarden"][jaar] / 100
		omzet = omzet * (1 + volume) * (1 + prijs)
		personeel = personeel * (1 + volume * elasticiteit) * (1 + index)
		groei.append(((1 + volume) * (1 + prijs) - 1) * 100)
		marges.append(
			100 - drivers["inkoop_pct"]["waarden"][jaar] - drivers["overige_kosten_pct"]["waarden"][jaar]
			- (personeel / omzet * 100 if omzet > 0 else 0.0)
		)
	return groei, marges


def _jaren_tekst(jaren):
	return ", ".join(f"Y{jaar}" for jaar in jaren)


def _absolute_vlag(driver, waarden):
	onder, boven = driver.grenzen
	jaren = [jaar for jaar, waarde in enumerate(waarden, start=1) if not onder <= waarde <= boven]
	if jaren:
		return labels.ASSUMPTION_FLAG_BOUNDS.format(years=_jaren_tekst(jaren), low=onder, high=boven)
	return None


def _historische_vlag(driver, waarden, pack_jaren):
	"""More than the tolerance outside the historical minimum and maximum."""
	reeks = [jaar.get(driver.historiek) for jaar in pack_jaren] if driver.historiek else []
	reeks = [waarde for waarde in reeks if waarde is not None and not math.isnan(waarde)]
	if not reeks:
		return None
	marge = config.LBO_VLAG_MARGE_DAGEN if driver.eenheid == "dagen" else config.LBO_VLAG_MARGE_PP
	onder, boven = min(reeks), max(reeks)
	jaren = [jaar for jaar, waarde in enumerate(waarden, start=1) if waarde < onder - marge or waarde > boven + marge]
	if jaren:
		return labels.ASSUMPTION_FLAG_HISTORY.format(years=_jaren_tekst(jaren), low=onder, high=boven, margin=marge)
	return None


def _volgorde_vlaggen(pack):
	"""Downside must not beat Base and Base must not beat Upside, in the favourable direction per driver."""
	vlaggen = []
	for driver in DRIVERS:
		if not driver.richting:
			continue
		waarden = {scenario: pack[scenario][driver.sleutel]["waarden"] for scenario in SCENARIOS}
		for slechter, beter in (("downside", "base"), ("base", "upside")):
			jaren = [
				jaar
				for jaar, (laag, hoog) in enumerate(zip(waarden[slechter], waarden[beter]), start=1)
				if driver.richting * (laag - hoog) > 1e-9
			]
			if jaren:
				tekst = labels.ASSUMPTION_FLAG_ORDER.format(
					worse=config.LBO_SCENARIOS[slechter]["label"],
					better=config.LBO_SCENARIOS[beter]["label"],
					years=_jaren_tekst(jaren),
				)
				vlaggen.append((slechter, driver.sleutel, tekst))
	return vlaggen


def controleer(pack, pack_jaren, omzet_0, personeel_0):
	"""Adds soft flags to the pack. No value is ever changed. Returns the flags as readable lines."""
	for scenario in SCENARIOS:
		for driver in DRIVERS:
			voorstel = pack[scenario][driver.sleutel]
			for vlag in (
				_absolute_vlag(driver, voorstel["waarden"]),
				_historische_vlag(driver, voorstel["waarden"], pack_jaren),
			):
				if vlag:
					voorstel["vlaggen"].append(vlag)

	for scenario, sleutel, tekst in _volgorde_vlaggen(pack):
		pack[scenario][sleutel]["vlaggen"].append(tekst)

	# Derived checks: the flag sits next to the driver that moves the result most
	for scenario in SCENARIOS:
		groei, marges = impliciete_groei_en_marge(pack[scenario], omzet_0, personeel_0)
		for reeks, grenzen, naam, sleutel in (
			(groei, config.LBO_VLAG_OMZETGROEI, labels.DRIVER_REVENUE_GROWTH, "volumegroei"),
			(marges, config.LBO_VLAG_EBITDA_MARGE, labels.DRIVER_EBITDA_MARGIN, "inkoop_pct"),
		):
			onder, boven = grenzen
			jaren = [jaar for jaar, waarde in enumerate(reeks, start=1) if not onder <= waarde <= boven]
			if jaren:
				tekst = labels.ASSUMPTION_FLAG_BOUNDS.format(years=_jaren_tekst(jaren), low=onder, high=boven)
				pack[scenario][sleutel]["vlaggen"].append(f"{naam}: {tekst}")

	regels = []
	for scenario in SCENARIOS:
		label = config.LBO_SCENARIOS[scenario]["label"]
		for driver in DRIVERS:
			for vlag in pack[scenario][driver.sleutel]["vlaggen"]:
				regels.append(f"{label} / {driver.label}: {vlag}")
	return regels


# ============================================================================
# Snapshots: one fixed AI assumption set per company and fiscal year
# ============================================================================
SNAPSHOT_VOORSTEL = "voorstel"        # written by the tool, not yet reviewed
SNAPSHOT_GOEDGEKEURD = "goedgekeurd"  # set by hand by the analyst after review


def snapshot_pad(ondernemingsnummer, boekjaar):
	"""assumpties/<enterprise number>_FY<year>.json; the number without dots."""
	nummer = re.sub(r"\D", "", str(ondernemingsnummer))
	return config.SNAPSHOT_FOLDER / f"{nummer}_FY{boekjaar}.json"


def bestand_hash(pad):
	return hashlib.sha256(pad.read_bytes()).hexdigest() if pad is not None else None


def schrijf_snapshot(pad, data, pdf, bedrijf):
	"""Stores a validated Gemini response with the metadata needed to explain it later."""
	pad.parent.mkdir(parents=True, exist_ok=True)
	inhoud = {
		"metadata": {
			"bedrijf": bedrijf,
			"status": SNAPSHOT_VOORSTEL,
			"datum": datetime.now().isoformat(timespec="seconds"),
			"gemini_model": data.get("Gebruikt_Model"),
			"prompt_versie": config.PROMPT_VERSIE,
			"schema_versie": config.SCHEMA_VERSIE,
			"pdf_bestand": pdf.name if pdf is not None else None,
			"pdf_sha256": bestand_hash(pdf),
		},
		"assumpties": {"regels": data["regels"]},
	}
	pad.write_text(json.dumps(inhoud, ensure_ascii=False, indent=2), encoding="utf-8")


def lees_snapshot(pad):
	"""Returns (validated response, metadata). A broken file raises ValueError: it is never overwritten silently."""
	try:
		inhoud = json.loads(pad.read_text(encoding="utf-8"))
		antwoord = AssumptieAntwoord.model_validate(inhoud["assumpties"])
		metadata = dict(inhoud.get("metadata") or {})
	except (OSError, ValueError, KeyError, TypeError) as fout:
		raise ValueError(f"{pad.name}: {fout}") from None
	return antwoord, metadata


def archiveer_snapshot(pad):
	"""Renames the current snapshot to ..._<date>.json, so no reviewed set is ever lost."""
	doel = pad.with_name(f"{pad.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{pad.suffix}")
	pad.rename(doel)
	return doel


def snapshot_info(pad, metadata):
	"""What the Excel and the run manifest show about the snapshot."""
	return {
		"naam": pad.name,
		"datum": str(metadata.get("datum", "")),
		"status": str(metadata.get("status", SNAPSHOT_VOORSTEL)),
	}
