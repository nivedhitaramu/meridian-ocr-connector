"""Traces, safe JSON log lines and counters.

The safety rule is an ALLOW-list: only the keys below can ever reach a span, a log line
or a metric. OCR text, prompts, completions, field values, the placeholder vault and the
original filename have no key here, so they cannot leak by accident.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

log = logging.getLogger("meridian")

SAFE_KEYS = {
    "request_id", "stage", "duration_ms", "level", "ts", "outcome", "error_class",
    "doc_type", "page_count", "file_ext", "file_count", "slot",
    "ocr_engine", "char_count", "mean_confidence", "fallback",
    "entity_counts", "placeholder_count", "output_scrubbed",
    "model", "prompt_version", "prompt_tokens", "completion_tokens",
    "check_status",
}

# ------------------------------------------------------------- OpenTelemetry
_tracer = None
try:  # optional: the app still runs, and still logs safely, without these packages
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _provider = TracerProvider(resource=Resource.create({"service.name": "meridian-ocr-connector"}))
    if config.OTEL_CONSOLE_EXPORT:
        _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    if config.OTEL_EXPORTER_OTLP_ENDPOINT:  # e.g. Jaeger at http://localhost:4318/v1/traces
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT)))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("meridian")
except Exception:  # pragma: no cover
    _tracer = None


def sanitize(attrs: dict) -> dict:
    clean = {}
    for k, v in attrs.items():
        if k not in SAFE_KEYS or v is None:
            continue
        if k == "entity_counts":
            v = {str(t): int(c) for t, c in dict(v).items()}
        clean[k] = v
    return clean


def _otel_value(v):
    return json.dumps(v) if isinstance(v, dict) else v


# ------------------------------------------------------------------ metrics
class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests_by_outcome: Counter[str] = Counter()
        self.stage_latency_ms: dict[str, list[int]] = defaultdict(list)
        self.fallbacks = 0
        self.documents = 0
        self.entities_by_type: Counter[str] = Counter()
        self.checks_by_status: Counter[str] = Counter()

    def snapshot(self) -> dict:
        with self._lock:
            def stats(xs):
                xs = sorted(xs[-500:])
                return {"count": len(xs), "p50": xs[len(xs) // 2] if xs else None,
                        "p95": xs[int(len(xs) * 0.95)] if xs else None}
            return {
                "requests_by_outcome": dict(self.requests_by_outcome),
                "stage_latency_ms": {k: stats(v) for k, v in self.stage_latency_ms.items()},
                "fallback_rate": round(self.fallbacks / self.documents, 3) if self.documents else 0.0,
                "entities_by_type": dict(self.entities_by_type),
                "checks_by_status": dict(self.checks_by_status),
            }


METRICS = Metrics()


# -------------------------------------------------------------- per request
class RequestTrace:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.events: list[dict] = []
        self.timings_ms: dict[str, int] = defaultdict(int)
        self._root_cm = None

    def emit(self, level: str = "info", **attrs) -> None:
        line = sanitize({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "level": level, "request_id": self.request_id, **attrs})
        self.events.append(line)
        _write_jsonl(line)

    @contextmanager
    def stage(self, name: str, **attrs):
        """Span named ocr / pii / llm / rule. Yields a dict the caller can add safe attrs to."""
        extra: dict = {}
        start = time.perf_counter()
        span_cm = _tracer.start_as_current_span(name) if _tracer else None
        span = span_cm.__enter__() if span_cm else None
        try:
            yield extra
        finally:
            ms = int((time.perf_counter() - start) * 1000)
            self.timings_ms[name] += ms
            with METRICS._lock:
                METRICS.stage_latency_ms[name].append(ms)
            safe = sanitize({"request_id": self.request_id, **attrs, **extra})
            if span is not None:
                for k, v in safe.items():
                    span.set_attribute(f"meridian.{k}", _otel_value(v))
                span_cm.__exit__(None, None, None)
            self.emit(stage=name, duration_ms=ms, **attrs, **extra)

    @contextmanager
    def root(self):
        cm = _tracer.start_as_current_span("extract_request") if _tracer else None
        span = cm.__enter__() if cm else None
        if span is not None:
            span.set_attribute("meridian.request_id", self.request_id)
        try:
            yield
        finally:
            if cm:
                cm.__exit__(None, None, None)


_write_lock = threading.Lock()


def _write_jsonl(line: dict) -> None:
    payload = json.dumps(line, separators=(",", ":"))
    log.info(payload)
    try:
        config.TELEMETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock, open(config.TELEMETRY_LOG, "a", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    except OSError:
        pass


# The last request's trace, for the demo panel. Already sanitized.
LAST_TRACE: dict = {}


def instrument_fastapi(app) -> None:
    """Auto-instrument HTTP spans. Headers and bodies are not captured by default; keep it so."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz")
    except Exception:  # pragma: no cover
        pass
