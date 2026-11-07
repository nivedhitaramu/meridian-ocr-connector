"""Run the 20-document test sheet and the rule cases; report the three accuracy numbers.

    python scripts/evaluate.py                         # calls the running API at http://localhost:8000
    python scripts/evaluate.py --api http://host:8000
    python scripts/evaluate.py --in-process            # no server; imports the pipeline directly
    python scripts/evaluate.py --sheet samples/holdout/holdout_sheet.csv --cases samples/holdout/holdout_cases.csv
                                                       # unseen holdout set from scripts/make_holdout.py

Writes samples/results_documents.csv (extracted vs expected, per field) and
samples/results_cases.csv (status vs expected). A non-default sheet adds its name,
e.g. samples/results_documents_holdout_sheet.csv. File names in a sheet are read
from the sheet's own folder. Normalization used for field match:
strings compared case-insensitively with collapsed spaces; numbers compared as floats
with weight tolerance 0.5 kg; dates compared as ISO strings.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
def norm(field: str, v):
    if v in (None, "", "None"):
        return None
    try:  # numbers compare as numbers, so 40 equals 40.0 and 1,200 equals 1200
        return float(str(v).replace(",", ""))
    except ValueError:
        return " ".join(str(v).split()).casefold()


def same(field: str, got, want) -> bool:
    g, w = norm(field, got), norm(field, want)
    if field.endswith("_kg") and isinstance(g, float) and isinstance(w, float):
        return abs(g - w) <= 0.5
    return g == w


def make_caller(args):
    if args.in_process:
        sys.path.insert(0, str(ROOT))
        from app.pipeline import runner as pipeline
        from app.core.errors import PipelineError

        def call(paths):
            try:
                return pipeline.run([p.read_bytes() for p in paths]).model_dump()
            except PipelineError as e:
                return {"error": e.error_class}
        return call

    import requests

    def call(paths):
        files = {"file": ("upload", paths[0].read_bytes())}
        if len(paths) > 1:
            files["file2"] = ("upload", paths[1].read_bytes())
        r = requests.post(f"{args.api}/v1/extract", files=files, timeout=300)
        return r.json() if r.ok else {"error": "request_failed"}
    return call


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--sheet", type=Path, default=SAMPLES / "test_sheet.csv", help="documents CSV")
    ap.add_argument("--cases", type=Path, default=SAMPLES / "test_cases.csv", help="rule cases CSV")
    args = ap.parse_args()
    call = make_caller(args)
    sheet_dir, cases_dir = args.sheet.resolve().parent, args.cases.resolve().parent
    suffix = "" if args.sheet.resolve() == (SAMPLES / "test_sheet.csv").resolve() else f"_{args.sheet.stem}"

    # ---- documents: type + fields
    rows, f_ok, f_total, t_ok, t_total = [], 0, 0, 0, 0
    with open(args.sheet) as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in reader.fieldnames if f not in ("file", "expected_document_type")]  # from the sheet, for any workflow
        for exp in reader:
            res = call([sheet_dir / exp["file"]])
            if "error" in res:
                got_type, got = "error", {}
            else:
                got_type, got = res["documents"][0]["document_type"], res["documents"][0]["fields"]
            t_total += 1
            t_ok += got_type == exp["expected_document_type"]
            row = {"file": exp["file"], "expected_type": exp["expected_document_type"], "got_type": got_type}
            for f in fields:
                ok = same(f, got.get(f), exp[f])
                f_total += 1
                f_ok += ok
                row[f"{f}_expected"], row[f"{f}_got"], row[f"{f}_ok"] = exp[f], got.get(f), ok
            rows.append(row)
            print(f"{exp['file']:<24} type={'OK ' if got_type == exp['expected_document_type'] else 'BAD'} "
                  f"fields={sum(row[f'{f}_ok'] for f in fields)}/{len(fields)}")
    with open(SAMPLES / f"results_documents{suffix}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- rule cases
    c_rows, r_ok = [], 0
    with open(args.cases) as fh:
        cases = list(csv.DictReader(fh))
    for c in cases:
        paths = [cases_dir / c["file"]] + ([cases_dir / c["file2"]] if c["file2"] else [])
        res = call(paths)
        got = res.get("check", {}).get("status", "error")
        r_ok += got == c["expected_status"]
        c_rows.append({**c, "got_status": got, "reason": res.get("check", {}).get("reason", ""), "ok": got == c["expected_status"]})
        print(f"{c['case']:<18} expected={c['expected_status']:<15} got={got}")
    with open(SAMPLES / f"results_cases{suffix}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(c_rows[0].keys()))
        w.writeheader()
        w.writerows(c_rows)

    print("\n=== Accuracy ===")
    print(f"Field match (normalized): {f_ok}/{f_total} = {f_ok / f_total:.1%}")
    print(f"Document-type accuracy:   {t_ok}/{t_total} = {t_ok / t_total:.1%}")
    print(f"Rule accuracy:            {r_ok}/{len(cases)} = {r_ok / len(cases):.1%}")


if __name__ == "__main__":
    main()
