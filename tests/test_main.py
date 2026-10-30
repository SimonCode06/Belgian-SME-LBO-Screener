"""The assumption step of main.py, with a simulated Gemini: no API call."""
import json

import pytest

import main as app
from src import config, labels
from tests.test_assumpties import nagebootste_gemini_respons


class NepClient:
	def __init__(self):
		self.aanroepen = 0
		self.models = self
		self.files = self

	def generate_content(self, model, contents, config):
		self.aanroepen += 1

		class Antwoord:
			text = json.dumps(nagebootste_gemini_respons())

		return Antwoord


@pytest.fixture
def pdf(tmp_path, monkeypatch):
	monkeypatch.setattr(config, "CACHE_FOLDER", tmp_path)
	pad = tmp_path / "Testco.pdf"
	pad.write_bytes(b"%PDF-1.4 test")
	return pad


def test_too_little_history_uses_no_ai(pdf, filings, cijfers):
	client = NepClient()
	cijfers = {**cijfers, "Driver_Aantal_Jaren": config.LBO_MIN_JAREN - 1}
	pack, bron, _, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert pack is None
	assert bron == labels.ASSUMPTIONS_FALLBACK_HISTORY
	assert client.aanroepen == 0


def test_ai_proposal_is_cached(pdf, filings, cijfers):
	client = NepClient()
	pack, bron, _, model = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert bron == labels.ASSUMPTIONS_AI and model == config.MODELLEN[0]
	assert pack["base"]["dso"]["waarden"] == [54.0] * 5

	opnieuw, bron, _, _ = app.haal_assumpties(client, pdf, filings, cijfers, [])
	assert client.aanroepen == 1
	assert opnieuw["base"]["dso"]["waarden"] == [54.0] * 5


def test_prompt_and_schema_are_in_the_cache_key(pdf, filings, cijfers, monkeypatch):
	from src.nbb_csv import bouw_driver_pack

	driver_pack = bouw_driver_pack(filings)
	voor = app.assumptie_cache_pad_voor(pdf, driver_pack)
	monkeypatch.setattr(config, "ASSUMPTIE_PROMPT", "another prompt")
	assert app.assumptie_cache_pad_voor(pdf, driver_pack) != voor


def test_gemini_failure_is_reported_and_labelled(pdf, filings, cijfers, monkeypatch):
	def faalt(*_):
		raise RuntimeError("no model available")

	monkeypatch.setattr(app, "genereer_assumpties", faalt)
	mislukt = []
	pack, bron, _, _ = app.haal_assumpties(NepClient(), pdf, filings, cijfers, mislukt)
	assert pack is None and bron == labels.ASSUMPTIONS_FALLBACK_NO_AI
	assert mislukt
