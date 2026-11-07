"""Payload format per webhook endpoint, for connectors

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('webhook_endpoints') as batch:
        batch.add_column(sa.Column('format', sa.String(30), nullable=False, server_default='event'))


def downgrade() -> None:
    with op.batch_alter_table('webhook_endpoints') as batch:
        batch.drop_column('format')
