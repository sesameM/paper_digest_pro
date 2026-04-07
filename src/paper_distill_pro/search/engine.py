"""Search engine — concurrent multi-source search, dedup, score, filter."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime

from paper_distill_pro.models import Paper

from .dedup import deduplicate
from .sources import get_connectors

logger = logging.getLogger(__name__)
CURRENT_YEAR = datetime.utcnow().year


async def search_papers(
    query: str,
    max_results: int = 20,
    sources: list[str] | None = None,
    since_year: int | None = None,
    min_citations: int = 0,
) -> list[Paper]:
    connectors = get_connectors(sources)
    tasks = [c.search(query, max_results=max_results) for c in connectors]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    all_papers: list[Paper] = []
    for connector, result in zip(connectors, raw, strict=True):
        if isinstance(result, Exception):
            logger.warning("[%s] error: %s", connector.name, result)
            continue
        all_papers.extend(result)

    papers = deduplicate(all_papers)
    if since_year:
        papers = [p for p in papers if p.year is None or p.year >= since_year]
    if min_citations:
        papers = [p for p in papers if p.citation_count >= min_citations]

    papers = _score(papers, query)
    papers.sort(key=lambda p: p.score, reverse=True)

    await asyncio.gather(*[c.close() for c in connectors], return_exceptions=True)
    return papers[:max_results]


def _score(papers: list[Paper], query: str) -> list[Paper]:
    query_tokens = set(query.lower().split())
    max_cites = max((p.citation_count for p in papers), default=1) or 1
    scored = []
    for p in papers:
        relevance = _relevance(p, query_tokens)
        recency = math.exp(-max(CURRENT_YEAR - (p.year or CURRENT_YEAR), 0) / 10)
        citation_norm = math.log1p(p.citation_count) / math.log1p(max_cites)
        p = p.model_copy()
        p.score = round(0.40 * relevance + 0.35 * recency + 0.25 * citation_norm, 4)
        scored.append(p)
    return scored


def _relevance(paper: Paper, tokens: set[str]) -> float:
    text = ((paper.title or "") + " " + (paper.abstract or "")).lower()
    hits = sum(1 for t in tokens if t in text)
    return min(hits / max(len(tokens), 1), 1.0)
