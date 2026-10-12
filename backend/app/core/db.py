from sqlmodel import create_engine

from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
# Privileged engine (table owner) - only for migrations, tests setup, maintenance
admin_engine = create_engine(settings.migration_database_url, pool_pre_ping=True)
