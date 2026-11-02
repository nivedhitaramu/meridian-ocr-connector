"""FastAPI app: POST /v1/extract (one file or a pair) and POST /v1/extract-eml (stretch)."""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core import config
from .ingestion import eml
from .pipeline import pii, runner as pipeline
from .core.errors import CLIENT_MESSAGE, PipelineError
from .domains.meridian.schemas import ExtractResponse
from .core.telemetry import LAST_TRACE, METRICS, instrument_fastapi

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="Meridian Freight OCR Connector", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,  # your own page only
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
instrument_fastapi(app)


@app.on_event("startup")
def _startup() -> None:
    pii.warm_up()


async def _read_capped(f: UploadFile) -> bytes:
    data = await f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise PipelineError("upload_too_large")
    return data


def _error(err: PipelineError) -> JSONResponse:
    status = 413 if err.error_class == "upload_too_large" else 415 if err.error_class == "upload_bad_type" else 422
    return JSONResponse(status_code=status, content={"error": CLIENT_MESSAGE, "request_id": LAST_TRACE.get("request_id")})


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract(file: UploadFile = File(...), file2: UploadFile | None = File(None)):
    try:
        blobs = [await _read_capped(file)]
        if file2 is not None:
            blobs.append(await _read_capped(file2))
        return await run_in_threadpool(pipeline.run, blobs)
    except PipelineError as err:
        return _error(err)


@app.post("/v1/extract-eml", response_model=ExtractResponse)
async def extract_eml(file: UploadFile = File(...)):
    try:
        blobs = eml.attachments(await _read_capped(file))
        return await run_in_threadpool(pipeline.run, blobs)
    except PipelineError as err:
        return _error(err)


@app.get("/v1/trace/last")
def last_trace():
    return LAST_TRACE or {"message": "No requests yet."}


@app.get("/v1/metrics")
def metrics():
    return METRICS.snapshot()


@app.get("/healthz")
def healthz():
    return {"ok": True}
