#!/usr/bin/env bash
# Run a one-off Python command in the app image with the same secret-derived
# environment as the `app` service (DATABASE_URL, REDIS_PASSWORD). A plain
# `docker compose run app python ...` replaces the service command that exports
# them, so production Settings validation would refuse to start.
#
#   scripts/ops/app_python.sh -m app.ops.bootstrap_private_collections
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose}"

# shellcheck disable=SC2016  # expanded inside the container, not here
exec ${COMPOSE} run --rm -T app /bin/sh -ec '
export DATABASE_URL="$(python -c "from pathlib import Path; from urllib.parse import quote; print(\"postgresql+asyncpg://chisa:\" + quote(Path(\"/run/secrets/postgres_password\").read_text().strip(), safe=\"\") + \"@postgres:5432/chisa_db\")")"
export REDIS_PASSWORD="$(cat /run/secrets/redis_password)"
exec python "$@"' sh "$@"
