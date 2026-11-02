"""Make audit events append-only for signed-in requests

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("REVOKE UPDATE, DELETE ON audit_events FROM meridian_app")


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("GRANT UPDATE, DELETE ON audit_events TO meridian_app")
