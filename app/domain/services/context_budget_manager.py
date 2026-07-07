from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config.settings import get_settings
from app.domain.services.budget_mode import BudgetMode
from app.shared.utils.token_estimator import TokenEstimator

log = logging.getLogger(__name__)

SectionCaps = tuple[int, int, int]  # (min, target, max)


@dataclass
class BudgetAudit:
    mode: str
    total_budget: int
    effective_ceiling: int
    used: dict[str, int] = field(default_factory=dict)
    grants: dict[str, int] = field(default_factory=dict)
    flex_pool_initial: int = 0
    reallocated_from: list[str] = field(default_factory=list)
    trimmed_sections: list[str] = field(default_factory=list)
    priority_profile: str = "default"

    @property
    def total_used(self) -> int:
        return sum(self.used.values())

    @property
    def within_budget(self) -> bool:
        return self.total_used <= self.effective_ceiling

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "total_budget": self.total_budget,
            "effective_ceiling": self.effective_ceiling,
            "used": self.used,
            "grants": self.grants,
            "flex_pool_initial": self.flex_pool_initial,
            "reallocated_from": self.reallocated_from,
            "trimmed_sections": self.trimmed_sections,
            "priority_profile": self.priority_profile,
            "total_used": self.total_used,
            "within_budget": self.within_budget,
        }


@dataclass
class BudgetAllocation:
    trimmed_lore: list[str]
    trimmed_memories: list[Any]
    trimmed_history: list[dict[str, str]]
    trimmed_summary: str | None
    trimmed_search_body: str
    audit: BudgetAudit


class ContextBudgetManager:
    """
    Flex budget allocator: skeleton reserve + soft caps (min/target/max) + reallocation.
    """

    SEARCH_INSTRUCTIONS_ESTIMATE = 300
    SUMMARY_HEADER_ESTIMATE = 40
    MSG_OVERHEAD = 10

    MODE_PROFILES: dict[str, dict[str, Any]] = {
        BudgetMode.SMALL_TALK.value: {
            "sections": {
                "summary": (0, 300, 600),
                "search": (0, 0, 0),
                "lore": (0, 0, 0),
                "memory": (0, 0, 0),
                "history": (800, 3200, 4200),
            },
        },
        BudgetMode.RAG.value: {
            "sections": {
                "summary": (0, 500, 900),
                "search": (0, 800, 1600),
                "lore": (0, 1000, 1600),
                "memory": (0, 600, 1000),
                "history": (600, 2400, 4000),
            },
        },
        BudgetMode.LOOP.value: {
            "sections": {
                "summary": (0, 600, 1000),
                "search": (400, 1800, 3200),
                "lore": (0, 800, 1500),
                "memory": (0, 600, 1000),
                "history": (800, 3500, 6000),
            },
        },
    }

    PRIORITY_WEIGHTS: dict[str, dict[str, float]] = {
        "default": {"search": 1.2, "history": 1.0, "lore": 0.9, "memory": 0.8, "summary": 0.6},
        "factual_other": {"search": 1.8, "history": 1.1, "lore": 0.4, "memory": 0.7, "summary": 0.5},
        "lore_query": {"lore": 1.6, "memory": 1.0, "history": 0.9, "search": 0.5, "summary": 0.5},
    }

    TRIM_PRIORITY = ["summary", "lore", "memory", "history", "search"]

    @classmethod
    def _settings(cls):
        return get_settings()

    @classmethod
    def _total_for_mode(cls, mode: BudgetMode) -> int:
        s = cls._settings()
        return {
            BudgetMode.SMALL_TALK: s.PROMPT_BUDGET_SMALL_TALK,
            BudgetMode.RAG: s.PROMPT_BUDGET_RAG,
            BudgetMode.LOOP: s.PROMPT_BUDGET_LOOP,
        }[mode]

    @classmethod
    def resolve_priority_profile(cls, intent_name: str, has_search: bool) -> str:
        upper = (intent_name or "").upper()
        if has_search and "OTHER" in upper:
            return "factual_other"
        if any(k in upper for k in ("LORE", "STORY", "CHARACTER", "WORLD")):
            return "lore_query"
        return "default"

    @classmethod
    def _section_caps(cls, mode: BudgetMode) -> dict[str, SectionCaps]:
        return dict(cls.MODE_PROFILES[mode.value]["sections"])

    @classmethod
    def _memory_text(cls, mem: Any) -> str:
        return mem.text_content if hasattr(mem, "text_content") else str(mem)

    @classmethod
    def _pack_strings(cls, items: list[str], token_budget: int) -> tuple[list[str], int]:
        if token_budget <= 0:
            return [], 0
        packed: list[str] = []
        used = 0
        for item in items:
            item_tokens = TokenEstimator.estimate(item)
            if used + item_tokens <= token_budget:
                packed.append(item)
                used += item_tokens
            else:
                break
        return packed, used

    @classmethod
    def _pack_memories(cls, memories: list[Any], token_budget: int) -> tuple[list[Any], int]:
        if token_budget <= 0:
            return [], 0
        packed: list[Any] = []
        used = 0
        for mem in memories:
            mem_tokens = TokenEstimator.estimate(cls._memory_text(mem))
            if used + mem_tokens <= token_budget:
                packed.append(mem)
                used += mem_tokens
            else:
                break
        return packed, used

    @classmethod
    def _fit_history(
        cls,
        history: list[dict[str, str]],
        token_budget: int,
        min_turns: int,
    ) -> tuple[list[dict[str, str]], int]:
        if not history:
            return [], 0
        min_messages = max(0, min_turns * 2)
        kept: list[dict[str, str]] = []
        used = 0
        for msg in reversed(history):
            msg_tokens = TokenEstimator.estimate(msg.get("content", "")) + cls.MSG_OVERHEAD
            if used + msg_tokens <= token_budget or len(kept) < min_messages:
                kept.insert(0, msg)
                used += msg_tokens
            else:
                break
        return kept, used

    @classmethod
    def _estimate_section_need(
        cls,
        section: str,
        *,
        conversation_summary: str | None,
        tool_result: str,
        lore_chunks: list[str],
        memories: list[Any],
        history: list[dict[str, str]],
    ) -> int:
        if section == "summary":
            if not conversation_summary:
                return 0
            return cls.SUMMARY_HEADER_ESTIMATE + TokenEstimator.estimate(conversation_summary)
        if section == "search":
            if not tool_result:
                return 0
            return cls.SEARCH_INSTRUCTIONS_ESTIMATE + TokenEstimator.estimate(tool_result)
        if section == "lore":
            return sum(TokenEstimator.estimate(c) for c in lore_chunks)
        if section == "memory":
            return sum(TokenEstimator.estimate(cls._memory_text(m)) for m in memories)
        if section == "history":
            return TokenEstimator.estimate_messages(history, cls.MSG_OVERHEAD)
        return 0

    @classmethod
    def _has_section_content(
        cls,
        section: str,
        *,
        conversation_summary: str | None,
        tool_result: str,
        lore_chunks: list[str],
        memories: list[Any],
    ) -> bool:
        if section == "summary":
            return bool(conversation_summary and conversation_summary.strip())
        if section == "search":
            return bool(tool_result and tool_result.strip())
        if section == "lore":
            return bool(lore_chunks)
        if section == "memory":
            return bool(memories)
        if section == "history":
            return True
        return False

    @classmethod
    def allocate(
        cls,
        *,
        mode: BudgetMode,
        system_fixed_tokens: int,
        user_message: str,
        lore_chunks: list[str],
        memories: list[Any],
        history: list[dict[str, str]],
        conversation_summary: str | None = None,
        tool_result: str = "",
        intent_name: str = "",
    ) -> BudgetAllocation:
        settings = cls._settings()
        total_budget = cls._total_for_mode(mode)
        flex_ratio = settings.PROMPT_FLEX_RATIO
        skeleton_headroom = settings.PROMPT_SKELETON_HEADROOM
        reallocate_empty = settings.PROMPT_REALLOCATE_EMPTY
        history_min_turns = settings.PROMPT_HISTORY_MIN_TURNS

        effective_ceiling = int(total_budget * (1 + flex_ratio))
        skeleton_reserve = int(system_fixed_tokens * (1 + skeleton_headroom))
        user_reserve = TokenEstimator.estimate(user_message) + 20

        caps = cls._section_caps(mode)
        has_search = bool(tool_result and tool_result.strip())
        priority_profile = cls.resolve_priority_profile(intent_name, has_search)
        weights = cls.PRIORITY_WEIGHTS[priority_profile]

        flex_pool = total_budget - skeleton_reserve - user_reserve
        reallocated_from: list[str] = []

        if reallocate_empty:
            for section in ("lore", "memory", "search", "summary"):
                if not cls._has_section_content(
                    section,
                    conversation_summary=conversation_summary,
                    tool_result=tool_result,
                    lore_chunks=lore_chunks,
                    memories=memories,
                ):
                    _, target, _ = caps[section]
                    if target > 0:
                        flex_pool += target
                        reallocated_from.append(section)

        flex_pool_initial = flex_pool
        grants: dict[str, int] = {s: 0 for s in caps}

        section_order = sorted(
            caps.keys(),
            key=lambda s: weights.get(s, 0.5),
            reverse=True,
        )

        for section in section_order:
            mn, target, mx = caps[section]
            need = cls._estimate_section_need(
                section,
                conversation_summary=conversation_summary,
                tool_result=tool_result,
                lore_chunks=lore_chunks,
                memories=memories,
                history=history,
            )
            if need <= 0:
                continue
            desired = min(need, mx)
            if desired < mn and need >= mn:
                desired = mn
            grant = min(desired, max(flex_pool, 0))
            grants[section] = grant
            flex_pool -= grant

        for section in section_order:
            mn, _, mx = caps[section]
            need = cls._estimate_section_need(
                section,
                conversation_summary=conversation_summary,
                tool_result=tool_result,
                lore_chunks=lore_chunks,
                memories=memories,
                history=history,
            )
            if need <= 0:
                continue
            if grants[section] >= min(need, mx):
                continue
            extra_cap = mx - grants[section]
            extra_need = min(need, mx) - grants[section]
            extra = min(extra_cap, extra_need, max(flex_pool, 0))
            if extra > 0:
                grants[section] += extra
                flex_pool -= extra

        trimmed_sections: list[str] = []

        summary_grant = grants["summary"]
        trimmed_summary: str | None = None
        summary_used = 0
        if conversation_summary and summary_grant > 0:
            body_budget = max(summary_grant - cls.SUMMARY_HEADER_ESTIMATE, 0)
            trimmed_body = TokenEstimator.trim_to_budget(
                conversation_summary,
                body_budget,
                suffix="... (tóm tắt đã rút gọn)",
            )
            trimmed_summary = trimmed_body
            summary_used = cls.SUMMARY_HEADER_ESTIMATE + TokenEstimator.estimate(trimmed_body)
            if TokenEstimator.estimate(conversation_summary) > TokenEstimator.estimate(trimmed_body):
                trimmed_sections.append("summary")

        search_grant = grants["search"]
        trimmed_search_body = ""
        search_used = 0
        if tool_result and search_grant > 0:
            body_budget = max(search_grant - cls.SEARCH_INSTRUCTIONS_ESTIMATE, 0)
            trimmed_search_body = TokenEstimator.trim_to_budget(
                tool_result,
                body_budget,
                suffix="... (đã rút gọn do vượt quá dung lượng)",
            )
            search_used = cls.SEARCH_INSTRUCTIONS_ESTIMATE + TokenEstimator.estimate(trimmed_search_body)
            if TokenEstimator.estimate(tool_result) > TokenEstimator.estimate(trimmed_search_body):
                trimmed_sections.append("search")

        lore_grant = grants["lore"]
        trimmed_lore, lore_used = cls._pack_strings(lore_chunks, lore_grant)
        if len(trimmed_lore) < len(lore_chunks):
            trimmed_sections.append("lore")

        memory_grant = grants["memory"]
        trimmed_memories, memory_used = cls._pack_memories(memories, memory_grant)
        if len(trimmed_memories) < len(memories):
            trimmed_sections.append("memory")

        history_grant = grants["history"]
        trimmed_history, history_used = cls._fit_history(
            history, history_grant, history_min_turns
        )
        if len(trimmed_history) < len(history):
            trimmed_sections.append("history")

        used = {
            "skeleton": skeleton_reserve,
            "user": user_reserve,
            "summary": summary_used,
            "search": search_used,
            "lore": lore_used,
            "memory": memory_used,
            "history": history_used,
        }

        audit = BudgetAudit(
            mode=mode.value,
            total_budget=total_budget,
            effective_ceiling=effective_ceiling,
            used=used,
            grants=grants,
            flex_pool_initial=flex_pool_initial,
            reallocated_from=reallocated_from,
            trimmed_sections=trimmed_sections,
            priority_profile=priority_profile,
        )

        if audit.total_used > effective_ceiling:
            log.warning(
                "Prompt budget exceeds flex ceiling after allocation",
                total_used=audit.total_used,
                effective_ceiling=effective_ceiling,
                mode=mode.value,
            )

        return BudgetAllocation(
            trimmed_lore=trimmed_lore,
            trimmed_memories=trimmed_memories,
            trimmed_history=trimmed_history,
            trimmed_summary=trimmed_summary,
            trimmed_search_body=trimmed_search_body,
            audit=audit,
        )


