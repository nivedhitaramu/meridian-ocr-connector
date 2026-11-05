"""Organizations, members and audit events."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import audit
from ..db.models import Organization, OrganizationMember, User
from ..db.session import get_db
from ..db.tenancy import set_scope
from .deps import Member, NotFound, current_member, current_user, request_id_for, require_role

router = APIRouter(prefix="/v1")


class NewOrganization(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RoleChange(BaseModel):
    role: Literal["admin", "supervisor", "clerk"]


@router.post("/organizations", status_code=201)
def create_organization(request: Request, body: NewOrganization, user: User = Depends(current_user),
                        session: Session = Depends(get_db)):
    """Anyone signed in can start an organization, and becomes its first admin."""
    organization_id, user_id = uuid.uuid4(), user.id
    session.rollback()  # the new organization and its admin go in one scoped transaction
    set_scope(session, user_id, organization_id)
    session.add(Organization(id=organization_id, name=body.name.strip()))
    session.flush()
    session.add(OrganizationMember(organization_id=organization_id, user_id=user_id, role="admin"))
    audit.record(session, organization_id, user_id, audit.ORGANIZATION_CREATED, f"organization:{organization_id}",
                 request_id_for(request))
    session.commit()
    return {"id": str(organization_id), "name": body.name.strip(), "role": "admin"}


@router.get("/organization")
def current_organization(member: Member = Depends(current_member), session: Session = Depends(get_db)):
    organization = session.get(Organization, member.organization_id)
    return {"id": str(organization.id), "name": organization.name, "plan": organization.plan, "role": member.role,
            "approval_steps": organization.approval_steps or ["supervisor"], "retention_days": organization.retention_days}


@router.patch("/organization")
def rename_organization(request: Request, body: NewOrganization, member: Member = Depends(require_role("admin")),
                        session: Session = Depends(get_db)):
    organization = session.get(Organization, member.organization_id)
    name = body.name.strip()
    if organization.name != name:
        organization.name = name
        audit.record(session, member.organization_id, member.user_id, audit.ORGANIZATION_RENAMED,
                     f"organization:{member.organization_id}", request_id_for(request))
        session.commit()
    return {"id": str(member.organization_id), "name": name}


def _is_last_admin(session: Session, member: Member, target: OrganizationMember) -> bool:
    if target.role != "admin":
        return False
    admins = session.scalar(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.organization_id == member.organization_id, OrganizationMember.role == "admin"))
    return admins == 1


_LAST_ADMIN = {"error": "An organization needs at least one admin."}


@router.get("/organization/members")
def list_members(member: Member = Depends(require_role("supervisor")), session: Session = Depends(get_db)):
    rows = session.execute(
        select(OrganizationMember, User.email).join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == member.organization_id)
    )
    return [{"user_id": str(m.user_id), "email": email, "role": m.role} for m, email in rows]


@router.patch("/organization/members/{user_id}")
def change_role(request: Request, user_id: uuid.UUID, body: RoleChange, member: Member = Depends(require_role("admin")),
                session: Session = Depends(get_db)):
    target = session.get(OrganizationMember, (member.organization_id, user_id))
    if target is None:
        raise NotFound
    if body.role != "admin" and _is_last_admin(session, member, target):
        return JSONResponse(status_code=409, content=_LAST_ADMIN)
    if target.role != body.role:
        target.role = body.role
        audit.record(session, member.organization_id, member.user_id, audit.MEMBER_ROLE_CHANGED,
                     f"member:{user_id}:{body.role}", request_id_for(request))
        session.commit()
    return {"user_id": str(user_id), "role": body.role}


@router.delete("/organization/members/{user_id}", status_code=204)
def remove_member(request: Request, user_id: uuid.UUID, member: Member = Depends(require_role("admin")),
                  session: Session = Depends(get_db)):
    target = session.get(OrganizationMember, (member.organization_id, user_id))
    if target is None:
        raise NotFound
    if _is_last_admin(session, member, target):
        return JSONResponse(status_code=409, content=_LAST_ADMIN)
    session.delete(target)
    audit.record(session, member.organization_id, member.user_id, audit.MEMBER_REMOVED,
                 f"member:{user_id}", request_id_for(request))
    try:
        session.commit()
    except IntegrityError:  # their past reviews must stay attributable
        session.rollback()
        return JSONResponse(status_code=409, content={"error": "This person has recorded reviews and can't be removed."})


@router.get("/audit-events")
def list_audit_events(limit: int = Query(50, ge=1, le=200), member: Member = Depends(require_role("admin")),
                      session: Session = Depends(get_db)):
    return [{"actor_id": str(e.actor_id) if e.actor_id else None, "action": e.action, "target": e.target,
             "request_id": e.request_id, "created_at": e.created_at.isoformat()}
            for e in audit.recent(session, member.organization_id, limit)]

