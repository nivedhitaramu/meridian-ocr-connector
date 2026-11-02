"""Verify Clerk session tokens. Clerk handles sign-up, sign-in, sign-out and password reset.

Every failure raises the same AuthError, and tokens are never logged.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt

from . import config


class AuthError(Exception):
    """The request isn't signed in. The client only ever sees a generic message."""


@dataclass(frozen=True)
class Identity:
    external_id: str
    email: str
    session_id: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{config.CLERK_ISSUER}/.well-known/jwks.json", cache_keys=True)


def _signing_key(token: str):
    return _jwks_client().get_signing_key_from_jwt(token).key


def verify_token(token: str) -> Identity:
    if not config.CLERK_ISSUER:  # fail closed: without an issuer, no token can be trusted
        raise AuthError("auth_not_configured")
    try:
        claims = jwt.decode(
            token, _signing_key(token), algorithms=["RS256"], issuer=config.CLERK_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"], "verify_aud": False},
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthError("token_invalid") from exc

    # Clerk tokens name the site that requested them. Only accept our own pages.
    party = claims.get("azp")
    if party is not None and party not in config.CLERK_AUTHORIZED_PARTIES:
        raise AuthError("token_wrong_party")
    email = claims.get("email")  # needs the session token customization in the README
    if not isinstance(email, str) or "@" not in email:
        raise AuthError("token_no_email")
    session_id = claims.get("sid")
    return Identity(external_id=claims["sub"], email=email, session_id=session_id if isinstance(session_id, str) else None)


def bearer_token(header: str | None) -> str:
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("token_missing")
    return token.strip()
