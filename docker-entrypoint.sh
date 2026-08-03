#!/usr/bin/env bash
set -e

echo "⏳ Waiting for Postgres…"
until python -c "import psycopg2, os; psycopg2.connect(os.environ['DATABASE_URL'].replace('+psycopg2',''))" 2>/dev/null; do
  sleep 1
done
echo "✅ Postgres is up"

# Create tables (first run) — uses create_all for the initial scaffold.
# Switch to `flask db upgrade` once Alembic migrations are generated.
flask --app wsgi db-create || true
flask --app wsgi seed || true

echo "🚀 Starting server on :8000"
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 60 wsgi:app
