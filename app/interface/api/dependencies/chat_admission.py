"""HTTP adapters for chat admission control (daily quotas, workload target boundary)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

from app.application.dependencies import get_chat_admission_control
from app.application.security.chat_admission import (
    ChatAdmissionControl,
    QuotaExceededError,
    QuotaReservation,
    QuotaUnavailableError,
    WorkloadTargetDeniedError,
)
from app.domain.value_objects.principal import PrincipalContext

Admission = Annotated[ChatAdmissionControl, Depends(get_chat_admission_control)]

QUOTA_EXCEEDED_DETAIL = (
    "Hôm nay Chisa đã trò chuyện hết lượt cho phiên này rồi, Senpai quay lại vào ngày mai nhé~"
)


async def admit_chat(
    admission: ChatAdmissionControl, principal: PrincipalContext, http_request: Any = None
) -> QuotaReservation | None:
    """Charge the daily quotas for one chat request or raise 429/503 (fail-closed)."""
    state = getattr(http_request, "state", None)
    client_ip = getattr(state, "client_ip", None) if state is not None else None
    try:
        return await admission.admit(principal, client_ip)
    except QuotaExceededError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=QUOTA_EXCEEDED_DETAIL,
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    except QuotaUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        ) from error


async def deny_workload_account_target(
    admission: ChatAdmissionControl, session: Any, principal: PrincipalContext, target: str
) -> None:
    """Discord workload credentials never act on registered web accounts."""
    if principal.kind != "workload":
        return
    try:
        await admission.ensure_workload_target_allowed(session, principal, target)
    except WorkloadTargetDeniedError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error
