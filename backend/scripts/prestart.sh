#! /usr/bin/env bash

set -e
set -x

# Run migrations (as MIGRATION_DATABASE_URL / table owner)
alembic upgrade head

# Ensure the non-owner app role exists with DML grants (RLS applies to it)
python scripts/setup_db_roles.py

# Create initial data in DB (as the app role)
python app/initial_data.py
