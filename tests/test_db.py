"""Migrations and schema rules. Uses TEST_DATABASE_URL (PostgreSQL in CI), otherwise a temporary SQLite file."""
import os
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.db.models import Base

GLOBAL_TABLES = {"organizations", "users"}
FORBIDDEN_IN_COLUMN_NAME = ("filename", "file_name", "ocr_text", "raw_text", "masked_text", "completion",
                            "placeholder", "vault")


@pytest.fixture
def url(tmp_path):
    return os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def alembic_config(url):
    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url
    return cfg


@pytest.fixture
def engine(url, alembic_config):
    command.upgrade(alembic_config, "head")
    eng = create_engine(url)
    if eng.dialect.name == "sqlite":
        event.listen(eng, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    yield eng
    eng.dispose()
    command.downgrade(alembic_config, "base")


def test_migration_runs_up_and_down(url, alembic_config):
    command.upgrade(alembic_config, "head")
    eng = create_engine(url)
    assert set(Base.metadata.tables) <= set(inspect(eng).get_table_names())
    command.downgrade(alembic_config, "base")
    eng.dispose()
    eng = create_engine(url)
    assert not set(Base.metadata.tables) & set(inspect(eng).get_table_names())
    eng.dispose()


def test_migration_matches_the_models(engine):
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata) == []


@pytest.mark.parametrize("table", sorted(set(Base.metadata.tables) - GLOBAL_TABLES))
def test_every_tenant_table_has_organization_id(table):
    column = Base.metadata.tables[table].c.organization_id
    assert not column.nullable


def test_no_column_can_hold_document_content():
    for table in Base.metadata.tables.values():
        for column in table.c:
            assert not any(word in column.name for word in FORBIDDEN_IN_COLUMN_NAME), f"{table.name}.{column.name}"
            assert column.name == "prompt_version" or "prompt" not in column.name, f"{table.name}.{column.name}"


def _org(session):
    org = models.Organization(name="Fictional Org")
    session.add(org)
    session.flush()
    return org


def _shipment(session, org, reference="MF-1"):
    shipment = models.Shipment(organization_id=org.id, reference=reference)
    session.add(shipment)
    session.flush()
    return shipment


def test_document_cannot_point_at_another_tenants_shipment(engine):
    with Session(engine) as session:
        a, b = _org(session), _org(session)
        shipment = _shipment(session, a)
        session.add(models.Document(organization_id=b.id, shipment_id=shipment.id))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_reviewer_must_belong_to_the_organization(engine):
    with Session(engine) as session:
        a, b = _org(session), _org(session)
        user = models.User(email=f"{uuid.uuid4()}@example.com")
        session.add(user)
        session.flush()
        session.add(models.OrganizationMember(organization_id=b.id, user_id=user.id))
        job = models.ProcessingJob(organization_id=a.id, shipment_id=_shipment(session, a).id)
        session.add(job)
        session.flush()
        result = models.VerificationResult(organization_id=a.id, job_id=job.id, status="Match", reason="Equal.")
        session.add(result)
        session.flush()
        session.add(models.ReviewAction(organization_id=a.id, verification_result_id=result.id,
                                        reviewer_id=user.id, action="approve"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_only_the_four_statuses_are_allowed(engine):
    with Session(engine) as session:
        org = _org(session)
        job = models.ProcessingJob(organization_id=org.id, shipment_id=_shipment(session, org).id)
        session.add(job)
        session.flush()
        session.add(models.VerificationResult(organization_id=org.id, job_id=job.id, status="Probably", reason="No."))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_idempotency_key_is_unique_within_a_tenant_only(engine):
    with Session(engine) as session:
        a, b = _org(session), _org(session)
        s_a, s_b = _shipment(session, a), _shipment(session, b)
        session.add(models.ProcessingJob(organization_id=a.id, shipment_id=s_a.id, idempotency_key="key-1"))
        session.add(models.ProcessingJob(organization_id=b.id, shipment_id=s_b.id, idempotency_key="key-1"))
        session.flush()
        session.add(models.ProcessingJob(organization_id=a.id, shipment_id=s_a.id, idempotency_key="key-1"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_deleting_an_organization_removes_its_data(engine):
    with Session(engine) as session:
        org = _org(session)
        shipment = _shipment(session, org)
        session.add(models.Document(organization_id=org.id, shipment_id=shipment.id))
        session.commit()
        session.delete(org)
        session.commit()
        assert session.query(models.Document).count() == 0
        assert session.query(models.Shipment).count() == 0
