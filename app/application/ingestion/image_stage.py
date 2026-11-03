"""Image stage: fetch and vet entity images, apart from text so it can never harm text (ING-019)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace
from urllib.parse import urlsplit

from app.domain.ingestion.entity_images import (
    ImageInfo,
    ImagePolicy,
    ImageRecord,
    ImageReport,
    entities_by_file,
)
from app.domain.interfaces.entity_images import (
    IImageInspector,
    IImageSource,
    IImageVault,
    ImageDownloadError,
    ImageRejectedError,
)
from app.domain.interfaces.wiki_ingestion import IBronzeStore, IWikiInventory


class ImageStage:
    def __init__(
        self,
        inventory: IWikiInventory,
        bronze: IBronzeStore,
        source: IImageSource,
        inspector: IImageInspector,
        vault: IImageVault,
        policy: ImagePolicy,
    ) -> None:
        self._inventory = inventory
        self._bronze = bronze
        self._source = source
        self._inspector = inspector
        self._vault = vault
        self._policy = policy

    async def run(self) -> ImageReport:
        linked = await self._linked_files()
        previous = self._vault.load_index()
        records: dict[str, ImageRecord] = {}
        failures: dict[str, str] = {}
        downloaded = reused = 0
        for info in await self._infos(linked, failures):
            kept = previous.get(info.name)
            if kept and kept.sha1 == info.sha1 and self._vault.has(kept):
                records[info.name] = replace(kept, entities=linked[info.name])
                reused += 1
                continue
            try:
                records[info.name] = await self._fetch(info, linked[info.name])
                downloaded += 1
            except (ImageRejectedError, ImageDownloadError) as error:
                failures[info.name] = f"{type(error).__name__}: {error}"
                if kept:
                    records[info.name] = replace(kept, entities=linked[info.name])
        self._vault.save_index(tuple(records.values()))
        return ImageReport(
            referenced=len(linked),
            downloaded=downloaded,
            reused=reused,
            failures=failures,
            orphans=sum(name not in linked for name in previous),
            max_failure_ratio=self._policy.max_failure_ratio,
        )

    async def _linked_files(self) -> Mapping[str, tuple[str, ...]]:
        states = await self._inventory.load()
        pages = (
            (state.title, self._bronze.load(state.bronze_key).properties)
            for state in states.values()
            if state.in_text_scope and state.bronze_key is not None
        )
        return entities_by_file(pages, self._policy.excluded_files)

    async def _infos(
        self, linked: Mapping[str, tuple[str, ...]], failures: dict[str, str]
    ) -> list[ImageInfo]:
        names = sorted(linked)
        size = self._policy.batch_size
        infos: list[ImageInfo] = []
        for start in range(0, len(names), size):
            infos.extend(await self._source.image_info(names[start : start + size]))
        found = {info.name for info in infos}
        failures.update({name: "missing on the wiki" for name in names if name not in found})
        return infos

    async def _fetch(self, info: ImageInfo, entities: tuple[str, ...]) -> ImageRecord:
        if urlsplit(info.url).hostname not in self._policy.allowed_hosts:
            raise ImageRejectedError("image host is not allowed")
        if info.size > self._policy.max_bytes:
            raise ImageRejectedError("declared size exceeds the limit")
        content = await self._source.download(info.url)
        inspected = self._inspector.inspect(content, info.mime)
        sha256 = hashlib.sha256(content).hexdigest()
        display = self._inspector.display_copy(content)
        original_path, display_path = self._vault.save(sha256, inspected.mime, content, display)
        return ImageRecord(
            name=info.name,
            sha1=info.sha1,
            sha256=sha256,
            mime=inspected.mime,
            width=inspected.width,
            height=inspected.height,
            size=len(content),
            original_path=original_path,
            display_path=display_path,
            file_page_url=info.file_page_url,
            revid=info.revid,
            entities=entities,
        )
