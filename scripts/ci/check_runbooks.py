"""Fail when an alert has no runbook or a runbook has no alert (STD-OBS-004, MON-030)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CATALOG = Path("docs/monitoring/alerts.yaml")
RUNBOOKS = Path("docs/runbooks")


def main() -> int:
    catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    alerts = {alert["id"] for alert in catalog["alerts"]}
    runbooks = {path.stem for path in RUNBOOKS.glob("*.md")}
    missing, orphaned = sorted(alerts - runbooks), sorted(runbooks - alerts)
    for alert_id in missing:
        print(f"Alert without runbook: {alert_id}", file=sys.stderr)
    for runbook in orphaned:
        print(f"Runbook without alert: {runbook}", file=sys.stderr)
    failed = bool(missing or orphaned)
    print(f"Runbooks: {'FAIL' if failed else 'PASS'} ({len(alerts)} alerts)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
