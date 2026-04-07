"""Shared pytest fixtures."""
import pytest
from paper_distill_pro.models import Author, Paper


@pytest.fixture
def sample_paper():
    return Paper(
        title="Attention Is All You Need",
        authors=[Author(name="Ashish Vaswani"), Author(name="Noam Shazeer")],
        year=2017,
        doi="10.48550/arXiv.1706.03762",
        arxiv_id="1706.03762",
        abstract="The dominant sequence transduction models are based on complex recurrent networks.",
        citation_count=80000,
        source="semantic_scholar",
        venue="NeurIPS",
        fields_of_study=["Computer Science", "Natural Language Processing"],
    )


@pytest.fixture
def sample_papers(sample_paper):
    return [
        sample_paper,
        Paper(title="BERT", authors=[Author(name="Jacob Devlin")], year=2018,
              arxiv_id="1810.04805", citation_count=50000, source="arxiv"),
        Paper(title="GPT-3", authors=[Author(name="Tom Brown")], year=2020,
              doi="10.48550/arXiv.2005.14165", citation_count=30000, source="openalex"),
    ]
