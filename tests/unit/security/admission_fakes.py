"""Test-only admission control that admits everything (quota is tested separately)."""

from __future__ import annotations


class AllowAllAdmission:
    async def admit(self, *_args, **_kwargs):
        return None

    async def refund(self, *_args, **_kwargs):
        return None

    async def ensure_workload_target_allowed(self, *_args, **_kwargs):
        return None
