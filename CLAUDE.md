# Meridian OCR Connector

Team Delta's project for the Build Fast with AI (BFWAI) OCR Connector fellowship. Meridian Freight is fictional, and all documents must be synthetic. This repo is public, so never commit secrets or real documents.

## Start and end of every session

- **Start:** read "Current status", then compare it with `git log` and the code. If they disagree, trust the code and tell the user.
- **End:** when work changes the project's state, update "Current status" and "Decisions". Keep entries short and dated. Don't mark anything done unless it was run and verified.

## What we're building

A receiving clerk uploads shipping documents and gets an answer to one question: **does the invoice quantity match the packing list?**

- **Now:** meet every fellowship requirement. The assignment PDF and the `fde-week-2.vercel.app/meridian` page are the authority on what's graded.
- **After submission:** grow it into a B2B document intelligence SaaS, with Meridian as the first domain pack. Planned: Postgres, auth, tenancy, background workers, a Next.js UI, human review and AWS.
- **Build order:** finish the fellowship work first. Don't start SaaS work before submission, unless the user changes this.
- **Architecture authority:** `docs/ARCHITECTURE.md`, drawn from the user's six diagrams, is the source of truth for design. The assignment still decides what's graded. Label anything not built as Target.

Scoring: working demo 30%, extraction accuracy 25%, masking 15%, code and README 15%, presentation 15%, `.eml` stretch +10%. A trace containing a name fails the masking criterion even if Presidio ran.

## Rules that must not break

**Fields:** `fields` has exactly six keys: `invoice_number`, `shipper_name`, `receiver_name`, `shipment_date`, `total_quantity`, `total_weight_kg`. Use null when absent. Helper values such as units stay outside `fields`.

**Statuses:** exactly four, always decided by `app/domains/meridian/rules.py` and never by the model.

| Status | When |
|---|---|
| Match | Both documents present and quantities equal |
| Mismatch | Quantities differ, units differ, or a total can't be read |
| Incomplete | Invoice or packing list missing |
| Not applicable | Only delivery receipts |

- 120 equals 120.0. `1,200` means 1200.
- 120 cartons vs 1,440 pieces is a Mismatch. Never guess a pack size.
- Weight never changes the status. Code converts pounds to kilograms, not the model.

**Privacy**
- Presidio masks text locally before any network call. Company names may stay; people, phones, emails, IDs and signatures may not.
- The placeholder map stays in memory for one request and is cleared in `finally`.
- Never send a raw scan to a hosted model. If it can't be safely redacted, return manual review.
- Uploads use random names and are deleted when the request ends. Original filenames are never stored or logged.
- `check.reason` is a code template with no names or IDs.
- Clients get only "Could not read this document." Logs get only an error class.

**Telemetry:** spans are `ocr`, `pii`, `llm`, `rule`. Only keys in `SAFE_KEYS` (`app/core/telemetry.py`) may be recorded. Never add OCR text, prompts, completions, field values, the placeholder map or filenames.

**API:** `POST /v1/extract` stays synchronous and returns the full object: `request_id`, `document_type`, `fields`, `check`, `pii`, `pipeline`. `documents[]` is an addition for pairs. Any future job API must be separate and share the same pipeline.

**Mock mode:** `LLM_PROVIDER=mock` is a regex stand-in tuned to the samples. Never demo it or report its accuracy as the real result.

**Working style:** explain major architecture changes before making them. Don't push or commit unless asked. Don't add features just to make the project look bigger. Keep the README accurate: no result or link goes in until it's real.

## Code map

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI routes |
| `app/core/` | `config.py`, `errors.py`, `telemetry.py` (spans, safe logs, metrics) |
| `app/ingestion/upload.py` | File byte checks, size cap, random storage |
| `app/ingestion/eml.py` | `.eml` attachments (stretch goal) |
| `app/pipeline/runner.py` | Runs the steps; used by the API, `.eml` route and evaluation |
| `app/pipeline/ocr.py` | Tesseract text, word boxes, fallback decision |
| `app/pipeline/pii.py` | Presidio, custom recognizers, placeholder map |
| `app/pipeline/llm.py`, `mock_llm.py` | Model calls and offline stand-in |
| `app/pipeline/vision.py` | Image redaction and receipt signature band |
| `app/domains/meridian/rules.py` | Normalization and the status decision |
| `app/domains/meridian/schemas.py` | Pydantic models and API contract |
| `app/domains/meridian/prompt.py` | Extraction prompt |
| `ui/streamlit_app.py` | Clerk page and trace panel |
| `docs/ARCHITECTURE.md` | Six architecture diagrams, labelled Built or Target |
| `scripts/` | Sample generation, `.eml` packets, evaluation |
| `samples/` | 40 synthetic documents, test sheets, `.eml` packets |
| `tests/` | Rules, placeholder map, upload, Presidio |

## Commands

Needs Python 3.11, Tesseract and Poppler on PATH. Docker is optional, and the `Dockerfile` installs both.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg
copy .env.example .env
uvicorn app.main:app --reload --port 8000
streamlit run ui/streamlit_app.py
pytest -q
python scripts/evaluate.py
```

Put the key in `LLM_API_KEY` in `.env`. Without a key, use `LLM_PROVIDER=mock` for development only. `evaluate.py` needs the API running, or use `--in-process`.

## Decisions

- **2026-11-02: Fellowship work comes before SaaS work.**
- **2026-11-02: The user's architecture replaces the first commit's README and docs as the reference.** Existing code is reused where it fits, moved into `core`, `ingestion`, `pipeline` and `domains/meridian`. Work is on branch `architecture-alignment`.
- **Frontend:** Streamlit now, as the assignment specifies. Next.js comes after submission.
- **OCR and PDF rendering:** Tesseract and pdf2image with Poppler, as built.
- **Two totals on a page:** `total_quantity` holds the shipping-unit total (cartons or packages), because put-away is by carton. The check compares like with like, so 1,200 pieces on an invoice matches a packing list printing 50 cartons and 1,200 pieces.
- **Person-only shipper or receiver:** the placeholder stays in the field, and the schema doesn't grow.
- **Hosted vision:** off unless `VISION_MODEL` is set; otherwise unreadable scans return manual review.

## Current status

**Last updated:** 2026-11-02, on local branch `architecture-alignment`.

**Verified by running:** `tests/test_rules.py`, `tests/test_pii_vault.py` and `tests/test_upload.py` pass (20 tests) after the restructure.

**Not verified:** the API, OCR, Presidio masking, the LLM call and the Streamlit page. Nothing has been run end to end since the move.

**Present in the code:** upload checks, OCR, masking, extraction, rules, `/v1/extract`, `/v1/extract-eml`, telemetry, trace panel, Streamlit page, 40 samples, 20-document test sheet, 12 rule cases and an evaluation script.

**Done on this branch:** code moved into architecture layers, `docs/ARCHITECTURE.md` added with six diagrams, README rewritten.

**Not done**
- [ ] Run the Presidio test and all four demo steps on a real install
- [ ] Measure accuracy with the real model (README says "Not measured yet")
- [ ] Confirm the LLM provider, its model ID and that its terms exclude training on prompts
- [ ] Deploy the live demo; the `Dockerfile` starts only the API, not Streamlit
- [ ] Confirm the Mermaid diagrams render on GitHub
- [ ] Pin dependency versions; add CI
- [ ] Build the Target layers: PostgreSQL, Redis, workers, auth, tenancy, Next.js, AWS

**Known issues, found by reading the code (fix privacy items first)**
1. **Name leak:** `_COMPANY_WORDS` in `app/pipeline/pii.py` keeps any name containing words like Mills, Co or Global, so "Attn: John Mills" isn't masked. It's also tuned to the sample companies.
2. **Signature band can be skipped:** `looks_like_receipt` depends on OCR text, and fallback runs when OCR is poor. A hosted vision call could then include the signature.
3. **No output check:** a name Presidio misses can pass through the model into `fields`.
4. **Weak contact-line grouping:** `vision.py` groups lines with `top // height`, which can miss part of a line.
5. **`masked_before_llm` is hardcoded** to `True` rather than set by what actually happened.
6. **Silent page limits:** PDFs stop at 5 pages and vision at 3, so a total on a later page is lost without warning.
7. **Wrong `request_id` on errors:** it's read from the global `LAST_TRACE`, so it can belong to another request.
8. **Public endpoints:** `/v1/trace/last` and `/v1/metrics` have no auth, and there's no rate limiting. Fix before deploying.
9. **Test sheet isn't a separate holdout:** its 20 documents are drawn from the 40 samples. Consider adding unseen documents.

**Next step:** install and run everything, get real accuracy numbers, then fix the privacy issues.

**Open questions for the team:** submission deadline, final LLM provider, live demo hosting, who owns what, and whether the Target layers should start before submission.
