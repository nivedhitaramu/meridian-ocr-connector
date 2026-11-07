"""Usage records for metering and plan limits

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        'usage_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.Uuid(), sa.ForeignKey('processing_jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('documents', sa.Integer(), nullable=False),
        sa.Column('model_calls', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('job_id', name='uq_usage_records_job_id'),
    )
    op.create_index('ix_usage_records_tenant_created', 'usage_records', ['organization_id', 'created_at'])
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON usage_records TO {APP_ROLE}")
    op.execute("ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON usage_records USING (organization_id = {CURRENT_ORG}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")


def downgrade() -> None:
    op.drop_table('usage_records')
