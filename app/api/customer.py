"""Customer API keys and webhook endpoints. Admins manage them; each secret is shown only once."""
from __future__ import annotations

import secrets
import uuid
from typing import Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import webhook_url
from ..db import audit
from ..db.models import ApiKey, WebhookDelivery, WebhookEndpoint
from ..db.session import get_db
from .deps import Member, NotFound, hash_key, request_id_for, require_role

router = APIRouter(prefix="/v1")
admin_only = require_role("admin")


class NewKey(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class NewWebhook(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    format: Literal["event", "wms_receipt"] = "event"  # app/connectors/formats.py


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _key_json(key: ApiKey) -> dict:
    return {"id": str(key.id), "name": key.name, "prefix": key.prefix, "created_at": _iso(key.created_at),
            "last_used_at": _iso(key.last_used_at), "revoked_at": _iso(key.revoked_at)}


def _new_key(session: Session, member: Member, name: str) -> tuple[ApiKey, str]:
    secret = "mk_" + secrets.token_urlsafe(32)
    key = ApiKey(organization_id=member.organization_id, name=name, prefix=secret[:10], key_hash=hash_key(secret),
                 created_by=member.user_id)
    session.add(key)
    session.flush()
    return key, secret


def _active_key(session: Session, member: Member, key_id: uuid.UUID) -> ApiKey:
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == member.organization_id,
                                              ApiKey.revoked_at.is_(None)))
    if key is None:
        raise NotFound
    return key


@router.get("/api-keys")
def list_keys(member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    rows = session.scalars(select(ApiKey).where(ApiKey.organization_id == member.organization_id)
                           .order_by(ApiKey.created_at.desc(), ApiKey.id))
    return [_key_json(key) for key in rows]


@router.post("/api-keys", status_code=201)
def create_key(request: Request, body: NewKey, member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    key, secret = _new_key(session, member, body.name.strip())
    audit.record(session, member.organization_id, member.user_id, audit.API_KEY_CREATED, f"api_key:{key.id}", request_id_for(request))
    session.commit()
    return {**_key_json(key), "key": secret}


@router.post("/api-keys/{key_id}/rotate", status_code=201)
def rotate_key(request: Request, key_id: uuid.UUID, member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    """The old key stops working at once. Its replacement is shown once."""
    old = _active_key(session, member, key_id)
    old.revoked_at = datetime.now(timezone.utc)
    key, secret = _new_key(session, member, old.name)
    audit.record(session, member.organization_id, member.user_id, audit.API_KEY_ROTATED, f"api_key:{key.id}", request_id_for(request))
    session.commit()
    return {**_key_json(key), "key": secret}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(request: Request, key_id: uuid.UUID, member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    key = _active_key(session, member, key_id)
    key.revoked_at = datetime.now(timezone.utc)
    audit.record(session, member.organization_id, member.user_id, audit.API_KEY_REVOKED, f"api_key:{key.id}", request_id_for(request))
    session.commit()
    return Response(status_code=204)


def _webhook_json(endpoint: WebhookEndpoint) -> dict:
    return {"id": str(endpoint.id), "url": endpoint.url, "format": endpoint.format, "created_at": _iso(endpoint.created_at)}


@router.get("/webhooks")
def list_webhooks(member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    rows = session.scalars(select(WebhookEndpoint).where(
        WebhookEndpoint.organization_id == member.organization_id, WebhookEndpoint.disabled_at.is_(None))
        .order_by(WebhookEndpoint.created_at.desc(), WebhookEndpoint.id))
    return [_webhook_json(endpoint) for endpoint in rows]


@router.post("/webhooks", status_code=201)
def add_webhook(request: Request, body: NewWebhook, member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    url = body.url.strip()
    if not webhook_url.acceptable(url, resolve=False):
        return JSONResponse(status_code=422, content={"error": "Use a public HTTPS address."})
    secret = "whsec_" + secrets.token_urlsafe(32)
    endpoint = WebhookEndpoint(organization_id=member.organization_id, url=url, secret=secret, format=body.format)
    session.add(endpoint)
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.WEBHOOK_ADDED, f"webhook:{endpoint.id}", request_id_for(request))
    session.commit()
    return {**_webhook_json(endpoint), "secret": secret}


@router.delete("/webhooks/{endpoint_id}", status_code=204)
def remove_webhook(request: Request, endpoint_id: uuid.UUID, member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    endpoint = session.scalar(select(WebhookEndpoint).where(
        WebhookEndpoint.id == endpoint_id, WebhookEndpoint.organization_id == member.organization_id,
        WebhookEndpoint.disabled_at.is_(None)))
    if endpoint is None:
        raise NotFound
    endpoint.disabled_at = datetime.now(timezone.utc)
    audit.record(session, member.organization_id, member.user_id, audit.WEBHOOK_REMOVED, f"webhook:{endpoint.id}", request_id_for(request))
    session.commit()
    return Response(status_code=204)


@router.get("/webhooks/deliveries")
def list_deliveries(member: Member = Depends(admin_only), session: Session = Depends(get_db)):
    rows = session.scalars(select(WebhookDelivery).where(WebhookDelivery.organization_id == member.organization_id)
                           .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id).limit(50))
    return [{"id": str(row.id), "endpoint_id": str(row.endpoint_id), "job_id": str(row.job_id), "status": row.status,
             "attempts": row.attempts, "response_code": row.response_code, "created_at": _iso(row.created_at)} for row in rows]
