"""Authenticated caller identity used at all application boundaries."""

from dataclasses import dataclass
from typing import Literal

PrincipalKind = Literal["user", "workload"]
PrincipalSource = Literal["web", "discord"]


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """Identity and authority extracted from a verified credential only.

    Request bodies, headers, paths, and external channel payloads must never
    construct this value.  They are untrusted input and may only be checked
    against this context by the authorization policy.
    """

    subject_id: str
    tenant_id: str | None
    channel_id: str | None
    source: PrincipalSource
    kind: PrincipalKind
    scopes: frozenset[str]
    display_name: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
