"""Export the OpenAPI contract to docs/api/openapi.json; --check fails on drift (STD-API-008)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTRACT = Path("docs/api/openapi.json")


def render() -> str:
    from app.main import create_app

    schema = create_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    current = render()
    if not parser.parse_args().check:
        CONTRACT.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT.write_text(current, encoding="utf-8")
        print(f"OpenAPI contract written to {CONTRACT}")
        return 0
    committed = ""
    if CONTRACT.exists():
        committed = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")
    if committed != current:
        print("OpenAPI drift: run scripts/ci/export_openapi.py and commit", file=sys.stderr)
        return 1
    print("OpenAPI contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
