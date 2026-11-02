"""Clerk token checks and the protected route, using a locally generated signing key."""
import os
import time
import uuid

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.core import auth, config
from app.db import models
from app.db.session import get_db

ISSUER = "https://fictional-app.clerk.accounts.dev"
PAGE = "http://localhost:3000"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key=KEY, algorithm="RS256", **overrides):
    now = int(time.time())
    claims = {"sub": "user_abc", "iss": ISSUER, "iat": now - 5, "exp": now + 60, "azp": PAGE, "email": "clerk@example.com"}
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm=algorithm)


@pytest.fixture(autouse=True)
def clerk_settings(monkeypatch):
    monkeypatch.setattr(config, "CLERK_ISSUER", ISSUER)
    monkeypatch.setattr(config, "CLERK_AUTHORIZED_PARTIES", [PAGE])
    monkeypatch.setattr(auth, "_signing_key", lambda _: KEY.public_key())


@pytest.fixture
def client(tmp_path):
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'auth.db'}"
    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=args)
    make_session = sessionmaker(engine)

    def session_for_test():
        with make_session() as session:
            yield session

    main.app.dependency_overrides[get_db] = session_for_test
    yield TestClient(main.app), make_session
    main.app.dependency_overrides.clear()
    engine.dispose()
    command.downgrade(cfg, "base")


def me(client, value):
    return client.get("/v1/me", headers={"Authorization": f"Bearer {value}"})


def test_first_sign_in_creates_the_user_once(client):
    http, make_session = client
    first = me(http, token())
    second = me(http, token())
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["email"] == "clerk@example.com"
    assert first.json()["memberships"] == []
    with make_session() as session:
        assert session.query(models.User).count() == 1


def test_email_change_in_clerk_updates_the_user(client):
    http, _ = client
    me(http, token())
    assert me(http, token(email="new@example.com")).json()["email"] == "new@example.com"


def test_memberships_are_returned(client):
    http, make_session = client
    user_id = me(http, token()).json()["id"]
    with make_session() as session:
        org = models.Organization(name="Fictional Org")
        session.add(org)
        session.flush()
        session.add(models.OrganizationMember(organization_id=org.id, user_id=uuid.UUID(user_id), role="admin"))
        session.commit()
        org_id = str(org.id)
    assert me(http, token()).json()["memberships"] == [{"organization_id": org_id, "role": "admin"}]


@pytest.mark.parametrize("bad", [
    {"exp": 1},                                   # expired
    {"iss": "https://someone-else.example"},      # another Clerk app
    {"azp": "https://attacker.example"},          # requested by another site
    {"email": None},                              # no session token customization
    {"email": "not-an-email"},
    {"sub": None},
])
def test_bad_claims_are_refused(client, bad):
    response = me(client[0], token(**bad))
    assert response.status_code == 401
    assert response.json() == {"error": "Not signed in."}


def test_token_signed_by_another_key_is_refused(client):
    assert me(client[0], token(key=OTHER_KEY)).status_code == 401


def test_unsigned_token_is_refused(client):
    assert me(client[0], token(key=None, algorithm="none")).status_code == 401


def test_shared_secret_token_is_refused(client):
    assert me(client[0], token(key="x" * 40, algorithm="HS256")).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}])
def test_missing_token_is_refused(client, headers):
    response = client[0].get("/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_no_issuer_configured_refuses_everything(client, monkeypatch):
    monkeypatch.setattr(config, "CLERK_ISSUER", "")
    assert me(client[0], token()).status_code == 401


def test_extract_stays_open_without_a_token():
    # The assignment's endpoint is not a product route: it reaches the file check, not a 401.
    assert TestClient(main.app).post("/v1/extract", files={"file": ("x", b"junk")}).status_code == 415
