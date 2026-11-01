"""Decide which pages to re-fetch and which are gone (ING-002, ING-013); pure and deterministic."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import IntEnum

from app.domain.ingestion.pages import PageState, PageStatus


class FetchReason(IntEnum):
    """Lower value is fetched first when the per-run budget is short."""

    NEW = 1
    REVISION = 2
    CONTENT_TEMPLATE = 3
    ROLLING_REFRESH = 4


@dataclass(frozen=True)
class FetchDecision:
    page_id: int
    title: str
    reason: FetchReason


@dataclass(frozen=True)
class TemplateClassifier:
    """Chrome templates (navboxes, stubs, DPL) re-render pages without changing ingested text."""

    chrome_patterns: tuple[str, ...]
    content_patterns: tuple[str, ...] = ()

    def is_content(self, template: str) -> bool:
        # An explicit content match wins; unknown templates count as content (safe default).
        if any(re.search(pattern, template, re.IGNORECASE) for pattern in self.content_patterns):
            return True
        return not any(
            re.search(pattern, template, re.IGNORECASE) for pattern in self.chrome_patterns
        )


@dataclass(frozen=True)
class FetchPolicy:
    stabilization: timedelta
    rolling_fraction: float
    budget: int


def plan_fetches(
    states: Iterable[PageState],
    *,
    revision_times: Mapping[int, datetime],
    changed_templates: frozenset[str],
    classifier: TemplateClassifier,
    policy: FetchPolicy,
    now: datetime,
) -> list[FetchDecision]:
    """Rank in-scope pages by why they need fetching and cut the list at the run budget."""
    in_scope = [state for state in states if state.in_text_scope]
    decisions = [
        d
        for d in (
            _decide(s, revision_times, changed_templates, classifier, policy, now) for s in in_scope
        )
        if d
    ]
    chosen = {decision.page_id for decision in decisions}
    decisions.extend(_rolling_refresh(in_scope, chosen, policy.rolling_fraction))
    decisions.sort(key=lambda decision: (decision.reason, decision.page_id))
    return decisions[: policy.budget]


def _decide(
    state: PageState,
    revision_times: Mapping[int, datetime],
    changed_templates: frozenset[str],
    classifier: TemplateClassifier,
    policy: FetchPolicy,
    now: datetime,
) -> FetchDecision | None:
    if state.fetched_revid is None:
        return FetchDecision(state.page_id, state.title, FetchReason.NEW)
    if state.fetched_revid != state.last_revid:
        revised_at = revision_times.get(state.page_id)
        # Vandal edits are usually reverted within the stabilisation window (D-ING-3).
        if revised_at is not None and now - revised_at < policy.stabilization:
            return None
        return FetchDecision(state.page_id, state.title, FetchReason.REVISION)
    retouched = state.fetched_touched is None or state.touched > state.fetched_touched
    if retouched and any(
        classifier.is_content(template)
        for template in changed_templates.intersection(state.templates)
    ):
        return FetchDecision(state.page_id, state.title, FetchReason.CONTENT_TEMPLATE)
    return None


def _rolling_refresh(
    in_scope: list[PageState], chosen: set[int], fraction: float
) -> list[FetchDecision]:
    """Re-fetch the stalest pages so a wrong template class can never hide a change forever."""
    quota = math.ceil(len(in_scope) * fraction)
    stale = sorted(
        (s for s in in_scope if s.page_id not in chosen and s.fetched_at is not None),
        key=lambda s: (s.fetched_at, s.page_id),
    )
    return [FetchDecision(s.page_id, s.title, FetchReason.ROLLING_REFRESH) for s in stale[:quota]]


def mark_absent(
    states: Mapping[int, PageState],
    present_ids: frozenset[int],
    confirmed_deleted: frozenset[int],
) -> dict[int, PageState]:
    """First absence marks pending; a second absence with a deletion log entry makes a tombstone."""
    updated: dict[int, PageState] = {}
    for page_id, state in states.items():
        if page_id in present_ids or state.status is PageStatus.DELETED:
            continue
        if state.status is PageStatus.PENDING_DELETE and page_id in confirmed_deleted:
            updated[page_id] = replace(state, status=PageStatus.DELETED)
        elif state.status is PageStatus.ACTIVE:
            updated[page_id] = replace(state, status=PageStatus.PENDING_DELETE)
    return updated
