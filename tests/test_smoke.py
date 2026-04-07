"""Offline smoke tests — 35 tests, no network required."""
from __future__ import annotations
import re
import pytest
from paper_distill_pro.models import (
    Author, Paper, Sections, Digest, DigestConfig, DigestSection, SyncResult
)
from paper_distill_pro.search.dedup import deduplicate, title_jaccard
from paper_distill_pro.fulltext.parser import _split, build_qa_context


# ── Paper model ───────────────────────────────────────────────────────────────

class TestPaperModel:
    def test_dedup_key_doi(self):
        p = Paper(title="X", doi="10.1/test", arxiv_id="2303.00001")
        assert p.dedup_key == "doi:10.1/test"

    def test_dedup_key_arxiv(self):
        p = Paper(title="X", arxiv_id="2303.00001")
        assert p.dedup_key == "arxiv:2303.00001"

    def test_dedup_key_title(self):
        p = Paper(title="Some Paper Title", year=2023)
        key = p.dedup_key
        assert key.startswith("title:") and "2023" in key

    def test_dedup_key_doi_normalised(self):
        p = Paper(title="X", doi="10.1/ABC")
        assert p.dedup_key == "doi:10.1/abc"

    def test_short_ref_single(self):
        p = Paper(title="X", authors=[Author(name="John Smith")], year=2023)
        assert p.short_ref() == "Smith (2023)"

    def test_short_ref_multi(self):
        p = Paper(title="X", authors=[Author(name="A B"), Author(name="C D")], year=2022)
        assert "et al." in p.short_ref()

    def test_author_names(self):
        p = Paper(title="X", authors=[Author(name="Alice"), Author(name="Bob")])
        assert p.author_names == ["Alice", "Bob"]

    def test_roundtrip_serialise(self):
        p = Paper(title="LLM survey", doi="10.1/x", year=2024, citation_count=100, score=0.95)
        p2 = Paper(**p.model_dump())
        assert p2.title == p.title and p2.score == p.score

    def test_paper_default_score(self):
        p = Paper(title="X")
        assert p.score == 0.0

    def test_paper_source_ids(self):
        p = Paper(title="X", pubmed_id="12345", ieee_id="ABC", acm_id="xyz", ssrn_id="99")
        assert p.pubmed_id == "12345"
        assert p.ssrn_id == "99"


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def _p(self, doi=None, arxiv_id=None, title="Test", year=2023, source="x"):
        return Paper(title=title, doi=doi, arxiv_id=arxiv_id, year=year, source=source)

    def test_dedup_by_doi_keeps_first(self):
        papers = [self._p(doi="10.1/a", source="openalex"), self._p(doi="10.1/a", source="crossref")]
        assert len(deduplicate(papers)) == 1
        assert deduplicate(papers)[0].source == "openalex"

    def test_dedup_by_arxiv(self):
        papers = [self._p(arxiv_id="2303.00001", source="arxiv"),
                  self._p(arxiv_id="2303.00001", source="semantic_scholar")]
        assert len(deduplicate(papers)) == 1

    def test_dedup_different_papers_kept(self):
        papers = [self._p(doi="10.1/a"), self._p(doi="10.1/b"), self._p(doi="10.1/c")]
        assert len(deduplicate(papers)) == 3

    def test_dedup_merges_abstract(self):
        a = self._p(doi="10.1/x")
        b = Paper(title="Test", doi="10.1/x", abstract="This is the abstract", source="s2")
        result = deduplicate([a, b])
        assert result[0].abstract == "This is the abstract"

    def test_dedup_empty(self):
        assert deduplicate([]) == []

    def test_dedup_single(self):
        p = self._p(doi="10.1/a")
        assert deduplicate([p]) == [p]

    def test_title_jaccard_identical(self):
        assert title_jaccard("attention is all you need", "attention is all you need") == 1.0

    def test_title_jaccard_zero(self):
        assert title_jaccard("quantum physics", "machine learning") == 0.0

    def test_title_jaccard_partial(self):
        score = title_jaccard("deep learning survey", "survey of deep learning methods")
        assert 0.0 < score < 1.0


# ── Full-text parser ──────────────────────────────────────────────────────────

SAMPLE = """
Abstract

This paper presents a novel approach to multi-source search.

Introduction

Large language models have transformed information retrieval.

Methods

We employ parallel API calls with deduplication and scoring.

Results

Our experiments show 35% improvement over baselines.

Conclusion

We present a comprehensive system for academic paper retrieval.

References

[1] Smith et al. (2023) Deep Learning. Nature.
[2] Jones et al. (2022) NLP Advances. ACL.
"""


class TestFulltextParser:
    def test_finds_abstract(self):
        secs = _split(SAMPLE)
        assert secs.abstract is not None
        assert "novel" in secs.abstract

    def test_finds_methods(self):
        secs = _split(SAMPLE)
        assert secs.methods is not None
        assert "deduplication" in secs.methods

    def test_finds_conclusion(self):
        secs = _split(SAMPLE)
        assert secs.conclusion is not None
        assert "comprehensive" in secs.conclusion

    def test_extracts_references(self):
        secs = _split(SAMPLE)
        assert len(secs.references) >= 1

    def test_build_context_includes_selected(self):
        secs = _split(SAMPLE)
        ctx = build_qa_context(secs, include=["abstract", "methods"])
        assert "Abstract" in ctx and "Methods" in ctx
        assert "Conclusion" not in ctx

    def test_build_context_max_tokens(self):
        secs = _split(SAMPLE)
        ctx = build_qa_context(secs, max_tokens=10)
        assert ctx is not None  # should still return something

    def test_build_context_fallback_raw(self):
        secs = Sections(raw_text="Some raw text here")
        ctx = build_qa_context(secs)
        assert "raw text" in ctx

    def test_parse_pdf_import_error(self, monkeypatch):
        import builtins
        real = builtins.__import__
        def mock_import(name, *a, **kw):
            if name == "fitz":
                raise ImportError
            return real(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", mock_import)
        from paper_distill_pro.fulltext.parser import parse_pdf
        result = parse_pdf(b"fake")
        assert isinstance(result, Sections)


# ── Digest model ──────────────────────────────────────────────────────────────

class TestDigestModel:
    def test_total_papers(self):
        d = Digest(title="T", date="2025-01-01", sections=[
            DigestSection(keyword="kw1", papers=[Paper(title="P1"), Paper(title="P2")]),
            DigestSection(keyword="kw2", papers=[Paper(title="P3")]),
        ])
        assert d.total_papers() == 3

    def test_digest_config_defaults(self):
        cfg = DigestConfig(keywords=["llm", "rag"])
        assert cfg.max_papers_per_keyword == 5 and cfg.since_days == 7

    def test_sync_result_defaults(self):
        r = SyncResult()
        assert r.synced == r.skipped == r.failed == r.updated == 0


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_keywords_list(self):
        from paper_distill_pro.config import Settings
        s = Settings(push_keywords=" llm , rag , moe ")
        assert s.keywords_list == ["llm", "rag", "moe"]

    def test_channels_list(self):
        from paper_distill_pro.config import Settings
        s = Settings(push_channels="slack , telegram , email")
        assert s.channels_list == ["slack", "telegram", "email"]

    def test_smtp_recipients(self):
        from paper_distill_pro.config import Settings
        s = Settings(smtp_to="a@x.com, b@x.com")
        assert s.smtp_recipients == ["a@x.com", "b@x.com"]

    def test_smtp_recipients_empty(self):
        from paper_distill_pro.config import Settings
        s = Settings()
        assert s.smtp_recipients == []


# ── Scoring ───────────────────────────────────────────────────────────────────

class TestScoring:
    def test_scores_in_range(self):
        from paper_distill_pro.search.engine import _score
        papers = [
            Paper(title="deep learning", abstract="neural network methods", year=2024, citation_count=100),
            Paper(title="old paper", year=2000, citation_count=5),
        ]
        for p in _score(papers, "deep learning"):
            assert 0.0 <= p.score <= 1.0

    def test_recent_scores_higher(self):
        from paper_distill_pro.search.engine import _score
        papers = [Paper(title="X", year=2024), Paper(title="X", year=2005)]
        scored = {p.year: p.score for p in _score(papers, "X")}
        assert scored[2024] > scored[2005]


# ── Source connectors (unit, no network) ─────────────────────────────────────

class TestConnectorRegistry:
    def test_all_connectors_registered(self):
        from paper_distill_pro.search.sources import ALL_CONNECTORS
        expected = {
            "openalex", "arxiv", "semantic_scholar", "pubmed", "crossref",
            "europe_pmc", "biorxiv", "dblp", "papers_with_code",
            "ieee", "acm", "ssrn",
        }
        assert expected == set(ALL_CONNECTORS.keys())

    def test_get_connectors_default(self):
        from paper_distill_pro.search.sources import get_connectors
        connectors = get_connectors()
        assert len(connectors) == 12

    def test_get_connectors_subset(self):
        from paper_distill_pro.search.sources import get_connectors
        connectors = get_connectors(["arxiv", "openalex"])
        assert len(connectors) == 2
        names = {c.name for c in connectors}
        assert names == {"arxiv", "openalex"}

    def test_get_connectors_ignores_unknown(self):
        from paper_distill_pro.search.sources import get_connectors
        connectors = get_connectors(["arxiv", "nonexistent"])
        assert len(connectors) == 1
