"""Let each organization choose who must approve an exception

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('approval_steps', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'approval_steps')
