"""arXiv connector — preprints via Atom API."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

from paper_distill_pro.models import Author, Paper

from .base import BaseConnector

logger = logging.getLogger(__name__)
BASE = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivConnector(BaseConnector):
    name = "arxiv"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        params = {
            "search_query": f"all:{quote(query)}",
            "max_results": min(max_results, 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            resp = await self._get(BASE, params=params)
            root = ET.fromstring(resp.text)
        except Exception as exc:
            logger.warning("arXiv search failed: %s", exc)
            return []

        results = []
        for entry in root.findall("atom:entry", NS):
            raw_id = entry.findtext("atom:id", "", NS)
            m = re.search(r"arxiv\.org/abs/([^\s]+)", raw_id)
            arxiv_id = m.group(1) if m else None
            published = entry.findtext("atom:published", "", NS)
            doi_elem = entry.find("arxiv:doi", NS)
            doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None
            results.append(
                Paper(
                    title=(entry.findtext("atom:title", "", NS) or "").replace("\n", " ").strip(),
                    authors=[
                        Author(name=a.findtext("atom:name", "", NS))
                        for a in entry.findall("atom:author", NS)
                    ],
                    year=self._safe_year(published[:4] if published else None),
                    arxiv_id=arxiv_id,
                    doi=doi,
                    abstract=(entry.findtext("atom:summary", "", NS) or "")
                    .replace("\n", " ")
                    .strip(),
                    source=self.name,
                    oa_url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
                    url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
                )
            )
        return results
