"""Create / update the non-owner application DB role used by the running app.

Run with the privileged MIGRATION_DATABASE_URL (table owner), after migrations.
The role named in DATABASE_URL gets DML-only privileges: it is NOT the table owner,
NOT a superuser and has NOBYPASSRLS, so Postgres row level security applies to it.
"""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    app_url = make_url(str(settings.DATABASE_URL))
    admin = create_engine(settings.migration_database_url)
    role, pw = app_url.username, app_url.password
    if role == make_url(settings.migration_database_url).username:
        raise SystemExit(
            "DATABASE_URL must use a different (non-owner) role than MIGRATION_DATABASE_URL"
        )
    with admin.begin() as c:
        exists = c.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": role}
        ).first()
        verb = "ALTER" if exists else "CREATE"
        q = c.dialect.identifier_preparer.quote(role)
        c.execute(
            text(
                f"{verb} ROLE {q} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD "
                + c.execute(text("SELECT quote_literal(:p)"), {"p": pw}).scalar_one()
            )
        )
        c.execute(
            text(
                f"GRANT CONNECT ON DATABASE {c.dialect.identifier_preparer.quote(app_url.database)} TO {q}"
            )
        )
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {q}"))
        c.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {q}"
            )
        )
        c.execute(text(f"REVOKE ALL ON alembic_version FROM {q}"))
        c.execute(text(f"GRANT SELECT ON alembic_version TO {q}"))
        c.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {q}"
            )
        )
    logger.info("app DB role %r ready", role)


if __name__ == "__main__":
    main()
