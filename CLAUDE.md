# Meridian OCR Connector

Team Delta's project for the Build Fast with AI (BFWAI) OCR Connector fellowship. Meridian Freight is fictional, and all documents must be synthetic. This repo is public, so never commit secrets or real documents.

## Start and end of every session

- **Start:** read "Current status", then compare it with `git log` and the code. If they disagree, trust the code and tell the user.
- **End:** when work changes the project's state, update "Current status" and "Decisions". Keep entries short and dated. Don't mark anything done unless it was run and verified.

## What we're building

A receiving clerk uploads shipping documents and gets an answer to one question: **does the invoice quantity match the packing list?**

- **Now:** meet every fellowship requirement. The assignment PDF and the `fde-week-2.vercel.app/meridian` page are the authority on what's graded.
- **After submission:** grow it into a B2B document intelligence SaaS, with Meridian as the first domain pack. Those product layers are now built, apart from AWS and connectors, and nothing is deployed.
- **Build order:** finish the graded fellowship work first. The user has also asked for the product issues to be built before submission.
- **Architecture authority:** `docs/ARCHITECTURE.md`, drawn from the user's six diagrams, is the source of truth for design. The assignment still decides what's graded. Label anything not built as Target.

Scoring: working demo 30%, extraction accuracy 25%, masking 15%, code and README 15%, presentation 15%, `.eml` stretch +10%. A trace containing a name fails the masking criterion even if Presidio ran.

## Rules that must not break

**Fields:** `fields` has exactly six keys: `invoice_number`, `shipper_name`, `receiver_name`, `shipment_date`, `total_quantity`, `total_weight_kg`. Use null when absent. Helper values such as units stay outside `fields`.

**Statuses:** exactly four, always decided by the engine in `app/domains/configured.py` from Meridian's configuration, and never by the model.

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
| `app/domains/configured.py` | Engine that runs a workflow: models, normalization, status decision |
| `app/domains/meridian/config/` | Meridian's versioned configuration, including the prompt. Add a new file; never edit a released one |
| `app/domains/meridian/grouping.py` | Grouping rules for uploads, using local OCR only |
| `ui/streamlit_app.py` | Clerk page and trace panel |
| `app/api/` | Product routes: tenancy, intake, shipments and jobs, reviews and summaries, customer API |
| `app/worker/` | Celery jobs; only IDs go through the queue |
| `web/` | Next.js product UI; see `web/README.md` |
| `docs/ARCHITECTURE.md` | Six architecture diagrams, labelled Built or Target |
| `docs/API.md` | Customer API and webhooks |
| `docs/SECURITY_REVIEW.md` | Findings and decisions from the pre-launch review (#36) |
| `scripts/` | Sample generation, `.eml` packets, evaluation |
| `samples/` | 40 synthetic documents, test sheets, `.eml` packets |
| `tests/` | Automated tests for every layer |

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
- **Frontend:** Streamlit stays the fellowship screen, as the assignment specifies. Next.js is the product UI.
- **OCR and PDF rendering:** Tesseract and pdf2image with Poppler, as built.
- **Two totals on a page:** `total_quantity` holds the shipping-unit total (cartons or packages), because put-away is by carton. The check compares like with like, so 1,200 pieces on an invoice matches a packing list printing 50 cartons and 1,200 pieces.
- **Person-only shipper or receiver:** the placeholder stays in the field, and the schema doesn't grow.
- **2026-11-02: Sign-in uses Clerk.** The API verifies tokens and stores no passwords. Product routes depend on `current_user`; `POST /v1/extract` stays open.
- **2026-11-02: Tenant isolation.** The organization comes from memberships, never a request body. Other tenants' records return 404. Each signed-in request runs as the restricted `meridian_app` role, because superusers skip row-level security. New tenant tables must add a policy in their migration.
- **2026-11-04: The user asked to build the product issues before submission.** This replaces the fellowship-first order for those issues. The assignment still decides what's graded.
- **Hosted vision:** off unless `VISION_MODEL` is set; otherwise unreadable scans return manual review.
- **2026-11-05: Document text is untrusted.** A line in a document changed the real model's answer, so prompt `meridian-v3` treats text as data and `app/pipeline/guard.py` sends obvious orders to manual review. See `docs/SECURITY_REVIEW.md`.
- **2026-11-05: Security review decisions.** The user accepted the proposals in `docs/SECURITY_REVIEW.md`. Still to do before launch: Clerk's verified-email setting, `MAX_EML_ATTACHMENTS=4` and a budget alert at deployment, and a Content-Security-Policy and webhook fixes under #33.
- **2026-11-05: Joining an organization needs an invitation and acceptance.** Invitations match the signed-in email, so Clerk must require a verified email address. There's no email sender yet, so people see invitations when they sign in. Expired ones are deleted nightly.

## Current status

**Last updated:** 2026-11-05.

**On `main`:** the full pipeline, `.eml` route, Streamlit page, Clerk sign-in, tenant isolation, audit events, shipments, Celery jobs, human review, approvals, customer API and webhooks, versioned configuration, personal GSTIN masking, retention, trends, document grouping and all Next.js screens (PRs through #74). 27 issues are still open, because their evidence or decisions are outstanding.

**Verified by running**
- **Real model (2026-11-04):** `gemini-3.1-flash-lite`, prompt `meridian-v2`: 100% on field, type and rule for the test sheet and holdout. The first holdout run was 94.0% on fields and 87.5% on rules, and its fixes mean the holdout is no longer unseen. This predates the #68 configuration change, which kept the prompt and parsing identical on 40,000 random cases.
- **Website (2026-11-04):** one real Clerk account signed in, created an organization and a shipment, uploaded documents and got one Incomplete result. This used SQLite and a local thread in place of Redis and Celery, kept outside the repo.
- **Customer API (2026-11-05):** `scripts/customer_example.py` submitted S01 and received a signed webhook over real HTTP, using the mock model, a throwaway database and threads instead of Celery.
- **Grouping (2026-11-05):** `scripts/evaluate_grouping.py`: 34 of 34 clean documents grouped and 0 wrong; 0 of 34 damaged documents grouped. The patterns were written after seeing these samples, so this isn't an unseen score.
- **New documents (2026-11-05):** 16 new synthetic documents, one run with the real model: fields 91/96 (94.8%), type 16/16, rules 10/10. All five misses were over-masking. Masking changed afterwards (#73) and the real model hasn't been re-run. The same author wrote these documents and the code.
- **Real stack (#74, in CI):** Celery, Redis and PostgreSQL ran a full check, recovered from a killed worker with one result, delivered a signed webhook, ran intake and ran retention under row-level security.
- **Provider terms:** Gemini's paid tier doesn't use prompts to improve products, and logs them for a limited time.
- **Browser tests (2026-11-05):** `web/e2e`, 14 tests, passed three runs in a row on this machine. They use the real API and the mock model, SQLite, threads in place of Celery, and a stand-in for Clerk, so they don't prove real sign-in or row-level security.
- **CI on every PR:** tests with PostgreSQL, including row-level security; the Docker stack; the demo image; the web app; the browser tests. CI uses `LLM_PROVIDER=mock`.

**Not verified**
- The website with a real Clerk account beyond the one Incomplete check
- Row-level security during a signed-in browser session
- Any deployed environment

**Remaining known issues**
1. **Company filter is word-based:** a company without a listed word gets masked, which lowers shipper and receiver accuracy.
2. **Personal addresses:** detection relies on Presidio's LOCATION and misses street lines, for example "14 Harbour Road".
3. **Slow OCR:** about 3 to 5 seconds per document on this machine, so check the timeout and hosting size before deploying.
4. **Rate limit is per process and per client address:** behind Streamlit, all users share one address, so the limit protects the LLM quota rather than separating users.
5. **Other invoice formats:** one uploaded invoice in a different format returned no shipper or quantity. That result hasn't been compared with its original.
6. **Webhooks:** DNS rebinding isn't fully closed and secrets are stored readable, both noted for #33.
7. **Intake:** files waiting for review are removed after about an hour, and the website limits a batch to about 11 MB.
8. **Page stuck after an action:** on the shipment and intake pages, updating in place sometimes left the page stuck even though the server had answered. They now do a full reload. The root cause was never found, and settings, exceptions and API access still update in place. Those passed the browser tests.

**Git safety:** stage files by name.

**Issues by what they need**
- **Real sign-in test:** #15, #24.
- **Browser evidence, ready to review:** #23, #25-#31, #39, #40.
- **Deployment on Google Cloud Run (recommended, user's account):** #6, then #11 and #12.
- **Decisions:** #32-#37, #41, #43, #44, and single sign-on in #45. #42 is merged. #38 is built for uploads, and the mailbox is #37.

**Next step:** deploy the live demo (#6), correct `docs/DEPLOY.md` once that works, then test real sign-in.

**Open questions for the team:** submission deadline, and when the AWS and decision issues should start.
