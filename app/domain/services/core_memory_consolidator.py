"""Fold new episodic memories into the core memory without touching what the person wrote (MEM-005).

The job only appends entries and retires entries it appended itself (`job_owned`); anything else in
the profile is the person's and is never changed or deleted (MEM-006).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.domain.interfaces.core_memory_consolidation import (
    ConsolidationState,
    EpisodicMemory,
    ICoreMemoryConsolidationStore,
    IEpisodicMemorySource,
)
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMPurpose, StructuredPrompt
from app.domain.services.core_memory import (
    MAX_ITEM_CHARS,
    MAX_ITEMS,
    MAX_NAME_CHARS,
    CoreMemory,
)
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

LIST_FIELDS = ("milestones", "preferences", "promises")
NICKNAME_FIELD = "nickname"
MAX_MEMORIES_PER_RUN = 40
MIN_ITEM_CHARS = 8
CONSOLIDATION_TEMPERATURE = 0.2
REDACTION_MARKER = "[REDACTED_"

_LIST_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "array", "items": {"type": "string"}} for name in LIST_FIELDS},
}
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        NICKNAME_FIELD: {"type": "string"},
        "add": _LIST_SCHEMA,
        "retire": _LIST_SCHEMA,
    },
    "required": ["add", "retire"],
}

SYSTEM_PROMPT = (
    "You maintain the short core profile of one person for an AI companion (Kuchiba Chisa).\n"
    "You get the current profile, split into entries written by the person (read-only) and entries "
    "you wrote earlier, plus new memories that are not in the profile yet.\n"
    "Return JSON: {\"nickname\": str, \"add\": {field: [str]}, \"retire\": {field: [str]}} with "
    f"fields {', '.join(LIST_FIELDS)}.\n"
    "- add: durable facts worth carrying in every conversation, one short sentence each, at most "
    f"{MAX_ITEM_CHARS} characters, in the language of the memory. Skip anything already covered.\n"
    "- retire: copy an entry you wrote earlier EXACTLY when a new memory makes it outdated, false "
    "or fulfilled. Never retire entries written by the person.\n"
    "- nickname: only a nickname the person and Chisa agreed on; empty string otherwise.\n"
    "Prefer returning nothing over guessing. Never invent facts."
)


@dataclass(frozen=True)
class Proposal:
    nickname: str = ""
    add: Mapping[str, list[str]] = field(default_factory=dict)
    retire: Mapping[str, list[str]] = field(default_factory=dict)


class CoreMemoryConsolidator:
    def __init__(
        self,
        llm: BaseLLMAdapter,
        store: ICoreMemoryConsolidationStore,
        source: IEpisodicMemorySource,
        pii_redactor: PiiRedactor | None = None,
    ) -> None:
        self._llm = llm
        self._store = store
        self._source = source
        self._redactor = pii_redactor or PiiRedactor()

    async def consolidate(self, owner: str) -> bool:
        """False when the person edited their core memory meanwhile; the next job retries."""
        state = await self._store.load(owner)
        memories = await self._unread(owner, state)
        if not memories:
            return True
        current = CoreMemory.model_validate(state.content)
        proposal = await self._propose(current, state, memories)
        updated, job_owned = apply_proposal(current, state.job_owned, proposal, self._redactor)
        changed = updated != current
        stored = await self._store.commit(
            owner,
            expected_version=state.version,
            content=updated.model_dump() if changed else None,
            job_owned=job_owned,
            **_watermark(state, memories),
        )
        log.info("Core memory consolidation finished", changed=changed, stored=stored)
        return stored

    async def _unread(self, owner: str, state: ConsolidationState) -> list[EpisodicMemory]:
        # Memories at the watermark second that were already folded in come back and are skipped.
        fetched = await self._source.list_user_memories_since(
            owner, state.consolidated_through, MAX_MEMORIES_PER_RUN + len(state.boundary_ids)
        )
        done = set(state.boundary_ids)
        return [memory for memory in fetched if memory.id not in done][:MAX_MEMORIES_PER_RUN]

    async def _propose(
        self, current: CoreMemory, state: ConsolidationState, memories: list[EpisodicMemory]
    ) -> Proposal:
        prompt = StructuredPrompt(
            system=SYSTEM_PROMPT,
            history=[],
            user_message=self._redactor.redact(_describe(current, state.job_owned, memories)).value,
            response_schema=RESPONSE_SCHEMA,
            temperature=CONSOLIDATION_TEMPERATURE,
            purpose=LLMPurpose.MEMORY_RECONCILIATION,
        )
        response = await self._llm.generate(prompt)
        return _parse(response.parsed)


def _watermark(state: ConsolidationState, read: list[EpisodicMemory]) -> dict[str, Any]:
    """Only memories actually read count, so the mark never passes an unread one."""
    newest = read[-1].created_at
    at_newest = {memory.id for memory in read if memory.created_at == newest}
    if newest == state.consolidated_through:
        at_newest |= set(state.boundary_ids)
    return {"consolidated_through": newest, "boundary_ids": tuple(sorted(at_newest))}


def apply_proposal(
    current: CoreMemory,
    job_owned: Mapping[str, list[str]],
    proposal: Proposal,
    redactor: PiiRedactor,
) -> tuple[CoreMemory, dict[str, list[str]]]:
    """Pure merge: never removes an entry the job does not own, never exceeds the size limits."""
    values: dict[str, Any] = {}
    owned_after: dict[str, list[str]] = {}
    for name in LIST_FIELDS:
        values[name], owned_after[name] = _merge_list(
            getattr(current, name),
            job_owned.get(name, []),
            proposal.add.get(name, []),
            proposal.retire.get(name, []),
            redactor,
        )
    values[NICKNAME_FIELD], owned_after[NICKNAME_FIELD] = _merge_nickname(
        current.nickname, job_owned.get(NICKNAME_FIELD, []), proposal.nickname, redactor
    )
    return CoreMemory.model_validate(values), owned_after


def _merge_list(
    current: list[str],
    owned: list[str],
    adds: list[str],
    retires: list[str],
    redactor: PiiRedactor,
) -> tuple[list[str], list[str]]:
    retired = {item for item in retires if item in owned}
    kept = [item for item in current if item not in retired]
    seen = {_dedupe_key(item) for item in kept}
    added: list[str] = []
    for raw in adds:
        item = raw.strip()
        if len(kept) + len(added) >= MAX_ITEMS:
            break
        # An over-long item is dropped, not cut: a clipped sentence would misstate the fact.
        if not MIN_ITEM_CHARS <= len(item) <= MAX_ITEM_CHARS:
            continue
        if _dedupe_key(item) in seen or _has_pii(item, redactor):
            continue
        added.append(item)
        seen.add(_dedupe_key(item))
    # An owned entry the person edited or removed is theirs now, so it stops being tracked.
    return kept + added, [item for item in owned if item in kept] + added


def _merge_nickname(
    current: str | None, owned: list[str], proposed: str, redactor: PiiRedactor
) -> tuple[str | None, list[str]]:
    name = proposed.strip()
    job_set_it = current is not None and current in owned
    replaceable = current is None or job_set_it
    valid = 0 < len(name) <= MAX_NAME_CHARS and not _has_pii(name, redactor)
    if replaceable and valid:
        return name, [name]
    return current, [current] if job_set_it and current else []


def _has_pii(text: str, redactor: PiiRedactor) -> bool:
    # The prompt was redacted, so the model may echo a placeholder back.
    return REDACTION_MARKER in text or redactor.redact(text).changed


def _dedupe_key(item: str) -> str:
    return " ".join(item.casefold().split())


def _describe(
    current: CoreMemory, job_owned: Mapping[str, list[str]], memories: list[EpisodicMemory]
) -> str:
    lines = [f"Nickname: {current.nickname or '(none)'}"]
    for name in LIST_FIELDS:
        owned = job_owned.get(name, [])
        items = getattr(current, name)
        lines.append(f"{name} written by the person: {[i for i in items if i not in owned]}")
        lines.append(f"{name} you wrote earlier: {[i for i in items if i in owned]}")
    lines.append("New memories:")
    lines += [f"- {memory.text}" for memory in memories]
    return "\n".join(lines)


def _parse(parsed: Any) -> Proposal:
    if not isinstance(parsed, dict):
        return Proposal()
    nickname = parsed.get(NICKNAME_FIELD)
    return Proposal(
        nickname=nickname if isinstance(nickname, str) else "",
        add=_string_lists(parsed.get("add")),
        retire=_string_lists(parsed.get("retire")),
    )


def _string_lists(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        name: [item for item in value.get(name, []) if isinstance(item, str)]
        for name in LIST_FIELDS
        if isinstance(value.get(name), list)
    }
