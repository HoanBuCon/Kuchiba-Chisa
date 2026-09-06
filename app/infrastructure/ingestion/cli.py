"""Single operator CLI for the canonical versioned ingestion DAG.

ING-01 deliberately exposes no file/SQLite/direct-Qdrant ingestion commands.
Every corpus build starts from an approved source identity and writes only to a
physical versioned staging collection. Publication remains an ING-02 action.
"""

from __future__ import annotations

import asyncio

import click
import httpx

from app.application.ingestion.orchestrator import (
    IngestionRunRequest,
    IngestionRunResult,
)
from app.config.settings import settings


@click.group(help="Kuchiba Chisa canonical ingestion DAG")
def cli() -> None:
    """Expose only governed canonical ingestion entry points."""


@cli.command("run-dag", help="Build one governed, versioned staging corpus.")
@click.option(
    "--staging-collection",
    required=True,
    help=(
        "Physical character_lore, world_lore, or story_lore version; active "
        "aliases are never accepted."
    ),
)
@click.option(
    "--source-id",
    required=True,
    help="Approved ingestion source UUID from the curator registry.",
)
@click.option(
    "--download-limit",
    type=click.IntRange(min=1, max=10_000),
    default=None,
    help="Optional bounded source-page count for this run.",
)
def run_dag_cmd(
    source_id: str,
    staging_collection: str,
    download_limit: int | None,
) -> None:
    """Run the canonical DAG; never provision, delete, or promote an alias."""

    try:
        request = IngestionRunRequest(
            staging_collection=staging_collection,
            source_id=source_id,
            download_limit=download_limit,
        )
        result = asyncio.run(run_application_dag(request))
    except Exception as exc:
        raise click.ClickException(
            f"ingestion DAG failed: {type(exc).__name__}"
        ) from exc
    click.echo(
        "[ACKNOWLEDGED] "
        f"job={result.job_id} pages={result.downloaded_pages} "
        f"parents={result.parent_documents} vectors={result.acknowledged_vectors} "
        f"parent_manifest={result.parent_manifest_checksum} "
        f"vector_manifest={result.vector_manifest_checksum}"
    )


async def run_application_dag(request: IngestionRunRequest) -> IngestionRunResult:
    """Compose request-scoped adapters and execute one bounded canonical run."""

    from app.application.dependencies import container
    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.infrastructure.ingestion.application_factory import (
        build_ingestion_orchestrator,
    )

    async with (
        httpx.AsyncClient(
            timeout=settings.INGESTION_SOURCE_TIMEOUT_SECONDS
        ) as http_client,
        AsyncSessionFactory() as session,
    ):
        orchestrator = await build_ingestion_orchestrator(
            session=session,
            http_client=http_client,
            embedder=container.embedder,
            vector_store=container.vector_store,
            settings=settings,
            request=request,
        )
        return await orchestrator.run(request)


if __name__ == "__main__":
    cli()
