#!/usr/bin/env bash
# Minimum viable Chisa backup (run from the repository root on the VPS, e.g. daily cron):
#   PostgreSQL logical dump, full Qdrant snapshot, uploaded image files.
# Optional offsite copy with rclone when BACKUP_RCLONE_REMOTE is set
# (use an rclone "crypt" remote so backups are encrypted at rest offsite).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/chisa}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${STAMP}"
COMPOSE="${COMPOSE:-docker compose}"

umask 077
mkdir -p "${TARGET}"

echo "[backup] postgres → ${TARGET}/postgres.dump"
${COMPOSE} exec -T postgres pg_dump -U chisa -d chisa_db -Fc > "${TARGET}/postgres.dump"

echo "[backup] qdrant → ${TARGET}/qdrant.snapshot"
${COMPOSE} exec -T app python -m app.ops.qdrant_snapshot > "${TARGET}/qdrant.snapshot"

echo "[backup] uploads → ${TARGET}/uploads.tar.gz"
${COMPOSE} exec -T app tar -C /app/app/static -czf - uploads > "${TARGET}/uploads.tar.gz"

# Integrity: every artefact must be non-empty and the dump must be readable.
for f in postgres.dump qdrant.snapshot uploads.tar.gz; do
  [ -s "${TARGET}/${f}" ] || { echo "[backup] ERROR: ${f} is empty" >&2; exit 1; }
done
${COMPOSE} exec -T postgres pg_restore --list < "${TARGET}/postgres.dump" > /dev/null
(cd "${TARGET}" && sha256sum postgres.dump qdrant.snapshot uploads.tar.gz > SHA256SUMS)

if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  echo "[backup] offsite → ${BACKUP_RCLONE_REMOTE}/${STAMP}"
  rclone copy "${TARGET}" "${BACKUP_RCLONE_REMOTE}/${STAMP}"
fi

find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} +
echo "[backup] OK ${TARGET}"
