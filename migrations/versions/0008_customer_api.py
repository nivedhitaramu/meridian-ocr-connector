"""API keys, webhook endpoints and webhook deliveries

Revision ID: 0008
Revises: 0007

An API key has to be found before its organization is known, so its policy also lets a caller read the
one row whose hash they present.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"
PRESENTED_KEY = "NULLIF(current_setting('app.api_key_hash', true), '')"
TABLES = ('api_keys', 'webhook_endpoints', 'webhook_deliveries')


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('prefix', sa.String(12), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('secret', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('endpoint_id', sa.Uuid(), sa.ForeignKey('webhook_endpoints.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.Uuid(), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('endpoint_id', 'job_id', name='uq_webhook_delivery_once'),
    )
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TABLES)} TO {APP_ROLE}")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON api_keys USING (organization_id = {CURRENT_ORG} OR key_hash = {PRESENTED_KEY}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")
    for table in TABLES[1:]:
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (organization_id = {CURRENT_ORG}) "
                   f"WITH CHECK (organization_id = {CURRENT_ORG})")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
