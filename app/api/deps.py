"""Who is calling, and which organization they're acting in. Product routes depend on these."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core import auth, config
from ..core.rate_limit import RateLimiter
from ..db import audit, users
from ..db.models import ApiKey, MEMBER_ROLES, OrganizationMember, User
from ..db.session import get_db
from ..db.tenancy import set_scope


class NotFound(Exception):
    """Also used for another tenant's records, so a caller can't tell whether they exist."""


class RateLimited(Exception):
    """This API key has made too many requests this minute."""


_key_limiter = RateLimiter(config.API_KEY_RATE_LIMIT_PER_MINUTE)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class Forbidden(Exception):
    """A member of this organization, but with too low a role."""


@dataclass(frozen=True)
class Member:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str


def request_id_for(request: Request) -> str:
    """One ID per request, for matching audit events to logs."""
    if not hasattr(request.state, "request_id"):
        request.state.request_id = str(uuid.uuid4())
    return request.state.request_id


def current_user(request: Request, session: Session = Depends(get_db)) -> User:
    """Every product route depends on this. The assignment's /v1/extract stays open."""
    identity = auth.verify_token(auth.bearer_token(request.headers.get("Authorization")))
    request.state.identity = identity
    return users.user_for(session, identity)


def _member_for_key(request: Request, session: Session, presented: str) -> Member:
    """A key acts for one organization as a clerk, so it can't manage members, keys or approvals."""
    digest = hash_key(presented)
    set_scope(session, None)
    if session.connection().dialect.name == "postgresql":
        session.execute(text("SELECT set_config('app.api_key_hash', :digest, true)"), {"digest": digest})
    key = session.scalar(select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked_at.is_(None)))
    if key is None or key.created_by is None:
        raise auth.AuthError("api_key_invalid")
    organization_id, user_id = key.organization_id, key.created_by
    set_scope(session, user_id, organization_id)
    # The person who made the key must still belong, so removing them also stops their keys.
    if session.get(OrganizationMember, (organization_id, user_id)) is None:
        raise auth.AuthError("api_key_owner_removed")
    if not _key_limiter.allow(str(key.id)):
        raise RateLimited
    key.last_used_at = datetime.now(timezone.utc)
    session.commit()
    set_scope(session, user_id, organization_id)
    return Member(user_id=user_id, organization_id=organization_id, role="clerk")


def current_member(request: Request, session: Session = Depends(get_db)) -> Member:
    """The organization comes from the caller's memberships or API key, never from a request body.

    X-Organization-Id picks one when a person belongs to several, and must be one of theirs.
    """
    presented = request.headers.get("X-API-Key")
    if presented:
        return _member_for_key(request, session, presented)
    user = current_user(request, session)
    user_id = user.id
    set_scope(session, user_id)
    rows = users.memberships(session, user)
    wanted = request.headers.get("X-Organization-Id")
    if wanted is not None:
        rows = [m for m in rows if str(m.organization_id) == wanted.strip().lower()]
    if len(rows) != 1:
        raise NotFound
    member = Member(user_id=user_id, organization_id=rows[0].organization_id, role=rows[0].role)
    set_scope(session, user_id, member.organization_id)
    if request.state.identity.session_id:
        audit.record_session_once(session, member.organization_id, user_id, request.state.identity.session_id,
                                  request_id_for(request))
    return member


ROLE_RANKS = {"clerk": 0, "supervisor": 1, "admin": 2}
assert set(ROLE_RANKS) == set(MEMBER_ROLES)


def require_role(minimum: str):
    """Roles rank clerk, then supervisor, then admin."""

    def check(member: Member = Depends(current_member)) -> Member:
        if ROLE_RANKS[member.role] < ROLE_RANKS[minimum]:
            raise Forbidden
        return member
    return check
