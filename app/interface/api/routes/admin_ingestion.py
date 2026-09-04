"""RBAC-protected curator APIs for governed ingestion sources."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ingestion.source_governance import (
    IngestionSourceGovernanceService,
    IngestionSourceNotFoundError,
)
from app.application.ingestion.corpus_release_lifecycle import (
    CorpusReleaseConsistencyError,
    CorpusReleaseLifecycleService,
    CorpusReleaseNotFoundError,
)
from app.application.security.authorization import AuthorizationError
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.database.repositories.ingestion_source import (
    IngestionSourceAuditRepository,
    IngestionSourceRepository,
)
from app.infrastructure.database.repositories.corpus_release import CorpusReleaseRepository
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.interface.api.dependencies.security import CurrentPrincipal
from app.interface.api.schemas.ingestion import (
    CorpusQualityReportResponse,
    CorpusReleaseResponse,
    SourceRegistrationRequest,
    SourceResponse,
)

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])


def get_source_governance_service(
    session: AsyncSession = Depends(get_db_session),
) -> IngestionSourceGovernanceService:
    """Compose source governance ports within the request transaction."""
    return IngestionSourceGovernanceService(
        source_repository=IngestionSourceRepository(session),
        audit_repository=IngestionSourceAuditRepository(session),
    )


def get_corpus_release_lifecycle_service(
    session: AsyncSession = Depends(get_db_session),
) -> CorpusReleaseLifecycleService:
    """Compose the quality-gated corpus publisher inside the admin request boundary."""
    return CorpusReleaseLifecycleService(
        release_repository=CorpusReleaseRepository(session),
        source_repository=IngestionSourceRepository(session),
        parent_repository=LoreParentRepository(session),
        publisher=qdrant_service,
    )


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def register_source(
    request: SourceRegistrationRequest,
    principal: CurrentPrincipal,
    service: Annotated[IngestionSourceGovernanceService, Depends(get_source_governance_service)],
) -> SourceResponse:
    """Register a source into quarantine under a verified curator identity."""
    try:
        source = await service.register(principal, request.to_command())
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    return SourceResponse.from_source(source)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[IngestionSourceGovernanceService, Depends(get_source_governance_service)],
) -> SourceResponse:
    """Read a source only when the verified curator owns it or has elevated scope."""
    try:
        source = await service.get(principal, source_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except IngestionSourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error
    return SourceResponse.from_source(source)


@router.post("/sources/{source_id}/approve", response_model=SourceResponse)
async def approve_source(
    source_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[IngestionSourceGovernanceService, Depends(get_source_governance_service)],
) -> SourceResponse:
    """Approve a reviewed source and persist its status transition audit record."""
    try:
        source = await service.approve(principal, source_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except IngestionSourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid source transition") from error
    return SourceResponse.from_source(source)


@router.get("/releases/{release_id}", response_model=CorpusReleaseResponse)
async def get_release(
    release_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[
        CorpusReleaseLifecycleService, Depends(get_corpus_release_lifecycle_service)
    ],
) -> CorpusReleaseResponse:
    """Read release metadata only after verified curator/source authorization."""
    try:
        release = await service.get(principal, release_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except CorpusReleaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found") from error
    return CorpusReleaseResponse.from_release(release)


@router.get(
    "/releases/{release_id}/quality",
    response_model=CorpusQualityReportResponse | None,
)
async def get_release_quality(
    release_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[
        CorpusReleaseLifecycleService, Depends(get_corpus_release_lifecycle_service)
    ],
) -> CorpusQualityReportResponse | None:
    """Return aggregate quality metrics without exposing evaluation corpus or generated text."""
    try:
        report = await service.get_quality_report(principal, release_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except CorpusReleaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found") from error
    return CorpusQualityReportResponse.from_report(report) if report is not None else None


@router.post("/releases/{release_id}/publish", response_model=CorpusReleaseResponse)
async def publish_release(
    release_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[
        CorpusReleaseLifecycleService, Depends(get_corpus_release_lifecycle_service)
    ],
) -> CorpusReleaseResponse:
    """Publish only a persisted, quality-passed release through an atomic alias swap."""
    try:
        release = await service.publish(principal, release_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except CorpusReleaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found") from error
    except CorpusReleaseConsistencyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Release cannot publish") from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Release publication is temporarily unavailable",
        ) from error
    return CorpusReleaseResponse.from_release(release)


@router.post("/releases/{release_id}/reconcile", response_model=CorpusReleaseResponse)
async def reconcile_release(
    release_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[
        CorpusReleaseLifecycleService, Depends(get_corpus_release_lifecycle_service)
    ],
) -> CorpusReleaseResponse:
    """Reconcile a committed promotion intent after an interrupted external alias operation."""
    try:
        release = await service.reconcile(principal, release_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except CorpusReleaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found") from error
    except CorpusReleaseConsistencyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Release cannot reconcile") from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Release reconciliation is temporarily unavailable",
        ) from error
    return CorpusReleaseResponse.from_release(release)


@router.post("/releases/{release_id}/rollback", response_model=CorpusReleaseResponse)
async def rollback_release(
    release_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[
        CorpusReleaseLifecycleService, Depends(get_corpus_release_lifecycle_service)
    ],
) -> CorpusReleaseResponse:
    """Rollback in one alias operation to a retained, independently verified receipt."""
    try:
        release = await service.rollback(principal, release_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from error
    except CorpusReleaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found") from error
    except CorpusReleaseConsistencyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Release cannot roll back") from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Release rollback is temporarily unavailable",
        ) from error
    return CorpusReleaseResponse.from_release(release)
