"""Joining an organization takes two steps: an admin invites an email, and the person with that email accepts.

The answer to an invitation is the same whether or not the email has an account, so it can't be used to find out.
An invitation is matched to the signed-in email, so Clerk must be set to require a verified email address.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import audit
from ..db.models import Organization, OrganizationInvitation, OrganizationMember, User
from ..db.session import get_db
from ..db.tenancy import set_invitee, set_scope
from .deps import Member, NotFound, current_user, request_id_for, require_role

router = APIRouter(prefix="/v1")

VALID_FOR = timedelta(days=7)


class NewInvitation(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "supervisor", "clerk"] = "clerk"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)  # SQLite returns no timezone


def _organization_json(invitation: OrganizationInvitation) -> dict:
    expires_at = _utc(invitation.expires_at)
    return {"id": str(invitation.id), "email": invitation.email, "role": invitation.role,
            "expires_at": expires_at.isoformat(), "expired": expires_at <= _now()}


@router.post("/organization/invitations", status_code=201)
def invite(request: Request, body: NewInvitation, member: Member = Depends(require_role("admin")),
           session: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        return JSONResponse(status_code=422, content={"error": "Enter an email address."})
    joined = session.scalar(
        select(OrganizationMember.user_id).join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == member.organization_id, func.lower(User.email) == email))
    if joined is not None:
        return JSONResponse(status_code=409, content={"error": "This person is already a member."})
    invitation = session.scalar(select(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == member.organization_id, OrganizationInvitation.email == email))
    if invitation is None:  # inviting again replaces the role and restarts the time limit
        invitation = OrganizationInvitation(organization_id=member.organization_id, email=email)
        session.add(invitation)
    invitation.role, invitation.invited_by, invitation.expires_at = body.role, member.user_id, _now() + VALID_FOR
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.MEMBER_INVITED,
                 f"invitation:{invitation.id}:{body.role}", request_id_for(request))
    try:
        session.commit()
    except IntegrityError:  # sent twice at once, and the other request saved it
        session.rollback()
        return JSONResponse(status_code=409, content={"error": "This person has just been invited."})
    return _organization_json(invitation)


@router.get("/organization/invitations")
def list_invitations(member: Member = Depends(require_role("admin")), session: Session = Depends(get_db)):
    rows = session.scalars(select(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == member.organization_id).order_by(OrganizationInvitation.email))
    return [_organization_json(row) for row in rows]


@router.delete("/organization/invitations/{invitation_id}", status_code=204)
def cancel_invitation(request: Request, invitation_id: uuid.UUID, member: Member = Depends(require_role("admin")),
                      session: Session = Depends(get_db)):
    invitation = session.get(OrganizationInvitation, invitation_id)
    if invitation is None or invitation.organization_id != member.organization_id:
        raise NotFound
    session.delete(invitation)
    audit.record(session, member.organization_id, member.user_id, audit.INVITATION_CANCELLED,
                 f"invitation:{invitation_id}", request_id_for(request))
    session.commit()


def _scope_to_invitee(session: Session, user: User) -> tuple[uuid.UUID, str]:
    user_id, email = user.id, user.email.strip().lower()
    set_scope(session, user_id)
    set_invitee(session, email)
    return user_id, email


def _open_invitation(session: Session, email: str, invitation_id: uuid.UUID) -> OrganizationInvitation:
    """Someone else's invitation and an expired one look the same: not found."""
    invitation = session.scalar(select(OrganizationInvitation).where(
        OrganizationInvitation.id == invitation_id, OrganizationInvitation.email == email,
        OrganizationInvitation.expires_at > _now()))
    if invitation is None:
        raise NotFound
    return invitation


@router.get("/invitations")
def my_invitations(user: User = Depends(current_user), session: Session = Depends(get_db)):
    """Shows who sent each one, because organization names aren't verified and anyone can choose one."""
    _, email = _scope_to_invitee(session, user)
    rows = session.execute(
        select(OrganizationInvitation, Organization.name, User.email)
        .join(Organization, Organization.id == OrganizationInvitation.organization_id)
        .outerjoin(User, User.id == OrganizationInvitation.invited_by)
        .where(OrganizationInvitation.email == email, OrganizationInvitation.expires_at > _now())
        .order_by(OrganizationInvitation.expires_at))
    return [{"id": str(invitation.id), "organization_name": name, "invited_by": sender, "role": invitation.role,
             "expires_at": _utc(invitation.expires_at).isoformat()} for invitation, name, sender in rows]


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(request: Request, invitation_id: uuid.UUID, user: User = Depends(current_user),
                      session: Session = Depends(get_db)):
    """The role comes from the invitation, never from this request."""
    user_id, email = _scope_to_invitee(session, user)
    invitation = _open_invitation(session, email, invitation_id)
    organization_id, role = invitation.organization_id, invitation.role
    set_scope(session, user_id, organization_id)
    if session.get(OrganizationMember, (organization_id, user_id)) is None:
        session.add(OrganizationMember(organization_id=organization_id, user_id=user_id, role=role))
        audit.record(session, organization_id, user_id, audit.MEMBER_ADDED, f"member:{user_id}:{role}",
                     request_id_for(request))
    session.delete(invitation)
    try:
        session.commit()
    except IntegrityError:  # accepted twice at once, and the other request saved it
        session.rollback()
        raise NotFound
    return {"organization_id": str(organization_id), "role": role}


@router.post("/invitations/{invitation_id}/decline", status_code=204)
def decline_invitation(request: Request, invitation_id: uuid.UUID, user: User = Depends(current_user),
                       session: Session = Depends(get_db)):
    user_id, email = _scope_to_invitee(session, user)
    invitation = _open_invitation(session, email, invitation_id)
    organization_id = invitation.organization_id
    set_scope(session, user_id, organization_id)
    session.delete(invitation)
    audit.record(session, organization_id, user_id, audit.INVITATION_DECLINED, f"invitation:{invitation_id}",
                 request_id_for(request))
    session.commit()
