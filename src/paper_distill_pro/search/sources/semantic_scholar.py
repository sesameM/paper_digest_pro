"""Semantic Scholar connector — citation data + influence metrics."""

from __future__ import annotations

import logging

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper

from .base import BaseConnector

logger = logging.getLogger(__name__)
BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,authors,year,abstract,citationCount,externalIds,openAccessPdf,venue,fieldsOfStudy"


class SemanticScholarConnector(BaseConnector):
    name = "semantic_scholar"

    def _h(self) -> dict:
        h = {}
        if settings.semantic_scholar_api_key:
            h["x-api-key"] = settings.semantic_scholar_api_key
        return h

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {"query": query, "limit": min(max_results, 100), "fields": FIELDS}
        try:
            resp = await self._get(f"{BASE}/paper/search", params=params, headers=self._h())
            return [self._parse(item) for item in resp.json().get("data", []) if item.get("title")]
        except Exception as exc:
            logger.warning("S2 search failed: %s", exc)
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        try:
            resp = await self._get(
                f"{BASE}/paper/{paper_id}", params={"fields": FIELDS}, headers=self._h()
            )
            return self._parse(resp.json())
        except Exception as exc:
            logger.warning("S2 get_paper failed: %s", exc)
            return None

    async def get_citations(self, paper_id: str, limit: int = 50) -> list[Paper]:
        try:
            resp = await self._get(
                f"{BASE}/paper/{paper_id}/citations",
                params={"fields": FIELDS, "limit": limit},
                headers=self._h(),
            )
            return [
                self._parse(item["citingPaper"])
                for item in resp.json().get("data", [])
                if item.get("citingPaper", {}).get("title")
            ]
        except Exception as exc:
            logger.warning("S2 get_citations failed: %s", exc)
            return []

    async def get_references(self, paper_id: str, limit: int = 50) -> list[Paper]:
        try:
            resp = await self._get(
                f"{BASE}/paper/{paper_id}/references",
                params={"fields": FIELDS, "limit": limit},
                headers=self._h(),
            )
            return [
                self._parse(item["citedPaper"])
                for item in resp.json().get("data", [])
                if item.get("citedPaper", {}).get("title")
            ]
        except Exception as exc:
            logger.warning("S2 get_references failed: %s", exc)
            return []

    def _parse(self, item: dict) -> Paper:
        ext = item.get("externalIds") or {}
        oa = item.get("openAccessPdf") or {}
        return Paper(
            title=item.get("title") or "",
            authors=[Author(name=a.get("name", "")) for a in item.get("authors", [])],
            year=self._safe_year(item.get("year")),
            doi=ext.get("DOI"),
            arxiv_id=ext.get("ArXiv"),
            abstract=item.get("abstract"),
            citation_count=self._safe_int(item.get("citationCount")),
            source=self.name,
            oa_url=oa.get("url"),
            pdf_url=oa.get("url"),
            venue=item.get("venue"),
            fields_of_study=item.get("fieldsOfStudy") or [],
        )
