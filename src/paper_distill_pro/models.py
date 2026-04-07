"""All Pydantic data models for paper-distill-pro."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    name: str
    affiliation: str | None = None
    orcid: str | None = None


class Paper(BaseModel):
    title: str
    authors: list[Author] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    citation_count: int = 0
    source: str = ""
    oa_url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    url: str | None = None
    score: float = 0.0
    fields_of_study: list[str] = Field(default_factory=list)
    # extra identifiers for specific sources
    pubmed_id: str | None = None
    ieee_id: str | None = None
    acm_id: str | None = None
    ssrn_id: str | None = None
    mendeley_id: str | None = None
    zotero_key: str | None = None

    @property
    def dedup_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id.strip()}"
        norm = re.sub(r"[^a-z0-9]", "", self.title.lower())
        return f"title:{norm[:50]}_{self.year}"

    @property
    def author_names(self) -> list[str]:
        return [a.name for a in self.authors]

    def short_ref(self) -> str:
        first = self.authors[0].name.split()[-1] if self.authors else "Unknown"
        return (
            f"{first} et al. ({self.year})" if len(self.authors) > 1 else f"{first} ({self.year})"
        )


class Sections(BaseModel):
    paper_id: str = ""
    abstract: str | None = None
    introduction: str | None = None
    methods: str | None = None
    results: str | None = None
    discussion: str | None = None
    conclusion: str | None = None
    references: list[str] = Field(default_factory=list)
    raw_text: str | None = None
    page_count: int = 0


class CitationTree(BaseModel):
    root: Paper
    citing: list[Paper] = Field(default_factory=list)
    references: list[Paper] = Field(default_factory=list)
    influential: list[Paper] = Field(default_factory=list)


class TrendReport(BaseModel):
    keyword: str
    annual_counts: dict[int, int] = Field(default_factory=dict)
    annual_citations: dict[int, int] = Field(default_factory=dict)
    cagr_papers: float = 0.0
    cagr_citations: float = 0.0
    top_papers: list[Paper] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SyncResult(BaseModel):
    synced: int = 0
    skipped: int = 0
    updated: int = 0
    failed: int = 0
    details: list[str] = Field(default_factory=list)


# ── Push / Digest ────────────────────────────────────────────────────────────


class DigestConfig(BaseModel):
    keywords: list[str]
    max_papers_per_keyword: int = 5
    since_days: int = 7
    min_citation_count: int = 0
    sources: list[str] = Field(default_factory=list)


class DigestSection(BaseModel):
    keyword: str
    papers: list[Paper]


class Digest(BaseModel):
    title: str
    date: str
    sections: list[DigestSection]
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def total_papers(self) -> int:
        return sum(len(s.papers) for s in self.sections)
