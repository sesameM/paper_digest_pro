"""Connector registry — all 11 academic source connectors."""

from __future__ import annotations

from .arxiv import ArxivConnector
from .base import BaseConnector
from .openalex import OpenAlexConnector
from .other import (
    BioRxivConnector,
    CrossRefConnector,
    DBLPConnector,
    EuropePMCConnector,
    PapersWithCodeConnector,
    PubMedConnector,
)
from .premium import ACMConnector, IEEEConnector, SSRNConnector
from .semantic_scholar import SemanticScholarConnector

ALL_CONNECTORS: dict[str, type[BaseConnector]] = {
    "openalex": OpenAlexConnector,
    "arxiv": ArxivConnector,
    "semantic_scholar": SemanticScholarConnector,
    "pubmed": PubMedConnector,
    "crossref": CrossRefConnector,
    "europe_pmc": EuropePMCConnector,
    "biorxiv": BioRxivConnector,
    "dblp": DBLPConnector,
    "papers_with_code": PapersWithCodeConnector,
    "ieee": IEEEConnector,
    "acm": ACMConnector,
    "ssrn": SSRNConnector,
}

# Default sources that work without API keys
FREE_SOURCES = [
    "openalex",
    "arxiv",
    "semantic_scholar",
    "pubmed",
    "crossref",
    "europe_pmc",
    "biorxiv",
    "dblp",
    "papers_with_code",
]

# Sources that need API keys
PREMIUM_SOURCES = ["ieee", "acm", "ssrn"]


def get_connectors(names: list[str] | None = None) -> list[BaseConnector]:
    selected = names if names else list(ALL_CONNECTORS.keys())
    return [ALL_CONNECTORS[n]() for n in selected if n in ALL_CONNECTORS]


__all__ = [
    "BaseConnector",
    "ALL_CONNECTORS",
    "FREE_SOURCES",
    "PREMIUM_SOURCES",
    "get_connectors",
]
