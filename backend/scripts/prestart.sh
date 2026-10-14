#! /usr/bin/env bash

set -e
set -x

# Run migrations (as MIGRATION_DATABASE_URL / table owner).
# D83: grants for the runtime role come from the migrations (0036); the role itself
# is created once by a DBA (scripts/setup_db_roles.py, never on shared environments).
alembic upgrade head

# Create initial data in DB (as the app role)
python -m app.initial_data
