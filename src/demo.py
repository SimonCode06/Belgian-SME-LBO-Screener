"""The demo: one fictitious company, run end to end without an API key (python main.py --demo).

examples/demo holds three NBB-CSV files of Demo Industries NV (enterprise number 0999.999.999,
which fails the Belgian check digit, so it can never be a real company), a fixed assumption
snapshot, an EBITDA ledger with one approved item, and illustrative answers for the two text
passes (tekst.json, oordeel.json) in place of Gemini.

The demo works in a copy (output/demo/), so a run never changes the files in examples/.
"""
import json
import shutil

from . import config

DEMO_MAP = config.BASIS_MAP / "examples" / "demo"


def bereid_voor():
	"""Copies the demo input to output/demo/ and points every folder of the run there. Returns that folder."""
	werkmap = config.OUTPUT_FOLDER / "demo"
	for naam in ("input", "assumpties"):
		shutil.copytree(DEMO_MAP / naam, werkmap / naam, dirs_exist_ok=True)
	config.INPUT_FOLDER = werkmap / "input"
	config.SNAPSHOT_FOLDER = werkmap / "assumpties"
	config.CACHE_FOLDER = werkmap / "cache"
	config.OUTPUT_FOLDER = werkmap
	config.RUNS_FOLDER = werkmap / "runs"
	return werkmap


def tekst():
	"""The illustrative answer of the text pass (same schema as Gemini's)."""
	return json.loads((DEMO_MAP / "ai" / "tekst.json").read_text(encoding="utf-8"))


def oordeel():
	"""The illustrative answer of the commentary pass: commentary, thesis and DD questions."""
	return json.loads((DEMO_MAP / "ai" / "oordeel.json").read_text(encoding="utf-8"))
