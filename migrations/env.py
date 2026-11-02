"""Alembic environment. Uses DATABASE_URL unless a test passes its own URL."""
from alembic import context
from sqlalchemy import create_engine

from app.core import config as app_config
from app.db.models import Base

url = context.config.attributes.get("url") or app_config.DATABASE_URL
if not url:
    raise RuntimeError("DATABASE_URL is not set")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
