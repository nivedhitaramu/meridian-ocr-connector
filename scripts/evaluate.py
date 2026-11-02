"""Run the 20-document test sheet and the rule cases; report the three accuracy numbers.

    python scripts/evaluate.py                         # calls the running API at http://localhost:8000
    python scripts/evaluate.py --api http://host:8000
    python scripts/evaluate.py --in-process            # no server; imports the pipeline directly

Writes samples/results_documents.csv (extracted vs expected, per field) and
samples/results_cases.csv (status vs expected). Normalization used for field match:
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
FIELDS = ["invoice_number", "shipper_name", "receiver_name", "shipment_date", "total_quantity", "total_weight_kg"]


def norm(field: str, v):
    if v in (None, "", "None"):
        return None
    if field in ("total_quantity", "total_weight_kg"):
        return float(str(v).replace(",", ""))
    return " ".join(str(v).split()).casefold()


def same(field: str, got, want) -> bool:
    g, w = norm(field, got), norm(field, want)
    if field == "total_weight_kg" and g is not None and w is not None:
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
    args = ap.parse_args()
    call = make_caller(args)

    # ---- documents: type + fields
    rows, f_ok, f_total, t_ok, t_total = [], 0, 0, 0, 0
    with open(SAMPLES / "test_sheet.csv") as fh:
        for exp in csv.DictReader(fh):
            res = call([SAMPLES / exp["file"]])
            if "error" in res:
                got_type, got = "error", {}
            else:
                got_type, got = res["documents"][0]["document_type"], res["documents"][0]["fields"]
            t_total += 1
            t_ok += got_type == exp["expected_document_type"]
            row = {"file": exp["file"], "expected_type": exp["expected_document_type"], "got_type": got_type}
            for f in FIELDS:
                ok = same(f, got.get(f), exp[f])
                f_total += 1
                f_ok += ok
                row[f"{f}_expected"], row[f"{f}_got"], row[f"{f}_ok"] = exp[f], got.get(f), ok
            rows.append(row)
            print(f"{exp['file']:<24} type={'OK ' if got_type == exp['expected_document_type'] else 'BAD'} "
                  f"fields={sum(row[f'{f}_ok'] for f in FIELDS)}/6")
    with open(SAMPLES / "results_documents.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- rule cases
    c_rows, r_ok = [], 0
    with open(SAMPLES / "test_cases.csv") as fh:
        cases = list(csv.DictReader(fh))
    for c in cases:
        paths = [SAMPLES / c["file"]] + ([SAMPLES / c["file2"]] if c["file2"] else [])
        res = call(paths)
        got = res.get("check", {}).get("status", "error")
        r_ok += got == c["expected_status"]
        c_rows.append({**c, "got_status": got, "reason": res.get("check", {}).get("reason", ""), "ok": got == c["expected_status"]})
        print(f"{c['case']:<18} expected={c['expected_status']:<15} got={got}")
    with open(SAMPLES / "results_cases.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(c_rows[0].keys()))
        w.writeheader()
        w.writerows(c_rows)

    print("\n=== Accuracy ===")
    print(f"Field match (normalized): {f_ok}/{f_total} = {f_ok / f_total:.1%}")
    print(f"Document-type accuracy:   {t_ok}/{t_total} = {t_ok / t_total:.1%}")
    print(f"Rule accuracy:            {r_ok}/{len(cases)} = {r_ok / len(cases):.1%}")


if __name__ == "__main__":
    main()
