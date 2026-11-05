"""Let each organization choose how long shipment records are kept

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('retention_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'retention_days')
