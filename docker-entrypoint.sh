#!/bin/sh
set -u

echo "Material Lab: preparing database migrations..."
if ! python -m app.migration_preflight; then
  echo "Material Lab: migration preflight failed; app startup stopped." >&2
  exit 1
fi

echo "Material Lab: applying database migrations..."
if ! alembic upgrade head; then
  echo "Material Lab: database migration failed; app startup stopped." >&2
  exit 1
fi
echo "Material Lab: database migrations complete."

exec "$@"
