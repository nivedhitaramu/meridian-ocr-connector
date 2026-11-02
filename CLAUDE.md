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
| `web/` | Next.js product UI; see `web/README.md` |
| `docs/ARCHITECTURE.md` | Six architecture diagrams, labelled Built or Target |
| `scripts/` | Sample generation, `.eml` packets, evaluation |
| `samples/` | 40 synthetic documents, test sheets, `.eml` packets |
| `tests/` | Rules, placeholder map, upload, Presidio |

## Commands

Needs Python 3.13, Tesseract and Poppler on PATH. Docker is optional, and the `Dockerfile` installs both.

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
- **2026-11-02: The user's architecture replaces the first commit's README and docs as the reference.** Existing code is reused where it fits, moved into `core`, `ingestion`, `pipeline` and `domains/meridian`. This is merged into `main`.
- **Frontend:** Streamlit now, as the assignment specifies. Next.js comes after submission.
- **OCR and PDF rendering:** Tesseract and pdf2image with Poppler, as built.
- **Two totals on a page:** `total_quantity` holds the shipping-unit total (cartons or packages), because put-away is by carton. The check compares like with like, so 1,200 pieces on an invoice matches a packing list printing 50 cartons and 1,200 pieces.
- **Person-only shipper or receiver:** the placeholder stays in the field, and the schema doesn't grow.
- **2026-11-02: Sign-in uses Clerk.** The API verifies tokens and stores no passwords. Product routes depend on `current_user`; `POST /v1/extract` stays open.
- **2026-11-02: Tenant isolation.** The organization comes from memberships, never a request body. Other tenants' records return 404. Each signed-in request runs as the restricted `meridian_app` role, because superusers skip row-level security. New tenant tables must add a policy in their migration.
- **Hosted vision:** off unless `VISION_MODEL` is set; otherwise unreadable scans return manual review.

## Current status

**Last updated:** 2026-11-02.

**On `main`:** architecture layout, privacy fixes (#4), hardening (#7, #8, #10), CI, Docker stack (#13, worker pending), database schema (#14) and Clerk token verification (#15, sign-in screens pending). Issues #2-#45 hold the full plan.

**In review:** #22 audit events (PR #52, CI passed), and #23 Next.js foundation on branch `web-foundation`. The workspace page hasn't been used with real Clerk sign-in.


**Verified by running, using `LLM_PROVIDER=mock`:** all 45 tests pass. The live API returned the right status for the 120 vs 120 pair, the 120 vs 118 pair, a receipt and an `.eml` packet. A faint scan and a renamed non-PDF were rejected. Telemetry and API logs contained no sample personal data, and no uploads were left behind. The Streamlit server started.

**Not verified:** a real LLM call, real accuracy, hosted vision and any deployed environment. Mock's 100% evaluation only proves the plumbing, because mock is tuned to the samples.

**Present in the code:** upload checks, OCR, masking, extraction, rules, `/v1/extract`, `/v1/extract-eml`, telemetry, trace panel, Streamlit page, 40 samples, 20-document test sheet, 12 rule cases and an evaluation script.


**Not done**
- [ ] Measure accuracy with the real model (README says "Not measured yet")
- [ ] Confirm the LLM provider, its model ID and that its terms exclude training on prompts
- [ ] Deploy the live demo; the `Dockerfile` starts only the API, not Streamlit
- [ ] Confirm the Mermaid diagrams render on GitHub
- [ ] Build the Target layers: PostgreSQL, Redis, workers, auth, tenancy, Next.js, AWS

**Privacy fixes in the local change (#4):** surnames like Mills are no longer treated as company words, so a company named only with such words gets masked. Emails with unusual domains are masked. Masked text with a leftover email, mobile, Aadhaar or PAN shape blocks the model call. Model output is scrubbed. NER spans are split by line. A poor scan with an unclear type goes to manual review. Contact lines use OCR line numbers. `masked_before_llm` reports what happened.

**Remaining known issues**
1. **Company filter is still word-based:** a real company without a listed word gets masked, which lowers shipper and receiver accuracy. Check this with unseen documents (#9).
2. **Personal addresses:** detection relies on Presidio's LOCATION and misses street lines, for example "14 Harbour Road".
3. **Slow OCR:** about 3 seconds per document on this machine, so check the timeout and hosting size before deploying.
4. **Rate limit is per process and per client address:** behind Streamlit, all users share one address, so the limit protects the LLM quota rather than separating users.
5. **Test sheet isn't a separate holdout:** its 20 documents are drawn from the 40 samples. Consider adding unseen documents.

**Next step:** the blockers are real accuracy with an LLM key (#5), the database (#14) and the live demo (#6). Most remaining ALN-web issues depend on #14, #20 or #21.

**Open questions for the team:** submission deadline, final LLM provider, live demo hosting, who owns what, and whether the Target layers should start before submission.
