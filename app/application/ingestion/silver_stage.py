"""Silver stage: clean fetched pages, check them, keep each last-known-good (ING-003, ING-006)."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.ingestion.corpus_safety import CorpusSafetyPolicy
from app.domain.ingestion.documents import CanonicalDocument
from app.domain.ingestion.page_checks import (
    SAFETY_REASON_PREFIX,
    CheckPolicy,
    FamilyContract,
    Verdict,
    check_page,
)
from app.domain.ingestion.pages import PageState
from app.domain.interfaces.silver import (
    CleaningError,
    IPageCleaner,
    ISilverLedger,
    ISilverStore,
    SilverEntry,
)
from app.domain.interfaces.wiki_ingestion import IBronzeStore, IWikiInventory


@dataclass(frozen=True)
class SilverReport:
    stats: dict[str, int]
    # (title, reasons) for every page that did not produce usable silver this run.
    flagged: tuple[tuple[str, tuple[str, ...]], ...] = ()
    # CSS class -> pages using it, for classes outside the known baseline (schema drift).
    unknown_markup: dict[str, int] = field(default_factory=dict)


def silver_key(state: PageState, cleaner_version: str) -> str:
    """Same bronze, family and cleaner always yield the same silver, so the key is their hash."""
    source = f"{state.bronze_key}|{state.family}|{cleaner_version}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def output_hash(document: CanonicalDocument) -> str:
    """Hash of what the corpus sees; revision ids are left out so a no-op edit is unchanged."""
    content = repr((document.blocks, document.infoboxes, document.glossary))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _needs_check(previous: SilverEntry | None, path: str) -> bool:
    if previous is None or previous.silver_path != path:
        return True
    # Held pages build up their stability count; blocked pages may have gained an approval.
    return previous.verdict is Verdict.HOLD or any(
        reason.startswith(SAFETY_REASON_PREFIX) for reason in previous.reasons
    )


class SilverStage:
    def __init__(
        self,
        inventory: IWikiInventory,
        bronze: IBronzeStore,
        cleaner: IPageCleaner,
        silver: ISilverStore,
        ledger: ISilverLedger,
        *,
        policy: CheckPolicy,
        contracts: Mapping[str, FamilyContract],
        safety: CorpusSafetyPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inventory = inventory
        self._bronze = bronze
        self._cleaner = cleaner
        self._silver = silver
        self._ledger = ledger
        self._policy = policy
        self._contracts = contracts
        self._safety = safety or CorpusSafetyPolicy()
        self._clock = clock

    async def run(self) -> SilverReport:
        states = await self._inventory.load()
        entries = await self._ledger.load()
        stats: Counter[str] = Counter()
        updated: list[SilverEntry] = []
        flagged: list[tuple[str, tuple[str, ...]]] = []
        unknown: Counter[str] = Counter()
        for state in states.values():
            if not state.in_text_scope or state.bronze_key is None:
                continue
            key = silver_key(state, self._cleaner.version)
            previous = entries.get(state.page_id)
            if not _needs_check(previous, self._silver.path_for(state.page_id, key)):
                stats["unchanged"] += 1
                continue
            try:
                entry, document = self._check(state, state.bronze_key, key, previous)
            except (OSError, CleaningError) as error:
                stats["failed"] += 1
                flagged.append((state.title, (f"error:{type(error).__name__}",)))
                continue
            updated.append(entry)
            stats[entry.verdict.value] += 1
            stats["unexplained_chars"] += document.unexplained_chars
            unknown.update(document.unknown_markup)
            if entry.verdict in {Verdict.QUARANTINE, Verdict.HOLD}:
                flagged.append((state.title, entry.reasons))
        await self._ledger.upsert(updated)
        return SilverReport(
            stats={"checked": len(updated), **stats},
            flagged=tuple(flagged),
            unknown_markup=dict(unknown.most_common()),
        )

    def _check(
        self, state: PageState, bronze_key: str, key: str, previous: SilverEntry | None
    ) -> tuple[SilverEntry, CanonicalDocument]:
        cleaned = self._cleaner.clean(self._bronze.load(bronze_key), state.family)
        document = self._safety.redact_emails(cleaned)
        path = self._silver.save(key, document)
        digest = output_hash(document)
        unchanged = (
            previous.unchanged_runs + 1 if previous and previous.output_hash == digest else 0
        )
        last_good_path = previous.lkg_path if previous else None
        last_good = self._silver.load(last_good_path) if last_good_path else None
        result = check_page(
            document,
            policy=self._policy,
            contract=self._contracts.get(state.family or ""),
            last_known_good=last_good,
            unchanged_runs=unchanged,
            safety_findings=self._safety.scan(document),
        )
        entry = SilverEntry(
            page_id=state.page_id,
            silver_path=path,
            output_hash=digest,
            verdict=result.verdict,
            reasons=result.reasons,
            unchanged_runs=unchanged,
            checked_at=self._clock(),
            lkg_path=path if result.usable else last_good_path,
        )
        return entry, document
