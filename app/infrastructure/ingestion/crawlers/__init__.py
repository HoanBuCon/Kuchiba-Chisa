"""
Crawler Package for Wuthering Waves Wiki Lore.
Provides async rate-limited discovery, pre-crawl selection, and raw wikitext extraction.
"""

from app.infrastructure.ingestion.crawlers.wiki_crawler import (
    WikiCrawler,
    CrawlReport,
    run_wiki_crawl,
)

__all__ = ["WikiCrawler", "CrawlReport", "run_wiki_crawl"]
