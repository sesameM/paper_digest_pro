"""IEEE Xplore, ACM Digital Library, and SSRN connectors."""

from __future__ import annotations

import logging
import re

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper

from .base import BaseConnector

logger = logging.getLogger(__name__)


# ── IEEE Xplore ───────────────────────────────────────────────────────────────


class IEEEConnector(BaseConnector):
    """
    IEEE Xplore Digital Library connector.
    Free API key: https://developer.ieee.org/
    Without a key the connector still works but rate-limited to 200 results/day.
    """

    name = "ieee"
    BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        if not settings.ieee_api_key:
            logger.info("IEEE_API_KEY not set — IEEE connector skipped")
            return []

        params = {
            "apikey": settings.ieee_api_key,
            "querytext": query,
            "max_records": min(max_results, 200),
            "datatype": "json",
            "sortfield": "article_number",
            "sortorder": "desc",
        }
        try:
            resp = await self._get(self.BASE, params=params)
            articles = resp.json().get("articles", [])
        except Exception as exc:
            logger.warning("IEEE search failed: %s", exc)
            return []

        results: list[Paper] = []
        for item in articles:
            doi = item.get("doi")
            arxiv_id = None
            authors = []
            for auth in item.get("authors", {}).get("authors", []):
                authors.append(
                    Author(name=auth.get("full_name", ""), affiliation=auth.get("affiliation"))
                )
            results.append(
                Paper(
                    title=item.get("title", ""),
                    authors=authors,
                    year=self._safe_year(item.get("publication_year")),
                    doi=doi,
                    arxiv_id=arxiv_id,
                    abstract=item.get("abstract"),
                    citation_count=self._safe_int(item.get("citing_paper_count")),
                    source=self.name,
                    ieee_id=str(item.get("article_number", "")),
                    venue=item.get("publication_title"),
                    url=item.get("pdf_url") or item.get("html_url"),
                    pdf_url=item.get("pdf_url"),
                    oa_url=item.get("pdf_url")
                    if item.get("access_type") == "OPEN_ACCESS"
                    else None,
                    fields_of_study=item.get("index_terms", {})
                    .get("ieee_terms", {})
                    .get("terms", [])[:5],
                )
            )
        return results


# ── ACM Digital Library ───────────────────────────────────────────────────────


class ACMConnector(BaseConnector):
    """
    ACM Digital Library connector via the public search API.
    The ACM API does not require authentication for basic metadata search.
    Full text access requires institutional access.
    """

    name = "acm"
    BASE = "https://dl.acm.org/action/doSearch"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        # ACM offers a JSON-LD endpoint through their search
        params = {
            "AllField": query,
            "pageSize": min(max_results, 50),
            "startPage": 0,
            "sortBy": "relevancy",
        }
        headers = {"Accept": "application/json"}
        try:
            resp = await self._get(self.BASE, params=params, headers=headers)
            # ACM returns HTML by default; attempt JSON parsing
            data = resp.json()
            items = data.get("items", data.get("results", []))
        except Exception:
            # Fallback: scrape structured metadata from HTML response using regex
            try:
                resp = await self._get(self.BASE, params=params)
                items = self._parse_acm_html(resp.text, max_results)
                return items
            except Exception as exc:
                logger.warning("ACM search failed: %s", exc)
                return []

        results: list[Paper] = []
        for item in items:
            doi = item.get("doi")
            results.append(
                Paper(
                    title=item.get("title", ""),
                    authors=[Author(name=a.get("name", "")) for a in item.get("authors", [])],
                    year=self._safe_year(item.get("publicationDate", "")[:4]),
                    doi=doi,
                    abstract=item.get("abstract"),
                    citation_count=self._safe_int(item.get("citationCount")),
                    source=self.name,
                    acm_id=item.get("id", ""),
                    venue=item.get("parentPublication", {}).get("title"),
                    url=f"https://dl.acm.org/doi/{doi}" if doi else None,
                )
            )
        return results

    def _parse_acm_html(self, html: str, max_results: int) -> list[Paper]:
        """Extract paper metadata from ACM search HTML using patterns."""
        results: list[Paper] = []

        # Extract DOIs
        doi_pattern = re.findall(r'data-doi="(10\.\d{4,}/[^\s"]+)"', html)
        title_pattern = re.findall(r'class="hlFld-Title"[^>]*>\s*<a[^>]*>([^<]+)</a>', html)
        year_pattern = re.findall(r'<span class="dot-separator">\s*(\d{4})\s*</span>', html)

        for i, doi in enumerate(doi_pattern[:max_results]):
            title = title_pattern[i] if i < len(title_pattern) else f"ACM Paper {doi}"
            year = self._safe_year(year_pattern[i]) if i < len(year_pattern) else None
            results.append(
                Paper(
                    title=title.strip(),
                    year=year,
                    doi=doi,
                    source=self.name,
                    url=f"https://dl.acm.org/doi/{doi}",
                )
            )
        return results


# ── SSRN (Social Science Research Network) ───────────────────────────────────


class SSRNConnector(BaseConnector):
    """
    SSRN connector — social science, economics, law, finance preprints.
    Uses the public Elsevier/SSRN search API (no key required for metadata).
    """

    name = "ssrn"
    BASE = "https://api.ssrn.com/content/latest/v1/papers"
    SEARCH_BASE = "https://papers.ssrn.com/sol3/results.cfm"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        # SSRN primary API (requires key for full access)
        if settings.ssrn_api_key:
            return await self._search_with_api(query, max_results)
        else:
            return await self._search_public(query, max_results)

    async def _search_with_api(self, query: str, max_results: int) -> list[Paper]:
        headers = {"Authorization": f"Bearer {settings.ssrn_api_key}"}
        params = {"q": query, "limit": min(max_results, 100)}
        try:
            resp = await self._get(self.BASE, params=params, headers=headers)
            items = resp.json().get("papers", resp.json().get("items", []))
            return [self._parse_api_item(item) for item in items]
        except Exception as exc:
            logger.warning("SSRN API search failed: %s", exc)
            return []

    async def _search_public(self, query: str, max_results: int) -> list[Paper]:
        """Fallback: scrape SSRN public search page for metadata."""
        params = {
            "txt": query,
            "form_name": "journalBrowse",
            "journal_id": 0,
            "Network_ID": 0,
            "start": 0,
            "orderBy": "Rank",
        }
        try:
            resp = await self._get(self.SEARCH_BASE, params=params)
            return self._parse_ssrn_html(resp.text, max_results)
        except Exception as exc:
            logger.warning("SSRN public search failed: %s", exc)
            return []

    def _parse_api_item(self, item: dict) -> Paper:
        ssrn_id = str(item.get("id", ""))
        return Paper(
            title=item.get("title", ""),
            authors=[Author(name=a.get("name", "")) for a in item.get("authors", [])],
            year=self._safe_year((item.get("submissionDate") or item.get("date", ""))[:4]),
            doi=item.get("doi"),
            abstract=item.get("abstract"),
            citation_count=self._safe_int(item.get("downloads")),  # SSRN uses downloads as proxy
            source=self.name,
            ssrn_id=ssrn_id,
            url=f"https://papers.ssrn.com/abstract={ssrn_id}" if ssrn_id else None,
        )

    def _parse_ssrn_html(self, html: str, max_results: int) -> list[Paper]:
        results: list[Paper] = []
        # Extract SSRN paper IDs and titles from HTML
        id_pattern = re.findall(r"abstract_id=(\d+)", html)
        title_pattern = re.findall(r'class="title"[^>]*>\s*<a[^>]*>([^<]+)</a>', html)
        date_pattern = re.findall(r"Date Written:\s*(\w+ \d+, \d{4})", html)

        seen = set()
        for i, ssrn_id in enumerate(id_pattern[:max_results]):
            if ssrn_id in seen:
                continue
            seen.add(ssrn_id)
            title = title_pattern[i].strip() if i < len(title_pattern) else f"SSRN Paper {ssrn_id}"
            year = None
            if i < len(date_pattern):
                year_m = re.search(r"(\d{4})", date_pattern[i])
                year = int(year_m.group(1)) if year_m else None
            results.append(
                Paper(
                    title=title,
                    year=year,
                    source=self.name,
                    ssrn_id=ssrn_id,
                    url=f"https://papers.ssrn.com/abstract={ssrn_id}",
                )
            )
        return results
