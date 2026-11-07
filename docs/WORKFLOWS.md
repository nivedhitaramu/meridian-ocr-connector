# Adding a workflow

A workflow is one kind of document check, such as Meridian's invoice against packing list. The pipeline, privacy steps, rules engine, API, jobs and website are shared. A workflow adds only its own configuration and an optional offline stand-in for tests.

## The two workflows

| Workflow | Documents | Check | Select with |
|---|---|---|---|
| `meridian` | Commercial invoice, packing list, delivery receipt | Total quantity | `DOMAIN=meridian` (the default) |
| `receiving` | Purchase order, goods received note | Total units ordered against received | `DOMAIN=receiving` |

One deployment runs one workflow.

## Steps

1. Create `app/domains/<name>/` with an empty `__init__.py`.
2. Add `config/<name>-1.json`. It sets the document types, fields and their types, which fields are references or company names, units, and the check with its reason templates. Copy `app/domains/receiving/config/receiving-1.json` as a starting point. Keep the line that tells the model document text is data.
3. Add `domain.py`, which loads the configuration. `app/domains/receiving/domain.py` is the whole file.
4. Optionally, add `mock.py`, a regex stand-in so tests run without a model. Never report its accuracy as the model's.
5. Make a synthetic test set with a sheet and cases, like `scripts/make_receiving_samples.py`, then evaluate it:

```bash
DOMAIN=receiving python scripts/evaluate.py --in-process --sheet samples/receiving/receiving_sheet.csv --cases samples/receiving/receiving_cases.csv
```

6. Add the configuration's hash to its test, so a released version is never edited. Change a workflow by adding a new configuration file.

The registry finds a workflow by its folder name, the website shows whatever fields the configuration defines, and the evaluation script reads the fields from the sheet. None of them needs a change.

## What isn't shared yet

- **Grouping in Intake** (`app/domains/meridian/grouping.py`) recognizes Meridian's references and titles only. With another workflow, Intake would send most files to a person.
- **Document labels on the website** are in `web/src/components/labels.tsx`. An unknown type shows as "Document", so add its label there.
- **Company detection in masking** uses a word list (Pvt, Ltd, Traders and so on) in `app/pipeline/pii.py`. A company without one of those words is masked, which lowers accuracy on the company fields.

## Receiving results

These are from 2026-11-07, with `gemini-3.1-flash-lite`, prompt `receiving-v1`, on the 9 documents and 5 cases in `samples/receiving/`.

| Measure | Result |
|---|---|
| Fields | 45/45 (100%) |
| Document type | 9/9 |
| Rules | 5/5: two Matches, a quantity Mismatch, a unit Mismatch and an Incomplete |

The same author made these clean, typed PDFs and the configuration, and this was one run. So this shows the workflow works end to end, not how it would score on real or unseen documents.
