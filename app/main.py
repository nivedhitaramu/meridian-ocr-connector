"""FastAPI app: POST /v1/extract (one file or a pair) and POST /v1/extract-eml (stretch)."""
from __future__ import annotations

import hmac
import json
import logging
import uuid

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .api import deps, tenancy
from .api.deps import current_user
from .core import auth, config
from .db import users
from .db.models import User
from .db.session import get_db
from .db.tenancy import set_scope
from .ingestion import eml
from .pipeline import pii, runner as pipeline
from .core.errors import CLIENT_MESSAGE, PipelineError
from .core.rate_limit import RateLimiter
from .domains.meridian.schemas import ExtractResponse
from .core.telemetry import LAST_TRACE, METRICS, instrument_fastapi

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("meridian")

app = FastAPI(title="Meridian Freight OCR Connector", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,  # your own page only
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Organization-Id"],
)
instrument_fastapi(app)
app.include_router(tenancy.router)
limiter = RateLimiter(config.RATE_LIMIT_PER_MINUTE)


@app.on_event("startup")
def _startup() -> None:
    pii.warm_up()


@app.exception_handler(auth.AuthError)
def _not_signed_in(_: Request, err: auth.AuthError) -> JSONResponse:
    log.info(json.dumps({"level": "info", "stage": "auth", "error_class": str(err)}))  # the class only, never the token
    return JSONResponse(status_code=401, content={"error": "Not signed in."}, headers={"WWW-Authenticate": "Bearer"})


@app.exception_handler(deps.NotFound)
def _not_found(_: Request, __: deps.NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Not found."})


@app.exception_handler(deps.Forbidden)
def _forbidden(_: Request, __: deps.Forbidden) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": "You don't have permission to do this."})


async def _read_capped(f: UploadFile) -> bytes:
    data = await f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise PipelineError("upload_too_large")
    return data


def _error(err: PipelineError) -> JSONResponse:
    status = 413 if err.error_class == "upload_too_large" else 415 if err.error_class == "upload_bad_type" else 422
    # An upload rejected before the pipeline starts has no id yet, so give it its own.
    request_id = err.request_id or str(uuid.uuid4())
    return JSONResponse(status_code=status, content={"error": CLIENT_MESSAGE, "request_id": request_id})


def _rate_limited(request: Request) -> JSONResponse | None:
    if limiter.allow(request.client.host if request.client else "unknown"):
        return None
    return JSONResponse(status_code=429, content={"error": "Too many requests. Try again in a minute."},
                        headers={"Retry-After": "60"})


def _not_authorized(request: Request) -> JSONResponse | None:
    token = config.INTERNAL_API_TOKEN
    if not token or hmac.compare_digest(request.headers.get("X-Internal-Token", ""), token):
        return None
    return JSONResponse(status_code=401, content={"error": "Not authorized."})


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract(request: Request, file: UploadFile = File(...), file2: UploadFile | None = File(None)):
    if (refused := _rate_limited(request)) is not None:
        return refused
    try:
        blobs = [await _read_capped(file)]
        if file2 is not None:
            blobs.append(await _read_capped(file2))
        return await run_in_threadpool(pipeline.run, blobs)
    except PipelineError as err:
        return _error(err)


@app.post("/v1/extract-eml", response_model=ExtractResponse)
async def extract_eml(request: Request, file: UploadFile = File(...)):
    if (refused := _rate_limited(request)) is not None:
        return refused
    try:
        blobs = eml.attachments(await _read_capped(file))
        return await run_in_threadpool(pipeline.run, blobs)
    except PipelineError as err:
        return _error(err)


@app.get("/v1/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_db)):
    set_scope(session, user.id)
    return {
        "id": str(user.id),
        "email": user.email,
        "memberships": [{"organization_id": str(m.organization_id), "role": m.role}
                        for m in users.memberships(session, user)],
    }


@app.get("/v1/trace/last")
def last_trace(request: Request):
    if (refused := _not_authorized(request)) is not None:
        return refused
    return LAST_TRACE or {"message": "No requests yet."}


@app.get("/v1/metrics")
def metrics(request: Request):
    if (refused := _not_authorized(request)) is not None:
        return refused
    return METRICS.snapshot()


@app.get("/healthz")
def healthz():
    return {"ok": True}
