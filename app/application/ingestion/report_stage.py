"""Gather a release's data for the Corpus Explorer; rendering is the writer's job (ING-017)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.corpus_report import (
    CorpusDiff,
    FamilyDistribution,
    FlaggedPage,
    KnowledgeSummary,
    diff_corpus,
    distributions,
    flagged_pages,
    knowledge_summary,
    pages_to_inspect,
)
from app.domain.ingestion.release_gates import GateReport, evaluate_data_gate
from app.domain.interfaces.gold import IGoldStore
from app.domain.interfaces.silver import ISilverLedger, ISilverStore
from app.domain.interfaces.wiki_ingestion import IBronzeStore, IWikiInventory


@dataclass(frozen=True)
class PageInspection:
    page_id: int
    title: str
    url: str
    raw_html: str
    silver_blocks: tuple[tuple[str, str, str], ...]
    removed: Mapping[str, int]
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True)
class CorpusReport:
    version: str
    previous: str | None
    manifest: Mapping[str, Any]
    gate: GateReport
    diff: CorpusDiff
    flagged: tuple[FlaggedPage, ...]
    distributions: tuple[FamilyDistribution, ...]
    knowledge: KnowledgeSummary
    inspections: tuple[PageInspection, ...]
    evaluation: Mapping[str, Any] | None = None


class IReportWriter(Protocol):
    def write(self, report: CorpusReport) -> str:
        """Render the report and return its store-relative entry page."""
        ...


class ReportStage:
    def __init__(
        self,
        inventory: IWikiInventory,
        bronze: IBronzeStore,
        silver: ISilverStore,
        ledger: ISilverLedger,
        gold: IGoldStore,
        writer: IReportWriter,
    ) -> None:
        self._inventory = inventory
        self._bronze = bronze
        self._silver = silver
        self._ledger = ledger
        self._gold = gold
        self._writer = writer

    async def run(
        self, version: str, previous: str | None, evaluation: Mapping[str, Any] | None
    ) -> str:
        chunks = self._gold.read_chunks(version)
        manifest = self._gold.read_manifest(version)
        states = await self._inventory.load()
        entries = await self._ledger.load()
        old_chunks = self._gold.read_chunks(previous) if previous else list(chunks)
        old_manifest = self._gold.read_manifest(previous) if previous else None
        titles = {page_id: (s.title, s.family or "") for page_id, s in states.items()}
        diff = diff_corpus(chunks, old_chunks)
        flagged = flagged_pages(entries, titles)
        by_page: dict[int, list[Chunk]] = {}
        for chunk in chunks:
            by_page.setdefault(chunk.page_id, []).append(chunk)
        inspections = []
        for page_id in pages_to_inspect(diff, flagged, chunks):
            state, entry = states.get(page_id), entries.get(page_id)
            if state is None or entry is None or state.bronze_key is None:
                continue
            document = self._silver.load(entry.lkg_path or entry.silver_path)
            inspections.append(
                PageInspection(
                    page_id=page_id,
                    title=state.title,
                    url=document.url,
                    raw_html=self._bronze.load(state.bronze_key).html,
                    silver_blocks=tuple(
                        (block.kind.value, " > ".join(block.section), block.text)
                        for block in document.blocks
                    ),
                    removed=document.removed,
                    chunks=tuple(by_page.get(page_id, ())),
                )
            )
        return self._writer.write(
            CorpusReport(
                version=version,
                previous=previous,
                manifest=manifest,
                gate=evaluate_data_gate(manifest, old_manifest),
                diff=diff,
                flagged=flagged,
                distributions=distributions(chunks),
                knowledge=knowledge_summary(self._gold.read_knowledge(version)),
                inspections=tuple(inspections),
                evaluation=evaluation,
            )
        )
