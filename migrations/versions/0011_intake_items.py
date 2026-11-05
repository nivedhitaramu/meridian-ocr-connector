"""Documents uploaded in a batch, waiting to be grouped into shipments

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        'intake_items',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_id', sa.Uuid(), nullable=False),
        sa.Column('storage_key', sa.String(200), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=True),
        sa.Column('reference', sa.String(100), nullable=True),
        sa.Column('reason', sa.String(40), nullable=True),
        sa.Column('shipment_id', sa.Uuid(), sa.ForeignKey('shipments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_intake_items_batch', 'intake_items', ['batch_id'])
    op.create_index('ix_intake_items_tenant_status', 'intake_items', ['organization_id', 'status'])
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON intake_items TO {APP_ROLE}")
    op.execute("ALTER TABLE intake_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE intake_items FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON intake_items USING (organization_id = {CURRENT_ORG}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")


def downgrade() -> None:
    op.drop_table('intake_items')
