"""
Mendeley bidirectional sync — OAuth 2.0 client credentials flow.

Setup:
  1. Register app at https://dev.mendeley.com/
  2. Set MENDELEY_CLIENT_ID and MENDELEY_CLIENT_SECRET in .env
  3. First run calls mendeley_auth() which opens a browser for the OAuth flow,
     then stores the access token in MENDELEY_ACCESS_TOKEN

For automated/CI use, use the client_credentials grant (no user interaction).
"""

from __future__ import annotations

import logging
import time

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper, SyncResult

logger = logging.getLogger(__name__)

BASE = "https://api.mendeley.com"
TOKEN_URL = "https://api.mendeley.com/oauth/token"

_token_cache: dict[str, str | float] = {}


# ── Token management ──────────────────────────────────────────────────────────


async def _get_token() -> str | None:
    """Return a valid access token, refreshing if expired."""
    # 1. Use a stored token from env
    if settings.mendeley_access_token:
        return settings.mendeley_access_token

    # 2. Try client_credentials grant (no user interaction)
    if settings.mendeley_client_id and settings.mendeley_client_secret:
        if _token_cache.get("expires_at", 0) > time.time():
            return str(_token_cache.get("access_token", ""))
        return await _client_credentials_grant()

    logger.warning("Mendeley credentials not configured")
    return None


async def _client_credentials_grant() -> str | None:
    """Obtain token via client credentials (for reading public documents)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": "all",
                    "client_id": settings.mendeley_client_id,
                    "client_secret": settings.mendeley_client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = time.time() + expires_in - 60
            return token
    except Exception as exc:
        logger.warning("Mendeley client_credentials grant failed: %s", exc)
        return None


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.mendeley-document.1+json",
    }


# ── Paper ↔ Mendeley conversion ───────────────────────────────────────────────


def _paper_to_mendeley(paper: Paper) -> dict:
    authors = [
        {
            "first_name": " ".join(a.name.split()[:-1]),
            "last_name": a.name.split()[-1] if a.name.split() else a.name,
        }
        for a in paper.authors
    ]
    doc: dict = {
        "type": "journal",
        "title": paper.title,
        "authors": authors,
        "abstract": paper.abstract or "",
        "year": paper.year,
        "identifiers": {},
        "keywords": paper.fields_of_study[:10],
    }
    if paper.doi:
        doc["identifiers"]["doi"] = paper.doi
    if paper.arxiv_id:
        doc["identifiers"]["arxiv"] = paper.arxiv_id
    if paper.venue:
        doc["source"] = paper.venue
    return doc


def _mendeley_to_paper(item: dict) -> Paper:
    authors = [
        Author(name=f"{a.get('first_name', '')} {a.get('last_name', '')}".strip())
        for a in item.get("authors", [])
    ]
    ids = item.get("identifiers", {})
    return Paper(
        title=item.get("title", ""),
        authors=authors,
        year=item.get("year"),
        doi=ids.get("doi") or ids.get("DOI"),
        arxiv_id=ids.get("arxiv"),
        abstract=item.get("abstract"),
        venue=item.get("source"),
        source="mendeley",
        mendeley_id=item.get("id"),
        url=item.get("link"),
        fields_of_study=item.get("keywords", []),
    )


# ── Push (write to Mendeley) ──────────────────────────────────────────────────


async def sync_to_mendeley(
    papers: list[Paper],
    folder_name: str | None = None,
) -> SyncResult:
    token = await _get_token()
    if not token:
        return SyncResult(failed=len(papers), details=["Mendeley token not available"])

    result = SyncResult()
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Optionally get or create a folder
        folder_id = None
        if folder_name:
            folder_id = await _get_or_create_folder(client, token, folder_name)

        # Fetch existing DOIs to skip duplicates
        existing_dois = await _fetch_existing_dois(client, token)

        for paper in papers:
            if paper.doi and paper.doi.lower() in existing_dois:
                result.skipped += 1
                continue
            try:
                resp = await client.post(
                    f"{BASE}/documents",
                    headers=_auth_headers(token),
                    json=_paper_to_mendeley(paper),
                )
                resp.raise_for_status()
                doc_id = resp.json().get("id")
                result.synced += 1
                result.details.append(f"Added: {paper.title[:60]}")

                # Add to folder if specified
                if folder_id and doc_id:
                    await client.post(
                        f"{BASE}/folders/{folder_id}/documents",
                        headers=_auth_headers(token),
                        json={"id": doc_id},
                    )
            except Exception as exc:
                logger.warning("Mendeley add failed for '%s': %s", paper.title, exc)
                result.failed += 1

    return result


# ── Pull (read from Mendeley) ─────────────────────────────────────────────────


async def pull_from_mendeley(
    folder_name: str | None = None,
    limit: int = 100,
) -> list[Paper]:
    """Fetch papers from Mendeley library and return as Paper objects."""
    token = await _get_token()
    if not token:
        logger.warning("Mendeley token not available")
        return []

    async with httpx.AsyncClient(timeout=20.0) as client:
        headers = _auth_headers(token)

        if folder_name:
            folder_id = await _find_folder_id(client, token, folder_name)
            if not folder_id:
                logger.warning("Mendeley folder '%s' not found", folder_name)
                return []
            endpoint = f"{BASE}/folders/{folder_id}/documents"
        else:
            endpoint = f"{BASE}/documents"

        try:
            resp = await client.get(
                endpoint, headers=headers, params={"limit": min(limit, 500), "type": "journal"}
            )
            resp.raise_for_status()
            items = (
                resp.json() if isinstance(resp.json(), list) else resp.json().get("documents", [])
            )
            papers = []
            for item in items:
                # Full document details require another call
                doc_resp = await client.get(
                    f"{BASE}/documents/{item.get('id', item)}", headers=headers
                )
                if doc_resp.status_code == 200:
                    papers.append(_mendeley_to_paper(doc_resp.json()))
            return papers
        except Exception as exc:
            logger.warning("Mendeley pull failed: %s", exc)
            return []


# ── helpers ───────────────────────────────────────────────────────────────────


async def _fetch_existing_dois(client: httpx.AsyncClient, token: str) -> set[str]:
    try:
        resp = await client.get(
            f"{BASE}/documents", headers=_auth_headers(token), params={"limit": 200, "view": "all"}
        )
        resp.raise_for_status()
        items = resp.json() if isinstance(resp.json(), list) else []
        dois = set()
        for item in items:
            ids = item.get("identifiers", {})
            doi = ids.get("doi") or ids.get("DOI")
            if doi:
                dois.add(doi.lower())
        return dois
    except Exception:
        return set()


async def _get_or_create_folder(client: httpx.AsyncClient, token: str, name: str) -> str | None:
    fid = await _find_folder_id(client, token, name)
    if fid:
        return fid
    try:
        resp = await client.post(
            f"{BASE}/folders", headers=_auth_headers(token), json={"name": name}
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as exc:
        logger.warning("Mendeley folder create failed: %s", exc)
        return None


async def _find_folder_id(client: httpx.AsyncClient, token: str, name: str) -> str | None:
    try:
        resp = await client.get(f"{BASE}/folders", headers=_auth_headers(token))
        resp.raise_for_status()
        for folder in resp.json():
            if folder.get("name", "").lower() == name.lower():
                return folder.get("id")
    except Exception:
        pass
    return None
