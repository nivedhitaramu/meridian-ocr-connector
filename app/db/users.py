"""Link a signed-in Clerk identity to its row in the users table."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.auth import AuthError, Identity
from .models import OrganizationMember, User


def _find(session: Session, external_id: str) -> User | None:
    return session.scalar(select(User).where(User.external_id == external_id))


def user_for(session: Session, identity: Identity) -> User:
    """Create the row on first sign-in, and keep the email up to date after that."""
    user = _find(session, identity.external_id)
    try:
        if user is None:
            user = User(external_id=identity.external_id, email=identity.email)
            session.add(user)
        elif user.email != identity.email:
            user.email = identity.email
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Two first requests can race, so another request may have just created this user.
        user = _find(session, identity.external_id)
        if user is None:  # the email belongs to a different account
            raise AuthError("email_conflict") from exc
    return user


def memberships(session: Session, user: User) -> list[OrganizationMember]:
    return list(session.scalars(select(OrganizationMember).where(OrganizationMember.user_id == user.id)))
