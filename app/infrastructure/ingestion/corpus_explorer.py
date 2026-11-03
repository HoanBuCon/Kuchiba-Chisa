"""Static HTML Corpus Explorer: opens from disk with no server or external asset (ING-017)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from app.application.ingestion.report_stage import CorpusReport, PageInspection
from app.infrastructure.ingestion.silver.rules import CONFIG_DIR

REPORTS_DIR = "reports"
TEMPLATES_DIR = CONFIG_DIR / "explorer"
# Enough to compare markup by eye; the full page stays in bronze.
RAW_PREVIEW_CHARS = 20_000


class HtmlCorpusExplorer:
    """Wiki text is untrusted, so autoescape stays on and no page runs a script."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def write(self, report: CorpusReport) -> str:
        folder = self._root / REPORTS_DIR / report.version
        (folder / "pages").mkdir(parents=True, exist_ok=True)
        inspected = {page.page_id for page in report.inspections}

        def page_link(page_id: int, title: str) -> Markup:
            label = escape(title or page_id)
            if page_id not in inspected:
                return Markup(label)
            return Markup('<a href="pages/{}.html">{}</a>').format(page_id, label)

        index = self._env.get_template("index.html").render(r=report, page_link=page_link)
        (folder / "index.html").write_text(index, encoding="utf-8")
        for page in report.inspections:
            (folder / "pages" / f"{page.page_id}.html").write_text(
                self._page(page, report.version), encoding="utf-8"
            )
        return f"{REPORTS_DIR}/{report.version}/index.html"

    def _page(self, page: PageInspection, version: str) -> str:
        raw = page.raw_html[:RAW_PREVIEW_CHARS]
        return self._env.get_template("page.html").render(p=page, raw=raw, version=version)
