"""Steps 1-5 wired together. Used by the API, the .eml endpoint and the eval script."""
from __future__ import annotations

import uuid

from . import llm, ocr, pii, vision
from ..core import config
from ..domains import registry
from ..domains.base import Domain, PIIInfo, PipelineInfo
from ..ingestion import upload
from ..core.errors import PipelineError
from ..core.telemetry import LAST_TRACE, METRICS, RequestTrace


def _process_one(slot: int, data: bytes, vault: pii.PlaceholderVault, tr: RequestTrace, domain: Domain):
    stored = upload.store(data)  # random name; original filename is never seen here
    try:
        with tr.stage("ocr", slot=slot, file_ext=stored.kind, ocr_engine="tesseract") as attrs:
            pages = ocr.load_pages(stored.path, stored.kind)
            result = ocr.run_ocr(pages)
            fallback = result.needs_fallback()
            attrs.update(page_count=result.page_count, char_count=len(result.text),
                         mean_confidence=result.mean_confidence, fallback=fallback)

        with tr.stage("pii", slot=slot) as attrs:
            before = dict(vault.entity_counts)
            masked_text, spans = pii.mask(result.text, vault, vision.signature_band_spans(result, domain))
            delta = {k: v - before.get(k, 0) for k, v in vault.entity_counts.items() if v - before.get(k, 0)}
            attrs.update(entity_counts=delta, placeholder_count=vault.placeholder_count)

        protected = False  # set only once this document's redaction or masking checks have passed
        with tr.stage("llm", slot=slot, prompt_version=domain.prompt_version) as attrs:
            if fallback:
                # Never the raw scan: redact boxes, contact lines and receipt signature band first.
                redacted = vision.redact_pages(result, spans, domain)
                protected = True
                out = llm.extract_from_images(redacted, domain)
            else:
                if pii.residual_types(masked_text):  # fail closed: this text must not leave
                    raise PipelineError("manual_review_residual_pii")
                protected = True
                out = llm.extract_from_text(masked_text, domain)
            scrubbed = pii.scrub_fields(out.extraction.fields, vault, domain.reference_fields, domain.party_fields)
            attrs.update(model=out.model, prompt_tokens=out.prompt_tokens, output_scrubbed=scrubbed,
                         completion_tokens=out.completion_tokens, doc_type=out.extraction.document_type)

        parsed = domain.post_process(out.extraction)
        doc = domain.build_document(slot, parsed, result.page_count, fallback)
        return doc, parsed, out.model, protected
    finally:
        stored.delete()  # the upload never outlives the request


def run(files: list[bytes]):
    domain = registry.active()
    request_id = str(uuid.uuid4())
    tr = RequestTrace(request_id)
    vault = pii.PlaceholderVault()  # shared across files so one person = one token
    try:
        with tr.root():
            tr.emit(stage="request.start", file_count=len(files))
            docs, parsed, models, protected = [], [], set(), []
            for slot, data in enumerate(files, start=1):
                d, p, m, safe = _process_one(slot, data, vault, tr, domain)
                docs.append(d)
                parsed.append(p)
                models.add(m)
                protected.append(safe)

            with tr.stage("rule") as attrs:
                result = domain.check(parsed)
                attrs.update(check_status=result.status)

            response = domain.build_response(
                request_id, docs, result,
                PIIInfo(masked_before_llm=all(protected), entity_counts=dict(vault.entity_counts),
                        placeholder_count=vault.placeholder_count),
                PipelineInfo(
                    ocr_engine="tesseract",
                    used_vision_fallback=any(d.used_vision_fallback for d in docs),
                    model=", ".join(sorted(models)), prompt_version=domain.prompt_version,
                    timings_ms={k: tr.timings_ms.get(k, 0) for k in ("ocr", "pii", "llm", "rule")},
                ),
            )
            _record(tr, "ok", response=response)
            return response
    except PipelineError as err:
        _record(tr, "error", error_class=err.error_class)
        err.request_id = request_id
        raise
    except Exception as exc:
        _record(tr, "error", error_class="internal_error")
        raise PipelineError("internal_error", request_id) from exc
    finally:
        vault.clear()  # placeholder map dies with the request


def _plain(value) -> dict:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _status(response):
    return _plain(response.check)["status"]


def _pii_counts(response) -> dict:
    return dict(_plain(response.pii)["entity_counts"])


def _record(tr: RequestTrace, outcome: str, response=None, error_class: str | None = None):
    with METRICS._lock:
        METRICS.requests_by_outcome[outcome if outcome == "ok" else error_class or "error"] += 1
        if response:
            METRICS.documents += len(response.documents)
            METRICS.fallbacks += sum(d.used_vision_fallback for d in response.documents)
            METRICS.entities_by_type.update(_pii_counts(response))
            METRICS.checks_by_status[_status(response)] += 1
    tr.emit(level="info" if outcome == "ok" else "error", stage="request.end", outcome=outcome,
            error_class=error_class, check_status=_status(response) if response else None)
    LAST_TRACE.clear()
    LAST_TRACE.update({
        "request_id": tr.request_id,
        "outcome": outcome,
        "error_class": error_class,
        "timings_ms": {k: tr.timings_ms.get(k, 0) for k in ("ocr", "pii", "llm", "rule")},
        "check_status": _status(response) if response else None,
        "entity_counts": _pii_counts(response) if response else {},
        "events": list(tr.events),
    })
