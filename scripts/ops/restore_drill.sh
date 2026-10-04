#!/usr/bin/env bash
# Non-destructive restore drill: restores a PostgreSQL dump into a scratch database
# (chisa_restore_drill), compares row counts with production, then drops it.
# Usage: scripts/ops/restore_drill.sh /var/backups/chisa/<STAMP>
set -euo pipefail

SOURCE="${1:?usage: restore_drill.sh <backup directory>}"
COMPOSE="${COMPOSE:-docker compose}"
DRILL_DB="chisa_restore_drill"

(cd "${SOURCE}" && sha256sum -c SHA256SUMS)

${COMPOSE} exec -T postgres dropdb -U chisa --if-exists "${DRILL_DB}"
${COMPOSE} exec -T postgres createdb -U chisa "${DRILL_DB}"
${COMPOSE} exec -T postgres pg_restore -U chisa -d "${DRILL_DB}" --no-owner --exit-on-error \
  < "${SOURCE}/postgres.dump"

QUERY="SELECT (SELECT version_num FROM alembic_version) AS revision,
              (SELECT count(*) FROM users) AS users,
              (SELECT count(*) FROM accounts) AS accounts,
              (SELECT count(*) FROM messages) AS messages;"
echo "[drill] restored:";   ${COMPOSE} exec -T postgres psql -U chisa -d "${DRILL_DB}" -c "${QUERY}"
echo "[drill] production:"; ${COMPOSE} exec -T postgres psql -U chisa -d chisa_db -c "${QUERY}"

# Plain commands (not `a && b`) so `set -e` aborts the drill on a bad artefact.
tar -tzf "${SOURCE}/uploads.tar.gz" > /dev/null
echo "[drill] uploads archive readable"
test -s "${SOURCE}/qdrant.snapshot"
echo "[drill] qdrant snapshot present ($(stat -c %s "${SOURCE}/qdrant.snapshot") bytes)"

${COMPOSE} exec -T postgres dropdb -U chisa "${DRILL_DB}"
echo "[drill] OK — counts above should match the backup time; scratch database dropped."
