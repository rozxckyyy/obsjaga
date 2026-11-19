#!/bin/sh
set -eu

if [ "${1:-}" = "uvicorn" ]; then
    alembic upgrade head
    if [ "${SEED_DEMO:-false}" = "true" ]; then
        python -m app.seed
    fi
fi

exec "$@"
