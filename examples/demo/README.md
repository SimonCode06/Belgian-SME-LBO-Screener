# Demo: Demo Industries NV (fictitious)

Everything in this folder is made up. It lets anyone run the full tool without an API key and
without real filings:

```
python main.py --demo
```

The output (overview workbook, company workbook, run manifest) lands in `output/demo/`. The run
works on a copy, so these files never change.

| File | What it is |
|---|---|
| `input/Demo_Industries_JR2022-2024.csv` | Three NBB-format filings (full schema). Every total reconciles. Written by `maak_demo.py`. |
| `assumpties/0999999999_FY2024.json` | A fixed assumption snapshot (Base, Downside, Upside), in the format Gemini returns. |
| `assumpties/0999999999_FY2024_adjustments.json` | The EBITDA ledger: director pay (verified on NBB code 9503, approved, market level EUR 250k) and a related-party rent (not verified, not approved). |
| `ai/tekst.json`, `ai/oordeel.json` | Illustrative answers to the two text passes (normalisations, red flags, ownership; commentary, thesis, DD questions). No PDF exists, so the quotes show as "not checkable". |

The enterprise number 0999.999.999 fails the Belgian check digit (97 − first eight digits mod 97),
so it can never belong to a real company.
