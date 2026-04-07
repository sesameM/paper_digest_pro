"""Digest builder — search per keyword and assemble a Digest object."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from paper_distill_pro.models import Digest, DigestConfig, DigestSection
from paper_distill_pro.search.engine import search_papers

logger = logging.getLogger(__name__)


async def build_digest(cfg: DigestConfig, title: str = "Scholar Digest") -> Digest:
    since_year = (datetime.now(tz=UTC) - timedelta(days=cfg.since_days * 5)).year
    tasks = [
        _fetch_section(
            keyword=kw,
            max_results=cfg.max_papers_per_keyword,
            since_year=since_year,
            min_citations=cfg.min_citation_count,
            sources=cfg.sources or None,
        )
        for kw in cfg.keywords
    ]
    sections = await asyncio.gather(*tasks)
    return Digest(
        title=title,
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        sections=[s for s in sections if s.papers],
    )


async def _fetch_section(keyword, max_results, since_year, min_citations, sources) -> DigestSection:
    papers = await search_papers(
        query=keyword,
        max_results=max_results,
        sources=sources,
        since_year=since_year,
        min_citations=min_citations,
    )
    return DigestSection(keyword=keyword, papers=papers)
