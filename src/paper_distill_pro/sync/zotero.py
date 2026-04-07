"""Zotero bidirectional sync — push papers to and pull papers from Zotero."""

from __future__ import annotations

import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper, SyncResult

logger = logging.getLogger(__name__)
BASE = "https://api.zotero.org"


def _headers() -> dict:
    return {
        "Zotero-API-Key": settings.zotero_api_key or "",
        "Zotero-API-Version": "3",
        "Content-Type": "application/json",
    }


def _lib() -> str:
    if settings.zotero_group_id:
        return f"groups/{settings.zotero_group_id}"
    return f"users/{settings.zotero_user_id}"


def _paper_to_zotero(paper: Paper, collection_key: str | None = None) -> dict:
    creators = [
        {
            "creatorType": "author",
            "firstName": " ".join(a.name.split()[:-1]),
            "lastName": a.name.split()[-1] if a.name.split() else a.name,
        }
        for a in paper.authors
    ]
    return {
        "itemType": "journalArticle",
        "title": paper.title,
        "creators": creators,
        "abstractNote": paper.abstract or "",
        "publicationTitle": paper.venue or "",
        "DOI": paper.doi or "",
        "url": paper.url or paper.oa_url or "",
        "date": str(paper.year) if paper.year else "",
        "tags": [{"tag": f} for f in paper.fields_of_study[:5]],
        "collections": [collection_key] if collection_key else [],
        "extra": f"arXiv: {paper.arxiv_id or ''}\nCitations: {paper.citation_count}\nSource: {paper.source}",
    }


def _zotero_to_paper(item: dict) -> Paper:
    """Convert a Zotero item dict to a Paper model (for pull sync)."""
    data = item.get("data", {})
    creators = data.get("creators", [])
    authors = [
        Author(name=f"{c.get('firstName', '')} {c.get('lastName', '')}".strip())
        for c in creators
        if c.get("creatorType") == "author"
    ]
    doi = data.get("DOI") or None
    extra = data.get("extra", "")
    arxiv_id = None
    for line in extra.splitlines():
        if line.startswith("arXiv:"):
            arxiv_id = line.split(":", 1)[1].strip() or None
    return Paper(
        title=data.get("title", ""),
        authors=authors,
        doi=doi,
        arxiv_id=arxiv_id,
        abstract=data.get("abstractNote") or None,
        year=int(data.get("date", "0")[:4]) if data.get("date", "").strip() else None,
        venue=data.get("publicationTitle") or None,
        url=data.get("url") or None,
        source="zotero",
        zotero_key=item.get("key"),
    )


# ── Push (write to Zotero) ────────────────────────────────────────────────────


async def sync_to_zotero(papers: list[Paper], collection_name: str | None = None) -> SyncResult:
    if not settings.zotero_api_key or not settings.zotero_user_id:
        return SyncResult(failed=len(papers), details=["Zotero API key / user ID not configured"])

    result = SyncResult()
    lib = _lib()

    async with httpx.AsyncClient(timeout=20.0) as client:
        collection_key = None
        if collection_name:
            collection_key = await _get_or_create_collection(client, lib, collection_name)

        existing_dois = await _fetch_existing_dois(client, lib)
        batch: list[dict] = []

        for paper in papers:
            if paper.doi and paper.doi.lower() in existing_dois:
                result.skipped += 1
                continue
            batch.append(_paper_to_zotero(paper, collection_key))
            if len(batch) == 50:
                ok, fail = await _write_batch(client, lib, batch)
                result.synced += ok
                result.failed += fail
                batch = []

        if batch:
            ok, fail = await _write_batch(client, lib, batch)
            result.synced += ok
            result.failed += fail

    return result


# ── Pull (read from Zotero) ───────────────────────────────────────────────────


async def pull_from_zotero(collection_name: str | None = None, limit: int = 100) -> list[Paper]:
    """Fetch papers from Zotero and return as Paper objects."""
    if not settings.zotero_api_key or not settings.zotero_user_id:
        logger.warning("Zotero credentials not configured")
        return []

    lib = _lib()
    async with httpx.AsyncClient(timeout=20.0) as client:
        params: dict = {"format": "json", "limit": min(limit, 100)}

        if collection_name:
            col_key = await _find_collection_key(client, lib, collection_name)
            if not col_key:
                logger.warning("Zotero collection '%s' not found", collection_name)
                return []
            endpoint = f"{BASE}/{lib}/collections/{col_key}/items"
        else:
            endpoint = f"{BASE}/{lib}/items"

        try:
            resp = await client.get(endpoint, headers=_headers(), params=params)
            resp.raise_for_status()
            items = resp.json()
            return [
                _zotero_to_paper(item)
                for item in items
                if item.get("data", {}).get("itemType") == "journalArticle"
            ]
        except Exception as exc:
            logger.warning("Zotero pull failed: %s", exc)
            return []


# ── helpers ───────────────────────────────────────────────────────────────────


async def _fetch_existing_dois(client: httpx.AsyncClient, lib: str) -> set[str]:
    try:
        resp = await client.get(
            f"{BASE}/{lib}/items",
            headers=_headers(),
            params={"format": "json", "itemType": "journalArticle", "limit": 100},
        )
        return {
            item["data"].get("DOI", "").lower()
            for item in resp.json()
            if item.get("data", {}).get("DOI")
        }
    except Exception:
        return set()


async def _write_batch(client: httpx.AsyncClient, lib: str, items: list[dict]) -> tuple[int, int]:
    try:
        resp = await client.post(f"{BASE}/{lib}/items", headers=_headers(), json=items)
        resp.raise_for_status()
        data = resp.json()
        return len(data.get("success", {})), len(data.get("failed", {}))
    except Exception as exc:
        logger.warning("Zotero write batch failed: %s", exc)
        return 0, len(items)


async def _get_or_create_collection(client: httpx.AsyncClient, lib: str, name: str) -> str | None:
    key = await _find_collection_key(client, lib, name)
    if key:
        return key
    try:
        resp = await client.post(
            f"{BASE}/{lib}/collections",
            headers=_headers(),
            json=[{"name": name, "parentCollection": False}],
        )
        resp.raise_for_status()
        created = resp.json()
        keys = list(created.get("success", {}).values())
        return keys[0] if keys else None
    except Exception as exc:
        logger.warning("Zotero collection create failed: %s", exc)
        return None


async def _find_collection_key(client: httpx.AsyncClient, lib: str, name: str) -> str | None:
    try:
        resp = await client.get(f"{BASE}/{lib}/collections", headers=_headers())
        for col in resp.json():
            if col["data"]["name"].lower() == name.lower():
                return col["key"]
    except Exception:
        pass
    return None
