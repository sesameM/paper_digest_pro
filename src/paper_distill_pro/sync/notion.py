"""Notion bidirectional sync — push and pull papers from a Notion database."""

from __future__ import annotations

import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper, SyncResult

logger = logging.getLogger(__name__)
BASE = "https://api.notion.com/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _paper_to_notion(paper: Paper, database_id: str) -> dict:
    props: dict = {
        "Title": {"title": [{"text": {"content": paper.title[:2000]}}]},
        "Year": {"number": paper.year or 0},
        "Citations": {"number": paper.citation_count},
        "Authors": {
            "rich_text": [
                {"text": {"content": ", ".join(a.name for a in paper.authors[:8])[:2000]}}
            ]
        },
        "Venue": {"rich_text": [{"text": {"content": (paper.venue or "")[:500]}}]},
        "Source": {"select": {"name": paper.source or "unknown"}},
    }
    if paper.doi:
        props["DOI"] = {"rich_text": [{"text": {"content": paper.doi}}]}
    if paper.oa_url or paper.url:
        props["URL"] = {"url": paper.oa_url or paper.url}
    if paper.arxiv_id:
        props["arXiv"] = {"rich_text": [{"text": {"content": paper.arxiv_id}}]}
    if paper.fields_of_study:
        props["Fields"] = {"multi_select": [{"name": f[:100]} for f in paper.fields_of_study[:5]]}

    children = []
    if paper.abstract:
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": paper.abstract[:2000]}}]
                },
            }
        )
    return {"parent": {"database_id": database_id}, "properties": props, "children": children}


def _notion_to_paper(page: dict) -> Paper:
    props = page.get("properties", {})

    def text_val(key: str) -> str:
        items = props.get(key, {}).get("rich_text", [])
        return items[0].get("text", {}).get("content", "") if items else ""

    def title_val() -> str:
        items = props.get("Title", {}).get("title", [])
        return items[0].get("text", {}).get("content", "") if items else ""

    def num_val(key: str) -> int:
        return int(props.get(key, {}).get("number") or 0)

    author_str = text_val("Authors")
    authors = [Author(name=n.strip()) for n in author_str.split(",") if n.strip()]
    fields_raw = props.get("Fields", {}).get("multi_select", [])

    year_raw = num_val("Year")
    return Paper(
        title=title_val(),
        authors=authors,
        year=year_raw if year_raw > 0 else None,
        doi=text_val("DOI") or None,
        arxiv_id=text_val("arXiv") or None,
        venue=text_val("Venue") or None,
        citation_count=num_val("Citations"),
        url=props.get("URL", {}).get("url"),
        source="notion",
        fields_of_study=[f.get("name", "") for f in fields_raw],
    )


# ── Push ──────────────────────────────────────────────────────────────────────


async def sync_to_notion(papers: list[Paper], database_id: str | None = None) -> SyncResult:
    db_id = database_id or settings.notion_database_id
    if not settings.notion_token or not db_id:
        return SyncResult(failed=len(papers), details=["Notion token / database ID not configured"])

    result = SyncResult()
    async with httpx.AsyncClient(timeout=20.0) as client:
        existing_titles = await _fetch_existing_titles(client, db_id)
        for paper in papers:
            if paper.title.lower() in existing_titles:
                result.skipped += 1
                continue
            try:
                resp = await client.post(
                    f"{BASE}/pages", headers=_headers(), json=_paper_to_notion(paper, db_id)
                )
                resp.raise_for_status()
                result.synced += 1
            except Exception as exc:
                logger.warning("Notion push failed for '%s': %s", paper.title, exc)
                result.failed += 1
    return result


# ── Pull ──────────────────────────────────────────────────────────────────────


async def pull_from_notion(database_id: str | None = None, limit: int = 100) -> list[Paper]:
    """Fetch papers from a Notion database and return as Paper objects."""
    db_id = database_id or settings.notion_database_id
    if not settings.notion_token or not db_id:
        logger.warning("Notion credentials not configured")
        return []

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{BASE}/databases/{db_id}/query",
                headers=_headers(),
                json={"page_size": min(limit, 100)},
            )
            resp.raise_for_status()
            pages = resp.json().get("results", [])
            return [_notion_to_paper(page) for page in pages]
        except Exception as exc:
            logger.warning("Notion pull failed: %s", exc)
            return []


# ── helpers ───────────────────────────────────────────────────────────────────


async def _fetch_existing_titles(client: httpx.AsyncClient, database_id: str) -> set[str]:
    try:
        resp = await client.post(
            f"{BASE}/databases/{database_id}/query", headers=_headers(), json={"page_size": 100}
        )
        pages = resp.json().get("results", [])
        return {
            (
                page.get("properties", {})
                .get("Title", {})
                .get("title", [{}])[0]
                .get("text", {})
                .get("content", "")
            ).lower()
            for page in pages
        }
    except Exception:
        return set()
