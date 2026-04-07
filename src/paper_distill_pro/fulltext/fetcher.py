"""Full-text fetcher — 4-level OA chain: metadata → CORE → Unpaywall → arXiv."""

from __future__ import annotations

import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Paper

logger = logging.getLogger(__name__)


async def fetch_pdf_bytes(paper: Paper) -> bytes | None:
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": settings.user_agent}, follow_redirects=True
    ) as client:
        for url in _candidate_urls(paper):
            data = await _download(client, url)
            if data:
                return data
    return None


async def resolve_oa_url(paper: Paper) -> str | None:
    """Return the best open-access URL without downloading."""
    if paper.oa_url:
        return paper.oa_url
    if paper.pdf_url:
        return paper.pdf_url
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        if paper.doi:
            url = await _unpaywall(client, paper.doi)
            if url:
                return url
    if paper.arxiv_id:
        return f"https://arxiv.org/abs/{paper.arxiv_id}"
    return None


def _candidate_urls(paper: Paper) -> list[str]:
    urls: list[str] = []
    if paper.pdf_url:
        urls.append(paper.pdf_url)
    if paper.oa_url and paper.oa_url != paper.pdf_url:
        urls.append(paper.oa_url)
    if paper.arxiv_id:
        urls.append(f"https://arxiv.org/pdf/{paper.arxiv_id}")
    return urls


async def _download(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            if "pdf" in ct or resp.content[:4] == b"%PDF":
                return resp.content
    except Exception as exc:
        logger.debug("PDF download failed for %s: %s", url, exc)
    return None


async def _unpaywall(client: httpx.AsyncClient, doi: str) -> str | None:
    try:
        resp = await client.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": settings.unpaywall_email},
        )
        data = resp.json()
        if oa_loc := data.get("best_oa_location"):
            return oa_loc.get("url_for_pdf") or oa_loc.get("url")
    except Exception as exc:
        logger.debug("Unpaywall failed for doi=%s: %s", doi, exc)
    return None
