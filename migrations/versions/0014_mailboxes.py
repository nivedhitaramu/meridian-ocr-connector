"""Mailboxes for email intake

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"
PRESENTED_TOKEN = "NULLIF(current_setting('app.mailbox_token', true), '')"


def upgrade() -> None:
    op.create_table(
        'mailboxes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(24), nullable=False),
        sa.Column('allowed_senders', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('organization_id', name='uq_mailboxes_organization_id'),
        sa.UniqueConstraint('token', name='uq_mailboxes_token'),
    )
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON mailboxes TO {APP_ROLE}")
    op.execute("ALTER TABLE mailboxes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mailboxes FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON mailboxes USING (organization_id = {CURRENT_ORG}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")
    # Incoming mail has no organization yet, so it can read the one mailbox its address names, and nothing else.
    op.execute(f"CREATE POLICY token_lookup ON mailboxes FOR SELECT USING (token = {PRESENTED_TOKEN})")


def downgrade() -> None:
    op.drop_table('mailboxes')
