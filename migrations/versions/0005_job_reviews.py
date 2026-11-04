"""Tie reviews to jobs, so manual review cases can be reviewed too

Revision ID: 0005
Revises: 0004

A manual review case has no verification result, so reviews now point at the job. No environment holds
review rows yet, so the columns can start as required.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('review_actions') as batch:
        batch.drop_constraint('fk_review_actions_tenant_result', type_='foreignkey')
        batch.drop_index('ix_review_actions_result')
        batch.drop_column('verification_result_id')
        batch.add_column(sa.Column('job_id', sa.Uuid(), nullable=False))
        batch.add_column(sa.Column('reason', sa.String(length=300), nullable=False))
        batch.add_column(sa.Column('correction', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True))
        batch.create_foreign_key('fk_review_actions_tenant_job', 'processing_jobs', ['organization_id', 'job_id'],
                                 ['organization_id', 'id'], ondelete='CASCADE')
        batch.create_index('ix_review_actions_job', ['job_id'])


def downgrade() -> None:
    op.execute('DELETE FROM review_actions')  # they point at jobs, which the old column can't express
    with op.batch_alter_table('review_actions') as batch:
        batch.drop_index('ix_review_actions_job')
        batch.drop_constraint('fk_review_actions_tenant_job', type_='foreignkey')
        batch.drop_column('correction')
        batch.drop_column('reason')
        batch.drop_column('job_id')
        batch.add_column(sa.Column('verification_result_id', sa.Uuid(), nullable=False))
        batch.create_foreign_key('fk_review_actions_tenant_result', 'verification_results',
                                 ['organization_id', 'verification_result_id'], ['organization_id', 'id'], ondelete='CASCADE')
        batch.create_index('ix_review_actions_result', ['verification_result_id'])
