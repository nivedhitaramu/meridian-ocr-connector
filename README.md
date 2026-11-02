# Meridian Freight — Shipping Document Reader (Team Delta)

Reads a **commercial invoice**, a **packing list** or a **delivery receipt**, fills six fields, and answers
the receiving clerk's one question: **does the invoice quantity match the packing list?**

Fictional company, synthetic documents only. Personal data is masked locally **before** any model call and
never appears in logs or traces.

```
 upload ──► OCR (Tesseract, local) ──► Presidio mask (local) ──► LLM (one call, masked text) ──► rule ──► JSON + status
   │             │  too little text / low confidence                                                │
   │             └──► redact word boxes + contact lines + receipt signature band ──► vision model    │
   │                  (no boxes found → "manual review" error, raw scan never sent)                   │
   └── random file id, bytes checked, deleted in `finally`             spans: ocr · pii · llm · rule ┘
```

## Quick start

```bash
# 1. System packages
#    macOS:   brew install tesseract poppler
#    Ubuntu:  sudo apt install tesseract-ocr poppler-utils
#    Windows: install Tesseract (UB Mannheim build) + poppler, add both to PATH

# 2. Python 3.11+
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg

# 3. Config — the API key comes from the environment, never from code
cp .env.example .env          # then put your key in LLM_API_KEY

# 4. Synthetic samples (40 documents, test sheet, .eml packets)
python scripts/make_samples.py && python scripts/make_eml.py

# 5. Run
uvicorn app.main:app --reload --port 8000              # API  → http://localhost:8000/docs
streamlit run ui/streamlit_app.py                      # page → http://localhost:8501

# 6. Test + score
pytest -q
python scripts/evaluate.py                             # needs the API running
```

No key yet? `LLM_PROVIDER=mock` runs a regex extractor tuned to the sample templates so you can build the UI
and telemetry. It is a dev stand-in; report accuracy from the real model only.

## API

`POST /v1/extract` — multipart, `file` (required) and `file2` (optional, for the pair check).
`POST /v1/extract-eml` — multipart `file` = an `.eml`; every PDF/PNG/JPEG attachment is processed (stretch goal).
`GET /v1/trace/last` — sanitized trace of the last request (demo panel). `GET /v1/metrics` — counters.

```json
{
  "request_id": "…",
  "document_type": "commercial_invoice",
  "fields": {"invoice_number": "MF-88421", "shipper_name": "Kestrel Exports",
             "receiver_name": "Meridian Freight Warehouse", "shipment_date": "2026-02-02",
             "total_quantity": 120, "total_weight_kg": 860.5},
  "check": {"status": "Match", "reason": "Invoice quantity equals packing-list quantity (120 cartons)."},
  "pii": {"masked_before_llm": true, "entity_counts": {"PERSON": 3, "IN_MOBILE": 1, "EMAIL_ADDRESS": 1}, "placeholder_count": 5},
  "pipeline": {"ocr_engine": "tesseract", "used_vision_fallback": false, "model": "…", "prompt_version": "meridian-v1",
               "timings_ms": {"ocr": 640, "pii": 38, "llm": 1102, "rule": 0}},
  "documents": [ {"slot": 1, "document_type": "commercial_invoice", "fields": {…}, "quantity_unit": "carton", …},
                 {"slot": 2, "document_type": "packing_list", …} ]
}
```

Top-level `document_type`/`fields` follow the brief's contract (first file). `documents[]` holds one entry
per file. Errors return `{"error": "Could not read this document."}`; the server log records only a class
(`ocr_empty`, `schema_invalid`, `manual_review_required`, `upload_bad_type`, …).

## Decisions the brief asks us to document

**Quantity unit.** `total_quantity` is the number printed on the total line, in the unit printed next to it
(returned as `quantity_unit`: carton, piece, package, pallet, box …).

**When a page prints two totals** (e.g. *Total Cartons: 50* and *Total Pieces: 1,200*): the field holds the
**shipping-unit total (cartons/packages)**, because put-away is by carton. The check still compares like with
like: if the other document's unit is among this page's totals, those two numbers are compared. So an invoice
for 1,200 pieces against that packing list is a **Match**. We never multiply by a guessed pack size: 120 cartons
vs 1,440 pieces with no shared unit is **Mismatch — units differ**.

**Numbers.** `1,200` → 1200 (separators stripped). `120` and `120.0` match. Pounds are converted to kg in code
(×0.45359237), not by the model. Weight is shown but never changes the status.

**Statuses.** Match / Mismatch (different numbers, different units, or a total that could not be read) /
Incomplete (invoice or packing list missing) / Not applicable (only delivery receipts).

**Personal data in fields.** Shipper and receiver are company names. If the model can only find a person, the
placeholder (e.g. `<PERSON_1>`) stays in the field rather than the real name — the schema does not grow.

## Personal data & security checklist

| Rule from the brief | Where |
|---|---|
| Presidio before any network call, plus Indian recognizers (mobile, Aadhaar-shaped, PAN, bank account, IFSC, policy, roll) | `app/pii.py` |
| Labelled names (`Attn:`, `Contact:`, `Received by:`, `Driver:`) and signature lines | `LabeledFieldRecognizer` |
| Company names kept in the prompt (spaCy often tags them PERSON) | `_COMPANY_WORDS` filter |
| Stable tokens per request, case/space-normalized; same person on two docs = one token | `PlaceholderVault` |
| Vault in memory only, cleared in `finally` | `pipeline.run` |
| Receipt bottom band masked in the **text** path too (OCR misreads the scribble) | `vision.signature_band_spans` |
| Vision fallback sends only redacted pages; no boxes → manual review | `vision.redact_pages`, `llm.extract_from_images` |
| Upload: magic bytes, 10 MB cap, random name, deleted after the request | `app/upload.py` |
| Telemetry uses an **allow-list** of keys, so text, prompts, values, vault and filenames cannot be logged | `app/telemetry.py` |
| Generic client error; CORS limited to the Streamlit origin | `app/main.py` |
| Key from env; `.env` git-ignored; `.env.example` committed empty | `.env.example` |

Before the demo, confirm your model provider's current API terms say prompts are not used for training.

![Vision fallback redaction](docs/redaction_example.png)

## Telemetry

OpenTelemetry spans `ocr`, `pii`, `llm`, `rule` (console exporter; set `OTEL_EXPORTER_OTLP_ENDPOINT` for Jaeger),
mirrored as one JSON object per line in `logs/telemetry.jsonl`:

```json
{"ts":"2026-11-02T13:20:53+00:00","level":"info","request_id":"e32e3588-…","stage":"pii","duration_ms":38,
 "slot":1,"entity_counts":{"PERSON":2,"IN_MOBILE":1,"EMAIL_ADDRESS":1},"placeholder_count":4}
```

Counters: requests by outcome, stage latency p50/p95, fallback rate, entities by type, checks by status.

Verify nothing leaked: `grep -E -i "@|[0-9]{10}|priya|raman" logs/telemetry.jsonl` should print nothing.

## Test sheet & accuracy

`samples/test_sheet.csv` — 20 documents with correct values (8 invoice/packing pairs, 3 receipts, 1 lone invoice).
`samples/test_cases.csv` — 12 rule cases. `scripts/evaluate.py` writes `results_documents.csv` (extracted vs
correct, per field) and `results_cases.csv`, and prints the three numbers the rubric asks for.

Field-match normalization: strings case-insensitive with collapsed spaces; dates as ISO; quantities as numbers;
weight within ±0.5 kg.

| Metric | Real model | (mock, sanity only) |
|---|---|---|
| Field match | _fill in_ | 100% |
| Document type | _fill in_ | 100% |
| Rule | _fill in_ | 100% |

Edge cases in the samples: matches at 40 / 120 / 1,200; 120 vs 118; cartons vs pieces; a packing list with two
totals; weight in lb; equal quantity with different weights; PNG and JPEG "scans"; signed receipts; one faint scan
that must go to manual review.

## Project layout

```
app/  main.py (FastAPI) · pipeline.py · upload.py · ocr.py · pii.py · llm.py · vision.py · rules.py
      schemas.py · telemetry.py · eml.py · mock_llm.py · config.py · errors.py
ui/streamlit_app.py      clerk page + trace panel
scripts/                 make_samples.py · make_eml.py · evaluate.py
samples/                 synthetic PDFs/PNGs/JPEGs, ground_truth.json, test sheet, .eml packets
tests/                   rules, vault, upload, presidio
```

## Demo script

1. Upload `S02_invoice.pdf` + `S02_packing.pdf` → **Match** (120 vs 120).
2. Upload `S04_invoice.pdf` + `S04_packing.pdf` → **Mismatch** (120 vs 118).
3. Upload `S02_receipt.pdf` alone → **Not applicable**; open the trace — `SIGNATURE` in entity counts, no text.
4. Show the trace panel: four stage timings, Match, entity counts; no phone, no email.
5. Stretch: upload `packet_S02_match.eml` → three documents, one Match.
