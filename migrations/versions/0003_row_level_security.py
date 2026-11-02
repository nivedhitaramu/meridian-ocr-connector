"""Add row-level security to tenant tables

Revision ID: 0003
Revises: 0002

Superusers skip row-level security, and the database user in docker-compose.yml is one. So signed-in
requests switch to this restricted role: see app/db/tenancy.py. PostgreSQL only.
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

APP_ROLE = 'meridian_app'
ALL_TABLES = ('organizations', 'users', 'organization_members', 'shipments', 'documents', 'processing_jobs',
              'extraction_results', 'verification_results', 'review_actions', 'audit_events')
TENANT_TABLES = ('shipments', 'documents', 'processing_jobs', 'extraction_results', 'verification_results',
                 'review_actions', 'audit_events')
CURRENT_ORG = "NULLIF(current_setting('app.current_organization', true), '')::uuid"
CURRENT_USER = "NULLIF(current_setting('app.current_user', true), '')::uuid"


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$
    """)
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(ALL_TABLES)} TO {APP_ROLE}")
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} "
                   f"USING (organization_id = {CURRENT_ORG}) WITH CHECK (organization_id = {CURRENT_ORG})")
    # People can see their own memberships before choosing an organization, but only change the current one.
    op.execute("ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_members FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON organization_members "
               f"USING (organization_id = {CURRENT_ORG} OR user_id = {CURRENT_USER}) "
               f"WITH CHECK (organization_id = {CURRENT_ORG})")


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table in ('organization_members',) + TENANT_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON {', '.join(ALL_TABLES)} FROM {APP_ROLE}")
