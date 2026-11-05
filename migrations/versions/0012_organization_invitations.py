"""Invitations to join an organization

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"
INVITEE_EMAIL = "NULLIF(current_setting('app.invitee_email', true), '')"


def upgrade() -> None:
    op.create_table(
        'organization_invitations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('invited_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('organization_id', 'email', name='uq_organization_invitations_tenant_email'),
        sa.CheckConstraint("role IN ('admin', 'supervisor', 'clerk')", name='ck_organization_invitations_role_allowed'),
    )
    op.create_index('ix_organization_invitations_email', 'organization_invitations', ['email'])
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON organization_invitations TO {APP_ROLE}")
    op.execute("ALTER TABLE organization_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_invitations FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON organization_invitations USING (organization_id = {CURRENT_ORG}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")
    # The person invited isn't a member yet, so they can read invitations to their own email, and nothing else.
    op.execute(f"CREATE POLICY invitee_can_read ON organization_invitations FOR SELECT USING (email = {INVITEE_EMAIL})")


def downgrade() -> None:
    op.drop_table('organization_invitations')
