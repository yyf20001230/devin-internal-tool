#!/bin/sh
# Seed the SQLite database on first boot (persistent volume is empty), then serve.
# Set SEED=always to rebuild the demo data on every start, SEED=never to skip.
set -e
: "${DB_PATH:=/data/data.db}"
: "${SEED:=auto}"
if [ "$SEED" = "always" ] || { [ "$SEED" = "auto" ] && [ ! -s "$DB_PATH" ]; }; then
  echo "seeding $DB_PATH"
  python -m server.seed
fi
exec python -m uvicorn server.main:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
