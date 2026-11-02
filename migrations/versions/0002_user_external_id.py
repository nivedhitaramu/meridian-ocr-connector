"""Link users to their Clerk account

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No environment holds users yet, so the column can start as required.
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('external_id', sa.String(length=100), nullable=False))
        batch.create_unique_constraint(op.f('uq_users_external_id'), ['external_id'])


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint(op.f('uq_users_external_id'), type_='unique')
        batch.drop_column('external_id')
