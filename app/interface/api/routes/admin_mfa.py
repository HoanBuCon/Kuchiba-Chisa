"""Admin TOTP enrollment and step-up verification (SEC-ADM-002, SEC-ADM-006, SEC-ADM-010)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.security.admin_mfa_service import (
    InvalidMfaCodeError,
    MfaAlreadyEnrolledError,
    MfaEnrollmentNotPendingError,
    MfaLockedError,
    MfaNotEnrolledError,
)
from app.domain.models.admin_mfa import STEP_UP_WINDOW
from app.domain.models.rbac import Permission
from app.interface.api.dependencies.security import (
    AdminMfaServiceDep,
    CurrentPrincipal,
    DbSession,
    admin_session_id,
    require_permission,
)

router = APIRouter(
    prefix="/admin/mfa",
    tags=["Admin MFA"],
    dependencies=[Depends(require_permission(Permission.ADMIN_CONSOLE))],
)
MAX_CODE_CHARS = 32


class CodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)


class EnrollmentView(BaseModel):
    secret: str
    provisioning_uri: str


class RecoveryCodesView(BaseModel):
    recovery_codes: list[str]
    step_up_seconds: int


class StepUpView(BaseModel):
    step_up_seconds: int


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _identity(principal: CurrentPrincipal) -> tuple[UUID, UUID]:
    session_id = admin_session_id(principal)
    if session_id is None:
        raise _error(status.HTTP_401_UNAUTHORIZED, "session_required")
    return UUID(principal.subject_id), session_id


@router.post("/enroll")
async def begin_enrollment(
    principal: CurrentPrincipal, service: AdminMfaServiceDep, session: DbSession
) -> EnrollmentView:
    account_id, _ = _identity(principal)
    try:
        enrollment = await service.begin_enrollment(session, account_id)
    except MfaAlreadyEnrolledError as error:
        raise _error(status.HTTP_409_CONFLICT, "mfa_already_enrolled") from error
    return EnrollmentView(secret=enrollment.secret, provisioning_uri=enrollment.provisioning_uri)


@router.post("/enroll/confirm")
async def confirm_enrollment(
    body: CodeRequest, principal: CurrentPrincipal, service: AdminMfaServiceDep, session: DbSession
) -> RecoveryCodesView:
    account_id, session_id = _identity(principal)
    try:
        codes = await service.confirm_enrollment(session, account_id, session_id, body.code)
    except MfaEnrollmentNotPendingError as error:
        raise _error(status.HTTP_409_CONFLICT, "mfa_enrollment_not_pending") from error
    except (InvalidMfaCodeError, MfaLockedError) as error:
        raise _rejection(error) from error
    return RecoveryCodesView(
        recovery_codes=codes, step_up_seconds=int(STEP_UP_WINDOW.total_seconds())
    )


@router.post("/verify")
async def verify_code(
    body: CodeRequest, principal: CurrentPrincipal, service: AdminMfaServiceDep, session: DbSession
) -> StepUpView:
    account_id, session_id = _identity(principal)
    try:
        await service.verify(session, account_id, session_id, body.code)
    except MfaNotEnrolledError as error:
        raise _error(status.HTTP_409_CONFLICT, "mfa_not_enrolled") from error
    except (InvalidMfaCodeError, MfaLockedError) as error:
        raise _rejection(error) from error
    return StepUpView(step_up_seconds=int(STEP_UP_WINDOW.total_seconds()))


@router.post("/verify/recovery")
async def verify_recovery_code(
    body: CodeRequest, principal: CurrentPrincipal, service: AdminMfaServiceDep, session: DbSession
) -> StepUpView:
    account_id, session_id = _identity(principal)
    try:
        await service.verify_recovery_code(session, account_id, session_id, body.code)
    except MfaNotEnrolledError as error:
        raise _error(status.HTTP_409_CONFLICT, "mfa_not_enrolled") from error
    except (InvalidMfaCodeError, MfaLockedError) as error:
        raise _rejection(error) from error
    return StepUpView(step_up_seconds=int(STEP_UP_WINDOW.total_seconds()))


def _rejection(error: Exception) -> HTTPException:
    if isinstance(error, MfaLockedError):
        return _error(status.HTTP_429_TOO_MANY_REQUESTS, "mfa_locked")
    return _error(status.HTTP_401_UNAUTHORIZED, "invalid_mfa_code")
