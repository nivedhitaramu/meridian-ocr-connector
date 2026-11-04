"""Tie a database session to one signed-in user and, once chosen, one organization.

On PostgreSQL each transaction switches to a restricted role and sets the values that the row-level
security policies read, so a missed filter in a query still can't return another tenant's rows.
"""
from __future__ import annotations

import uuid

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


def set_scope(session: Session, user_id: uuid.UUID | None, organization_id: uuid.UUID | None = None) -> None:
    """A background job has no signed-in user, so it passes None and acts within one organization."""
    session.info["scope"] = (str(user_id) if user_id else "", str(organization_id) if organization_id else "")
    _apply(session, session.connection())  # also covers a transaction that's already open


def _apply(session: Session, connection: Connection) -> None:
    scope = session.info.get("scope")
    if scope is None or connection.dialect.name != "postgresql":
        return
    connection.execute(text("SET LOCAL ROLE meridian_app"))
    connection.execute(text("SELECT set_config('app.current_user', :user, true), "
                            "set_config('app.current_organization', :organization, true)"),
                       {"user": scope[0], "organization": scope[1]})


@event.listens_for(Session, "after_begin")
def _scope_new_transaction(session: Session, transaction, connection: Connection) -> None:
    _apply(session, connection)
