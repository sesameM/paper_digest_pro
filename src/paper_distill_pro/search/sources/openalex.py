"""OpenAlex connector — 250M+ works, fully open."""

from __future__ import annotations

import logging

from paper_distill_pro.models import Author, Paper

from .base import BaseConnector

logger = logging.getLogger(__name__)
BASE = "https://api.openalex.org/works"


class OpenAlexConnector(BaseConnector):
    name = "openalex"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {
            "search": query,
            "per-page": min(max_results, 50),
            "select": "id,title,authorships,publication_year,doi,abstract_inverted_index,"
            "cited_by_count,primary_location,open_access,concepts",
            "sort": "cited_by_count:desc",
        }
        try:
            resp = await self._get(BASE, params=params)
            data = resp.json()
        except Exception as exc:
            logger.warning("OpenAlex search failed: %s", exc)
            return []

        results: list[Paper] = []
        for item in data.get("results", []):
            abstract = self._rebuild_abstract(item.get("abstract_inverted_index"))
            doi = (item.get("doi") or "").replace("https://doi.org/", "") or None
            oa = item.get("open_access", {})
            venue = (item.get("primary_location") or {}).get("source", {}).get("display_name")
            results.append(
                Paper(
                    title=item.get("title") or "",
                    authors=[
                        Author(
                            name=a.get("author", {}).get("display_name", ""),
                            orcid=a.get("author", {}).get("orcid"),
                        )
                        for a in item.get("authorships", [])
                    ],
                    year=self._safe_year(item.get("publication_year")),
                    doi=doi,
                    abstract=abstract,
                    citation_count=self._safe_int(item.get("cited_by_count")),
                    source=self.name,
                    oa_url=oa.get("oa_url"),
                    venue=venue,
                    url=item.get("id"),
                    fields_of_study=[
                        c.get("display_name", "") for c in item.get("concepts", [])[:5]
                    ],
                )
            )
        return results

    @staticmethod
    def _rebuild_abstract(inv: dict | None) -> str | None:
        if not inv:
            return None
        positions: dict[int, str] = {}
        for word, pos_list in inv.items():
            for pos in pos_list:
                positions[pos] = word
        return " ".join(positions[i] for i in sorted(positions))
