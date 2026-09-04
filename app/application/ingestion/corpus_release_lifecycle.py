"""Application lifecycle for quality-gated, auditable corpus publication."""

from __future__ import annotations

import uuid

from app.application.ingestion.source_governance import IngestionSourceNotFoundError
from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.interfaces.corpus_publisher import ICorpusPublisher
from app.domain.interfaces.repositories import (
    ICorpusReleaseRepository,
    IIngestionSourceRepository,
    ILoreParentRepository,
)
from app.domain.models.corpus_release import (
    CorpusQualityReport,
    CorpusRelease,
    CorpusReleaseAuditAction,
    CorpusReleaseAuditEvent,
    CorpusReleaseStatus,
)
from app.domain.value_objects.principal import PrincipalContext

_QUALITY_EVALUATOR_ACTOR_ID = "service:corpus-evaluator"
_READ_SCOPE = "ingestion:release:read"
_READ_ANY_SCOPE = "ingestion:release:read:any"
_PUBLISH_SCOPE = "ingestion:release:publish"
_PUBLISH_ANY_SCOPE = "ingestion:release:publish:any"
_ROLLBACK_SCOPE = "ingestion:release:rollback"
_ROLLBACK_ANY_SCOPE = "ingestion:release:rollback:any"


class CorpusReleaseNotFoundError(LookupError):
    """The requested release receipt does not exist."""


class CorpusReleaseConsistencyError(RuntimeError):
    """A durable receipt disagrees with staging state and must never be promoted."""


class CorpusReleaseLifecycleService:
    """Keep RBAC, manifest verification, external mutation, and audit in one use case."""

    def __init__(
        self,
        *,
        release_repository: ICorpusReleaseRepository,
        source_repository: IIngestionSourceRepository,
        parent_repository: ILoreParentRepository,
        publisher: ICorpusPublisher,
    ) -> None:
        self._release_repository = release_repository
        self._source_repository = source_repository
        self._parent_repository = parent_repository
        self._publisher = publisher

    async def record_quality_report(self, report: CorpusQualityReport) -> CorpusRelease:
        """Persist an internally-produced evaluator receipt and gate promotion on it.

        This method deliberately has no HTTP schema. Curator transport code cannot
        submit caller-controlled metrics to bypass the release gate. A failed
        evaluation remains a staged release so it can be corrected and re-run, but
        its aggregate metrics and an immutable failure audit event are retained.
        """
        release = await self._get_release(report.release_id)
        if release.status is not CorpusReleaseStatus.STAGED:
            raise CorpusReleaseConsistencyError(
                "quality reports can only be recorded for staged releases"
            )

        existing_report = await self._release_repository.get_quality_report(release.release_id)
        if existing_report is not None:
            # The persistence model intentionally has one current aggregate report
            # per release. Preserve its primary key when a failed staging evaluation
            # is re-run rather than relying on a unique-constraint error.
            report = report.model_copy(update={"report_id": existing_report.report_id})

        await self._release_repository.save_quality_report(report)
        if report.passes_release_gate:
            resulting_release = release.mark_quality_passed(report)
            action = CorpusReleaseAuditAction.QUALITY_PASSED
        else:
            resulting_release = release
            action = CorpusReleaseAuditAction.FAILED

        await self._release_repository.save_release(resulting_release)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=_QUALITY_EVALUATOR_ACTOR_ID,
                action=action,
                old_status=release.status,
                new_status=resulting_release.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=resulting_release.corpus_version,
            )
        )
        await self._release_repository.commit()
        return resulting_release

    async def get(self, principal: PrincipalContext, release_id: uuid.UUID) -> CorpusRelease:
        """Return non-content release metadata to the source owner or elevated curator."""
        return await self._authorized_release(
            principal,
            release_id,
            own_scope=_READ_SCOPE,
            elevated_scope=_READ_ANY_SCOPE,
        )

    async def get_quality_report(
        self, principal: PrincipalContext, release_id: uuid.UUID
    ) -> CorpusQualityReport | None:
        """Expose aggregate evaluation metrics only after the same source authorization."""
        await self.get(principal, release_id)
        return await self._release_repository.get_quality_report(release_id)

    async def publish(self, principal: PrincipalContext, release_id: uuid.UUID) -> CorpusRelease:
        """Atomically activate a fully verified staged corpus and persist its audit receipt."""
        release = await self._authorized_release(
            principal,
            release_id,
            own_scope=_PUBLISH_SCOPE,
            elevated_scope=_PUBLISH_ANY_SCOPE,
        )
        if release.status is not CorpusReleaseStatus.QUALITY_PASSED:
            raise CorpusReleaseConsistencyError("release has not passed the quality gate")
        report = await self._release_repository.get_quality_report(release_id)
        if report is None or not report.passes_release_gate:
            raise CorpusReleaseConsistencyError("release has no valid persisted quality receipt")
        await self._require_parent_manifest(release)
        previous_active_collection = await self._publisher.active_target(
            release.logical_collection.value
        )
        if previous_active_collection is None:
            raise CorpusReleaseConsistencyError("release has no retained active rollback target")
        promotion_requested = release.mark_promotion_requested(
            previous_active_collection=previous_active_collection
        )
        await self._release_repository.save_release(promotion_requested)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=principal.subject_id,
                action=CorpusReleaseAuditAction.PROMOTION_REQUESTED,
                old_status=release.status,
                new_status=promotion_requested.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=release.corpus_version,
            )
        )
        await self._release_repository.commit()

        publication = await self._publisher.promote(promotion_requested)
        if publication.previous_active_collection != previous_active_collection:
            raise CorpusReleaseConsistencyError("active alias changed during promotion request")
        published = promotion_requested.mark_published(
            previous_active_collection=previous_active_collection
        )
        await self._release_repository.save_release(published)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=principal.subject_id,
                action=CorpusReleaseAuditAction.PUBLISHED,
                old_status=release.status,
                new_status=published.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=published.corpus_version,
            )
        )
        await self._release_repository.commit()
        return published

    async def reconcile(self, principal: PrincipalContext, release_id: uuid.UUID) -> CorpusRelease:
        """Resolve an interrupted publish or rollback from durable intent and live alias state."""
        initial = await self._get_release(release_id)
        if initial.status is CorpusReleaseStatus.ROLLBACK_REQUESTED:
            release = await self._authorized_release(
                principal,
                release_id,
                own_scope=_ROLLBACK_SCOPE,
                elevated_scope=_ROLLBACK_ANY_SCOPE,
            )
        else:
            release = await self._authorized_release(
                principal,
                release_id,
                own_scope=_PUBLISH_SCOPE,
                elevated_scope=_PUBLISH_ANY_SCOPE,
            )
        if release.status not in {
            CorpusReleaseStatus.PROMOTION_REQUESTED,
            CorpusReleaseStatus.ROLLBACK_REQUESTED,
        }:
            return release
        if release.previous_active_collection is None:
            raise CorpusReleaseConsistencyError("promotion request has no rollback target")
        active_target = await self._publisher.active_target(release.logical_collection.value)
        if (
            release.status is CorpusReleaseStatus.PROMOTION_REQUESTED
            and active_target == release.staging_collection
        ):
            reconciled = release.mark_published(
                previous_active_collection=release.previous_active_collection
            )
            action = CorpusReleaseAuditAction.PUBLISHED
        elif (
            release.status is CorpusReleaseStatus.PROMOTION_REQUESTED
            and active_target == release.previous_active_collection
        ):
            reconciled = release.restore_quality_passed()
            action = CorpusReleaseAuditAction.FAILED
        elif (
            release.status is CorpusReleaseStatus.ROLLBACK_REQUESTED
            and active_target == release.previous_active_collection
        ):
            reconciled = release.mark_rolled_back()
            action = CorpusReleaseAuditAction.ROLLED_BACK
        elif (
            release.status is CorpusReleaseStatus.ROLLBACK_REQUESTED
            and active_target == release.staging_collection
        ):
            reconciled = release.restore_published()
            action = CorpusReleaseAuditAction.FAILED
        else:
            raise CorpusReleaseConsistencyError("live alias does not match promotion intent")
        await self._release_repository.save_release(reconciled)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=principal.subject_id,
                action=action,
                old_status=release.status,
                new_status=reconciled.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=reconciled.corpus_version,
            )
        )
        await self._release_repository.commit()
        return reconciled

    async def rollback(self, principal: PrincipalContext, release_id: uuid.UUID) -> CorpusRelease:
        """Atomically restore the retained prior release only after re-verifying its manifests."""
        release = await self._authorized_release(
            principal,
            release_id,
            own_scope=_ROLLBACK_SCOPE,
            elevated_scope=_ROLLBACK_ANY_SCOPE,
        )
        if release.status is not CorpusReleaseStatus.PUBLISHED:
            raise CorpusReleaseConsistencyError("only a published release can be rolled back")
        if release.previous_active_collection is None:
            raise CorpusReleaseConsistencyError("release has no retained rollback target")
        prior_release = await self._release_repository.get_release_by_staging_collection(
            release.previous_active_collection
        )
        if prior_release is None:
            raise CorpusReleaseConsistencyError("retained rollback target has no release receipt")
        if (
            prior_release.source_id != release.source_id
            or prior_release.logical_collection != release.logical_collection
        ):
            raise CorpusReleaseConsistencyError("retained rollback receipt does not match release scope")
        await self._require_parent_manifest(prior_release)
        active_target = await self._publisher.active_target(release.logical_collection.value)
        if active_target != release.staging_collection:
            raise CorpusReleaseConsistencyError("live alias does not match published release")
        rollback_requested = release.mark_rollback_requested()
        await self._release_repository.save_release(rollback_requested)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=principal.subject_id,
                action=CorpusReleaseAuditAction.ROLLBACK_REQUESTED,
                old_status=release.status,
                new_status=rollback_requested.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=prior_release.corpus_version,
            )
        )
        await self._release_repository.commit()

        publication = await self._publisher.promote(prior_release)
        if publication.previous_active_collection != release.staging_collection:
            raise CorpusReleaseConsistencyError("active alias changed during rollback request")
        rolled_back = rollback_requested.mark_rolled_back()
        await self._release_repository.save_release(rolled_back)
        await self._release_repository.record_audit(
            CorpusReleaseAuditEvent(
                release_id=release.release_id,
                actor_id=principal.subject_id,
                action=CorpusReleaseAuditAction.ROLLED_BACK,
                old_status=release.status,
                new_status=rolled_back.status,
                old_corpus_version=release.corpus_version,
                new_corpus_version=prior_release.corpus_version,
            )
        )
        await self._release_repository.commit()
        return rolled_back

    async def _authorized_release(
        self,
        principal: PrincipalContext,
        release_id: uuid.UUID,
        *,
        own_scope: str,
        elevated_scope: str,
    ) -> CorpusRelease:
        self._require_web_curator(principal)
        release = await self._get_release(release_id)
        source = await self._source_repository.get_source(release.source_id)
        if source is None:
            raise IngestionSourceNotFoundError("release source was not found")
        AuthorizationPolicy.require_subject_access(
            principal,
            source.owner_id,
            own_scope=own_scope,
            elevated_scope=elevated_scope,
        )
        return release

    async def _require_parent_manifest(self, release: CorpusRelease) -> None:
        actual = await self._parent_repository.get_corpus_manifest(
            source_id=release.source_id,
            corpus_version=release.corpus_version,
        )
        if (
            actual.parent_count != release.parent_count
            or actual.checksum != release.parent_manifest_checksum
        ):
            raise CorpusReleaseConsistencyError("parent store manifest does not match release receipt")

    async def _get_release(self, release_id: uuid.UUID) -> CorpusRelease:
        release = await self._release_repository.get_release(release_id)
        if release is None:
            raise CorpusReleaseNotFoundError("corpus release was not found")
        return release

    @staticmethod
    def _require_web_curator(principal: PrincipalContext) -> None:
        if principal.kind != "user" or principal.source != "web":
            raise AuthorizationError("interactive curator credential is required")
