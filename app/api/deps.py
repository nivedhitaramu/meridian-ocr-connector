"""Who is calling, and which organization they're acting in. Product routes depend on these."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..core import auth
from ..db import audit, users
from ..db.models import MEMBER_ROLES, User
from ..db.session import get_db
from ..db.tenancy import set_scope


class NotFound(Exception):
    """Also used for another tenant's records, so a caller can't tell whether they exist."""


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


def current_member(request: Request, user: User = Depends(current_user), session: Session = Depends(get_db)) -> Member:
    """The organization comes from the caller's memberships, never from a request body.

    X-Organization-Id picks one when a person belongs to several, and must be one of theirs.
    """
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


def require_role(minimum: str):
    """Roles rank clerk, then supervisor, then admin."""
    ranks = {"clerk": 0, "supervisor": 1, "admin": 2}
    assert set(ranks) == set(MEMBER_ROLES)

    def check(member: Member = Depends(current_member)) -> Member:
        if ranks[member.role] < ranks[minimum]:
            raise Forbidden
        return member
    return check
