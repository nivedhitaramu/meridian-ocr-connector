"""Every error code the API can save either has its own explanation on the website or is meant to use the generic one.

The link is only matching text, so nothing else would notice a new code shown to a reviewer as "couldn't be read".
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "web" / "src" / "components" / "labels.tsx"

# Codes where "The document couldn't be read." is enough, or that only the open extract route returns.
GENERIC = {
    "eml_no_attachments", "eml_unreadable", "file_unreadable", "internal_error", "llm_http_error", "llm_not_configured",
    "llm_rate_limited", "llm_unreachable", "ocr_engine_missing", "schema_invalid", "upload_bad_type", "upload_empty",
    "upload_too_large",
}


def raised_codes() -> set[str]:
    codes = set()
    for path in (ROOT / "app").rglob("*.py"):
        codes |= set(re.findall(r'PipelineError\("([a-z_]+)"', path.read_text(encoding="utf-8")))
    return codes


def explained_codes() -> set[str]:
    block = re.search(r"const ERROR_LABELS[^{]*{(.*?)};", LABELS.read_text(encoding="utf-8"), re.S)
    assert block, "ERROR_LABELS not found in labels.tsx"
    return set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))


def test_the_scan_finds_codes():
    assert {"manual_review_residual_pii", "file_unreadable"} <= raised_codes()


def test_every_code_is_explained_or_meant_to_be_generic():
    missing = raised_codes() - explained_codes() - GENERIC
    assert not missing, f"add these to ERROR_LABELS in labels.tsx, or to GENERIC here: {sorted(missing)}"


def test_every_manual_review_code_has_its_own_explanation():
    """A reviewer must know why a person is needed."""
    manual = {code for code in raised_codes() if code.startswith("manual_review")}
    assert manual and manual <= explained_codes()
    assert not manual & GENERIC


def test_generic_list_holds_only_real_codes():
    assert GENERIC <= raised_codes(), sorted(GENERIC - raised_codes())
