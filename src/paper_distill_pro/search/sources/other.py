"""PubMed, CrossRef, EuropePMC, bioRxiv, DBLP, PapersWithCode connectors."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper

from .base import BaseConnector

logger = logging.getLogger(__name__)


# ── PubMed ────────────────────────────────────────────────────────────────────


class PubMedConnector(BaseConnector):
    name = "pubmed"
    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def _bp(self) -> dict:
        p: dict = {}
        if settings.pubmed_api_key:
            p["api_key"] = settings.pubmed_api_key
        return p

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        try:
            params = {
                **self._bp(),
                "db": "pubmed",
                "term": query,
                "retmax": min(max_results, 100),
                "retmode": "json",
                "sort": "relevance",
            }
            ids = (
                (await self._get(self.ESEARCH, params=params))
                .json()
                .get("esearchresult", {})
                .get("idlist", [])
            )
        except Exception as exc:
            logger.warning("PubMed esearch failed: %s", exc)
            return []
        if not ids:
            return []
        try:
            params2 = {**self._bp(), "db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
            root = ET.fromstring((await self._get(self.EFETCH, params=params2)).text)
        except Exception as exc:
            logger.warning("PubMed efetch failed: %s", exc)
            return []
        results = []
        for article in root.findall(".//PubmedArticle"):
            med = article.find(".//MedlineCitation")
            art = med.find("Article") if med is not None else None
            if not art:
                continue
            title = (
                "".join(art.find("ArticleTitle").itertext())
                if art.find("ArticleTitle") is not None
                else ""
            )
            abstract_elem = art.find(".//AbstractText")
            abstract = "".join(abstract_elem.itertext()) if abstract_elem is not None else None
            authors = []
            for auth in art.findall(".//Author"):
                last, fore = auth.findtext("LastName", ""), auth.findtext("ForeName", "")
                name = f"{fore} {last}".strip()
                if name:
                    authors.append(Author(name=name))
            year_str = (art.find(".//PubDate") or ET.Element("")).findtext("Year", "")
            doi = None
            for id_elem in article.findall(".//ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text
                    break
            pmid = med.findtext("PMID") if med is not None else None
            results.append(
                Paper(
                    title=title.strip(),
                    authors=authors,
                    year=self._safe_year(year_str),
                    doi=doi,
                    abstract=abstract,
                    source=self.name,
                    pubmed_id=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                )
            )
        return results


# ── CrossRef ──────────────────────────────────────────────────────────────────


class CrossRefConnector(BaseConnector):
    name = "crossref"
    BASE = "https://api.crossref.org/works"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {
            "query": query,
            "rows": min(max_results, 100),
            "select": "title,author,published,DOI,abstract,is-referenced-by-count,container-title,URL",
            "sort": "relevance",
        }
        try:
            items = (
                (await self._get(self.BASE, params=params))
                .json()
                .get("message", {})
                .get("items", [])
            )
        except Exception as exc:
            logger.warning("CrossRef search failed: %s", exc)
            return []
        results = []
        for item in items:
            titles = item.get("title") or []
            title = titles[0] if titles else ""
            if not title:
                continue
            pub = item.get("published") or {}
            dp = pub.get("date-parts") or [[]]
            year = self._safe_year(dp[0][0] if dp[0] else None)
            authors = [
                Author(name=f"{a.get('given', '')} {a.get('family', '')}".strip())
                for a in item.get("author", [])
            ]
            ct = item.get("container-title") or []
            results.append(
                Paper(
                    title=title,
                    authors=authors,
                    year=year,
                    doi=item.get("DOI"),
                    abstract=item.get("abstract"),
                    citation_count=self._safe_int(item.get("is-referenced-by-count")),
                    source=self.name,
                    venue=ct[0] if ct else None,
                    url=item.get("URL"),
                )
            )
        return results


# ── Europe PMC ────────────────────────────────────────────────────────────────


class EuropePMCConnector(BaseConnector):
    name = "europe_pmc"
    BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {
            "query": query,
            "format": "json",
            "resulttype": "lite",
            "pageSize": min(max_results, 100),
            "sort": "CITED desc",
        }
        try:
            results_list = (
                (await self._get(self.BASE, params=params))
                .json()
                .get("resultList", {})
                .get("result", [])
            )
        except Exception as exc:
            logger.warning("EuropePMC search failed: %s", exc)
            return []
        return [
            Paper(
                title=item.get("title", "").rstrip("."),
                authors=[Author(name=a) for a in (item.get("authorString") or "").split(", ") if a],
                year=self._safe_year(item.get("pubYear")),
                doi=item.get("doi"),
                abstract=item.get("abstractText"),
                citation_count=self._safe_int(item.get("citedByCount")),
                source=self.name,
                url=f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}",
            )
            for item in results_list
        ]


# ── bioRxiv ───────────────────────────────────────────────────────────────────


class BioRxivConnector(BaseConnector):
    name = "biorxiv"
    BASE = "https://api.biorxiv.org/details/biorxiv"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        from datetime import datetime, timedelta

        since = (datetime.utcnow() - timedelta(days=120)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            resp = await self._get(
                f"{self.BASE}/{since}/{today}/0/{min(max_results * 4, 200)}/json"
            )
            papers_raw = resp.json().get("collection", [])
        except Exception as exc:
            logger.warning("bioRxiv search failed: %s", exc)
            return []
        kw = query.lower().split()
        results = []
        for item in papers_raw:
            combined = ((item.get("title") or "") + " " + (item.get("abstract") or "")).lower()
            if not any(k in combined for k in kw):
                continue
            doi = item.get("doi", "")
            results.append(
                Paper(
                    title=item.get("title", ""),
                    authors=[
                        Author(name=a.get("name", ""))
                        for a in (item.get("authors", {}).get("parse", []) or [])
                    ],
                    year=self._safe_year((item.get("date") or "")[:4]),
                    doi=doi or None,
                    abstract=item.get("abstract"),
                    source=self.name,
                    url=f"https://www.biorxiv.org/content/{doi}" if doi else None,
                    pdf_url=f"https://www.biorxiv.org/content/{doi}.full.pdf" if doi else None,
                )
            )
            if len(results) >= max_results:
                break
        return results


# ── DBLP ─────────────────────────────────────────────────────────────────────


class DBLPConnector(BaseConnector):
    name = "dblp"
    BASE = "https://dblp.org/search/publ/api"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {"q": query, "format": "json", "h": min(max_results, 100)}
        try:
            hits = (
                (await self._get(self.BASE, params=params))
                .json()
                .get("result", {})
                .get("hits", {})
                .get("hit", [])
            )
        except Exception as exc:
            logger.warning("DBLP search failed: %s", exc)
            return []
        results = []
        for hit in hits:
            info = hit.get("info", {})
            title = info.get("title", "")
            if not title:
                continue
            authors_raw = info.get("authors", {}).get("author", [])
            if isinstance(authors_raw, (str, dict)):
                authors_raw = [authors_raw]
            authors = [
                Author(name=a.get("text", "") if isinstance(a, dict) else a) for a in authors_raw
            ]
            results.append(
                Paper(
                    title=title.rstrip("."),
                    authors=authors,
                    year=self._safe_year(info.get("year")),
                    doi=info.get("doi"),
                    source=self.name,
                    venue=info.get("venue"),
                    url=info.get("url"),
                )
            )
        return results


# ── Papers with Code ──────────────────────────────────────────────────────────


class PapersWithCodeConnector(BaseConnector):
    name = "papers_with_code"
    BASE = "https://paperswithcode.com/api/v1/papers"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {"q": query, "items_per_page": min(max_results, 50)}
        try:
            items = (await self._get(self.BASE, params=params)).json().get("results", [])
        except Exception as exc:
            logger.warning("PapersWithCode search failed: %s", exc)
            return []
        return [
            Paper(
                title=item.get("title", ""),
                authors=[Author(name=a) for a in item.get("authors", [])],
                year=self._safe_year((item.get("published") or "")[:4]),
                arxiv_id=item.get("arxiv_id"),
                abstract=item.get("abstract"),
                citation_count=self._safe_int(item.get("paper_citations")),
                source=self.name,
                url=item.get("url_pdf"),
                pdf_url=item.get("url_pdf"),
            )
            for item in items
        ]
