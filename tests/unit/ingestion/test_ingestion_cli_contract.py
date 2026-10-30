"""The ingestion CLI exposes only the governed canonical DAG."""

import uuid

from click.testing import CliRunner

from app.application.ingestion.orchestrator import IngestionRunResult
from app.infrastructure.ingestion import cli as ingestion_cli
from app.infrastructure.ingestion.cli import cli

LEGACY_COMMANDS = (
    "scan-wiki",
    "crawl-wiki",
    "build-canonical",
    "process-chunks",
    "sync-qdrant",
    "cleanup-orphans",
    "run-pipeline",
)


def test_cli_help_lists_only_the_canonical_dag():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "run-dag" in result.output
    for legacy_command in LEGACY_COMMANDS:
        assert legacy_command not in result.output


def test_run_dag_reports_acknowledged_release(monkeypatch):
    async def acknowledged_run(request):
        assert str(request.source_id) == "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638"
        assert request.staging_collection == "world_lore__v20260906"
        return IngestionRunResult(
            job_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            release_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            downloaded_pages=1,
            parsed_pages=1,
            parent_documents=1,
            staged_chunks=1,
            acknowledged_vectors=1,
            parent_manifest_checksum="parent-checksum",
            vector_manifest_checksum="vector-checksum",
        )

    monkeypatch.setattr(ingestion_cli, "run_application_dag", acknowledged_run)
    result = CliRunner().invoke(
        cli,
        [
            "run-dag",
            "--source-id",
            "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638",
            "--staging-collection",
            "world_lore__v20260906",
        ],
    )

    assert result.exit_code == 0
    assert "[ACKNOWLEDGED]" in result.output
