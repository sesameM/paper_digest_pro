"""Deduplication — three-level: DOI → arXiv ID → title hash."""

from __future__ import annotations

import re

from paper_distill_pro.models import Paper


def deduplicate(papers: list[Paper]) -> list[Paper]:
    seen: dict[str, Paper] = {}
    for paper in papers:
        key = paper.dedup_key
        if key not in seen:
            seen[key] = paper
        else:
            # Merge metadata from duplicate into the winner
            seen[key] = _merge(seen[key], paper)
    return list(seen.values())


def _merge(primary: Paper, secondary: Paper) -> Paper:
    merged = primary.model_copy()
    for attr in ("doi", "abstract", "oa_url", "pdf_url", "venue", "arxiv_id"):
        if not getattr(merged, attr) and getattr(secondary, attr):
            setattr(merged, attr, getattr(secondary, attr))
    if not merged.citation_count and secondary.citation_count:
        merged.citation_count = secondary.citation_count
    if not merged.fields_of_study and secondary.fields_of_study:
        merged.fields_of_study = secondary.fields_of_study
    return merged


def title_jaccard(a: str, b: str) -> float:
    ta = set(re.sub(r"[^a-z0-9]", " ", a.lower()).split())
    tb = set(re.sub(r"[^a-z0-9]", " ", b.lower()).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
