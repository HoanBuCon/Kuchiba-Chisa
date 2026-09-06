"""Operator CLI regressions for the ING-01 canonical entry-point migration."""

from __future__ import annotations

import sys

import pytest

import chisa_cli


def test_direct_ingest_dispatches_only_to_canonical_dag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def record_run(
        source_id: str | None = None,
        staging_collection: str | None = None,
        download_limit: int | None = None,
    ) -> None:
        captured.update(
            source_id=source_id,
            staging_collection=staging_collection,
            download_limit=download_limit,
        )

    monkeypatch.setattr(chisa_cli, "run_ingestion_dag", record_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chisa_cli.py",
            "ingest",
            "--source-id",
            "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638",
            "--staging-collection",
            "character_lore__v20260906",
            "--download-limit",
            "5",
        ],
    )

    assert chisa_cli.handle_direct_cli_args() is True
    assert captured == {
        "source_id": "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638",
        "staging_collection": "character_lore__v20260906",
        "download_limit": 5,
    }


@pytest.mark.parametrize("legacy_command", ["scan", "crawl", "clean", "benchmark"])
def test_legacy_ingestion_modes_fail_closed(monkeypatch, legacy_command: str) -> None:
    monkeypatch.setattr(sys, "argv", ["chisa_cli.py", legacy_command])

    with pytest.raises(SystemExit, match="Legacy ingestion modes were removed"):
        chisa_cli.handle_direct_cli_args()
