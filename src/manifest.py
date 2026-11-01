"""Run manifest: one JSON per run in output/runs/, so every assessment can be reconstructed later.

It answers "why did the tool say NO-GO last week?": which code (git commit), which package
versions, which config, which input files (by hash), which assumption snapshot and which
Gemini model produced which status and IRR.
"""
import hashlib
import json
import math
import platform
import subprocess
from datetime import datetime
from importlib import metadata

from . import config

PAKKETTEN = ("pandas", "numpy", "openpyxl", "pydantic", "google-genai")


def manifest_naam(tijdstip=None):
	return f"run_{(tijdstip or datetime.now()).strftime('%Y%m%d_%H%M%S')}.json"


def _hash(pad):
	try:
		return hashlib.sha256(pad.read_bytes()).hexdigest()
	except OSError:
		return None


def _git(*argumenten):
	try:
		uitvoer = subprocess.run(
			["git", *argumenten], cwd=config.BASIS_MAP, capture_output=True, text=True, timeout=10, check=True
		)
		return uitvoer.stdout.strip()
	except (OSError, subprocess.SubprocessError):
		return None


def git_info():
	"""The commit and whether tracked files were changed after it. Without git: unknown."""
	commit = _git("rev-parse", "HEAD")
	if commit is None:
		return {"commit": "unknown", "niet_gecommitte_wijzigingen": None}
	gewijzigd = _git("status", "--porcelain", "--untracked-files=no")
	return {"commit": commit, "niet_gecommitte_wijzigingen": bool(gewijzigd)}


def pakket_versies():
	versies = {"python": platform.python_version()}
	for pakket in PAKKETTEN:
		try:
			versies[pakket] = metadata.version(pakket)
		except metadata.PackageNotFoundError:
			versies[pakket] = None
	return versies


def _getal(waarde):
	try:
		waarde = float(waarde)
	except (TypeError, ValueError):
		return None
	return None if math.isnan(waarde) else waarde


def bedrijf_regel(rij, invoer):
	"""invoer: {"csv": [paths], "pdf": path or None, "gemini_model": str or None}."""
	pdf = invoer.get("pdf")
	return {
		"bedrijf": rij["Bedrijfsnaam"],
		"ondernemingsnummer": rij["Ondernemingsnummer"],
		"boekjaar": rij["Boekjaar"],
		"csv": {pad.name: _hash(pad) for pad in invoer.get("csv", [])},
		"pdf": {pdf.name: _hash(pdf)} if pdf is not None else None,
		"assumptie_bron": rij["LBO_Assumptie_Bron"],
		"snapshot": rij.get("LBO_Snapshot_Naam", "-"),
		"snapshot_status": rij.get("LBO_Snapshot_Status", "-"),
		"gemini_model": invoer.get("gemini_model"),
		"status": rij["LBO_Status"],
		"ai_irr_pct": _getal(rij["Indicatieve_IRR_Pct"]),
		"screening_irr_pct": _getal(rij["LBO_Screening_IRR_Pct"]),
		"stress_irr_pct": _getal(rij["LBO_Stress_IRR_Pct"]),
		"stress_convenanten": rij["LBO_Stress_Convenanten"],
	}


def bouw_manifest(naam, df, invoer_per_bedrijf, argumenten, uitvoer, mislukt):
	return {
		"manifest": naam,
		"tijdstip": datetime.now().isoformat(timespec="seconds"),
		"model_versie": config.MODEL_VERSIE,
		"prompt_versie": config.PROMPT_VERSIE,
		"schema_versie": config.SCHEMA_VERSIE,
		"git": git_info(),
		"versies": pakket_versies(),
		"config_sha256": _hash(config.BASIS_MAP / "src" / "config.py"),
		"argumenten": argumenten,
		"bedrijven": [
			bedrijf_regel(rij, invoer_per_bedrijf.get(rij["Ondernemingsnummer"], {})) for _, rij in df.iterrows()
		],
		"uitvoer": [pad.name for pad in uitvoer],
		"mislukt": list(mislukt),
	}


def schrijf_manifest(manifest):
	config.RUNS_FOLDER.mkdir(parents=True, exist_ok=True)
	pad = config.RUNS_FOLDER / manifest["manifest"]
	pad.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	return pad
