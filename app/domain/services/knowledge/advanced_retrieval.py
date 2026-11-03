"""Advanced retrieval as a fixed flow: lookups, search, one correction pass (ADV-001, ADV-007)."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.interfaces.llm_provider import LLMCallBudget
from app.domain.models.evidence import Evidence
from app.domain.services.knowledge.lore_search import (
    ILoreIndex,
    LoreSearchService,
    to_evidence,
)
from app.domain.services.knowledge.question_router import QuestionRoute, QuestionRouter
from app.domain.services.knowledge.structured_tools import StructuredTools

DIALOGUE_LIMIT = 8


@dataclass(frozen=True)
class AdvancedEvidence:
    evidence: tuple[Evidence, ...]
    query: str
    # Nothing strong enough was found, so the Composer must abstain in Chisa's voice.
    abstain: bool
    expanded: bool
    degraded: tuple[str, ...]
    # An exact list from structured data; given to the Composer alone, because the LLM
    # skipped these short lines for longer passages when it saw both.
    listed: tuple[Evidence, ...] = ()


class AdvancedRetrieval:
    def __init__(
        self,
        search: LoreSearchService,
        tools: StructuredTools,
        router: QuestionRouter,
        dialogue: ILoreIndex,
    ) -> None:
        self._search = search
        self._tools = tools
        self._router = router
        self._dialogue = dialogue

    async def retrieve(
        self, question: str, budget: LLMCallBudget | None = None
    ) -> AdvancedEvidence:
        found = await self._search.search(question, budget)
        route = self._router.route((question, found.query), found.entities)
        listed = self._listed(route)
        profiles = tuple(
            item for item in map(self._tools.get_entity, route.profiles) if item is not None
        )
        # A profile card is context, not an answer: a question about a fact the card lacks
        # must still abstain, so only listings and strong search results count as sufficient.
        sufficient = bool(listed) or found.strong
        extra: tuple[Evidence, ...] = ()
        expanded = False
        if not sufficient and found.entities:
            extra = await self._dialogue_evidence(found.query, found.vector, found.entities)
            expanded = True
        evidence = self._unique((*listed, *profiles, *found.evidence, *extra))
        return AdvancedEvidence(
            evidence=evidence,
            query=found.query,
            abstain=not sufficient and not extra,
            expanded=expanded,
            degraded=found.degraded,
            listed=listed,
        )

    def _listed(self, route: QuestionRoute) -> tuple[Evidence, ...]:
        quests = (
            self._tools.list_quests(
                location=route.quest_location,
                chapter=route.quest_chapter,
                character=route.quest_character,
            )
            if route.lists_quests
            else ()
        )
        entities = (
            self._tools.find_entities(fields=route.entity_fields, entity_type="resonator")
            if route.entity_fields
            else ()
        )
        return (*quests, *entities)

    async def _dialogue_evidence(
        self, query: str, vector: tuple[float, ...], entities: tuple[str, ...]
    ) -> tuple[Evidence, ...]:
        """Dialogue only when canon falls short, and only about the entity asked (ADV-005)."""
        hits = await self._dialogue.search(
            query, vector, own_titles=(), mentioned=entities, limit=DIALOGUE_LIMIT
        )
        return tuple(to_evidence(hit, hit.score) for hit in hits)

    @staticmethod
    def _unique(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        return tuple({item.evidence_id: item for item in reversed(evidence)}.values())[::-1]
