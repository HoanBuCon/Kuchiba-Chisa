#!/usr/bin/env bash
# Minimum viable production monitoring for a single VPS (run every 5 minutes by cron).
# Checks container state/restarts, API readiness, disk and RAM, and posts to a
# dedicated Discord webhook only when the alert state changes (no alert storms).
#
#   */5 * * * * cd /opt/chisa && DISCORD_ALERT_WEBHOOK_URL=... scripts/ops/monitor.sh
#
# External uptime: additionally point a free uptime monitor at https://<domain>/ready.
set -uo pipefail

WEBHOOK="${DISCORD_ALERT_WEBHOOK_URL:?set DISCORD_ALERT_WEBHOOK_URL (dedicated alerts channel)}"
STATE_DIR="${MONITOR_STATE_DIR:-/var/lib/chisa-monitor}"
DISK_LIMIT="${MONITOR_DISK_PERCENT:-80}"
MEM_MIN_PERCENT="${MONITOR_MEM_AVAILABLE_PERCENT:-10}"
SERVICES="${MONITOR_SERVICES:-postgres redis qdrant app worker discord web}"
mkdir -p "${STATE_DIR}"

problems=()

for service in ${SERVICES}; do
  cid="$(docker compose ps -q "${service}" 2>/dev/null)"
  if [ -z "${cid}" ]; then problems+=("${service}: not created"); continue; fi
  state="$(docker inspect -f '{{.State.Status}}' "${cid}")"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${cid}")"
  restarts="$(docker inspect -f '{{.RestartCount}}' "${cid}")"
  [ "${state}" = "running" ] || problems+=("${service}: ${state}")
  [ "${health}" = "unhealthy" ] && problems+=("${service}: unhealthy")
  last_file="${STATE_DIR}/${service}.restarts"
  last="$(cat "${last_file}" 2>/dev/null || echo "${restarts}")"
  [ "${restarts}" -gt "${last}" ] && problems+=("${service}: restarted $((restarts - last))x")
  echo "${restarts}" > "${last_file}"
done

ready_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/ready)"
[ "${ready_code}" = "200" ] || problems+=("api /ready: HTTP ${ready_code}")

disk_used="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
[ "${disk_used}" -ge "${DISK_LIMIT}" ] && problems+=("disk: ${disk_used}% used")

mem_total="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
mem_avail="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
mem_pct=$((mem_avail * 100 / mem_total))
[ "${mem_pct}" -lt "${MEM_MIN_PERCENT}" ] && problems+=("memory: only ${mem_pct}% available")

swap_used_kb="$(awk '/SwapTotal/ {t=$2} /SwapFree/ {f=$2} END {print t-f}' /proc/meminfo)"
[ "${swap_used_kb}" -gt 1048576 ] && problems+=("swap: $((swap_used_kb / 1024)) MB in use")

if [ "${#problems[@]}" -eq 0 ]; then summary="OK"; else summary="$(printf '%s; ' "${problems[@]}")"; fi
previous="$(cat "${STATE_DIR}/last_summary" 2>/dev/null || echo "OK")"

if [ "${summary}" != "${previous}" ]; then
  if [ "${summary}" = "OK" ]; then text="✅ Chisa recovered on $(hostname)"; else text="🚨 Chisa alert on $(hostname): ${summary}"; fi
  payload="$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1][:1900]}))' "${text}")"
  curl -s -o /dev/null --max-time 10 -H 'content-type: application/json' -d "${payload}" "${WEBHOOK}" \
    && echo "${summary}" > "${STATE_DIR}/last_summary"
fi
echo "${summary}"
