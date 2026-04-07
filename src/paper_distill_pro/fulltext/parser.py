"""PDF parser — extract structured sections using PyMuPDF + optional LLM sub-agent."""

from __future__ import annotations

import logging
import re

from paper_distill_pro.models import Paper, Sections

from .sub_agent import parse_with_llm

logger = logging.getLogger(__name__)

_SECTION_PATTERNS: list[tuple[str, str]] = [
    ("abstract", r"^[\s\d\.]*Abstract\s*$"),
    ("introduction", r"^[\s\d\.]*Introduction\s*$"),
    ("methods", r"^[\s\d\.]*Method(olog(y|ies))?s?\s*$|^[\s\d\.]*Materials?\s+and\s+Methods?\s*$"),
    ("results", r"^[\s\d\.]*Results?\s*$"),
    ("discussion", r"^[\s\d\.]*Discussion\s*$"),
    ("conclusion", r"^[\s\d\.]*Conclusions?\s*$"),
    ("references", r"^[\s\d\.]*References?\s*$|^[\s\d\.]*Bibliography\s*$"),
]

MAX_SECTION_CHARS = 8_000
MAX_RAW_CHARS = 60_000


def parse_pdf(pdf_bytes: bytes, paper: Paper | None = None) -> Sections:
    """
    Extract structured sections from a PDF using regex-based heuristics.
    For LLM-enhanced extraction, use :func:`parse_pdf_llm` instead.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return Sections()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = [page.get_text("text") for page in doc]
        full_text = "\n".join(pages_text)
        page_count = len(doc)
        doc.close()
    except Exception as exc:
        logger.warning("PDF parsing failed: %s", exc)
        return Sections()

    sections = _split(full_text)
    sections.raw_text = full_text[:MAX_RAW_CHARS]
    sections.page_count = page_count
    if paper:
        sections.paper_id = paper.dedup_key
    return sections


async def parse_pdf_llm(pdf_bytes: bytes, paper: Paper | None = None) -> Sections:
    """
    Extract structured sections from a PDF using an LLM sub-agent.

    Attempts LLM parsing first (if SUB_AGENT_API_KEY is configured), then
    falls back to regex-based extraction if the API call fails.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return Sections()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = [page.get_text("text") for page in doc]
        full_text = "\n".join(pages_text)
        page_count = len(doc)
        doc.close()
    except Exception as exc:
        logger.warning("PDF parsing failed: %s", exc)
        return Sections()

    title = paper.title if paper else ""

    # Try LLM parsing first
    llm_sections = await parse_with_llm(full_text, paper_title=title)
    if llm_sections:
        llm_sections.page_count = page_count
        if paper:
            llm_sections.paper_id = paper.dedup_key
        return llm_sections

    # Fallback to regex
    sections = _split(full_text)
    sections.raw_text = full_text[:MAX_RAW_CHARS]
    sections.page_count = page_count
    if paper:
        sections.paper_id = paper.dedup_key
    return sections


def _split(text: str) -> Sections:
    positions: list[tuple[int, str]] = []
    for name, pattern in _SECTION_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL):
            positions.append((m.start(), name))

    if not positions:
        return _heuristic(text)

    positions.sort(key=lambda x: x[0])
    seen: set[str] = set()
    deduped: list[tuple[int, str]] = []
    for pos, name in positions:
        if name not in seen:
            seen.add(name)
            deduped.append((pos, name))

    section_texts: dict[str, str] = {}
    for i, (start, name) in enumerate(deduped):
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        section_texts[name] = text[start:end].strip()[:MAX_SECTION_CHARS]

    refs: list[str] = []
    if ref_text := section_texts.get("references", ""):
        refs = _parse_refs(ref_text)

    return Sections(
        abstract=section_texts.get("abstract"),
        introduction=section_texts.get("introduction"),
        methods=section_texts.get("methods"),
        results=section_texts.get("results"),
        discussion=section_texts.get("discussion"),
        conclusion=section_texts.get("conclusion"),
        references=refs,
    )


def _heuristic(text: str) -> Sections:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return Sections(
        abstract=paragraphs[0][:MAX_SECTION_CHARS] if paragraphs else None,
        introduction="\n\n".join(paragraphs[1:5])[:MAX_SECTION_CHARS]
        if len(paragraphs) > 1
        else None,
    )


def _parse_refs(ref_text: str) -> list[str]:
    refs = re.split(r"\n(?=[\[\(]?\d{1,3}[\]\)\.]\s)", ref_text)
    if len(refs) < 2:
        refs = ref_text.split("\n\n")
    return [r.strip() for r in refs if r.strip()][:100]


def build_qa_context(
    sections: Sections,
    include: list[str] | None = None,
    max_tokens: int = 80_000,
) -> str:
    order = include or [
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
    ]
    max_chars = max_tokens * 4
    parts: list[str] = []
    total = 0

    section_map = {
        "abstract": sections.abstract,
        "introduction": sections.introduction,
        "methods": sections.methods,
        "results": sections.results,
        "discussion": sections.discussion,
        "conclusion": sections.conclusion,
    }

    for key in order:
        content = section_map.get(key)
        if not content:
            continue
        header = f"## {key.capitalize()}\n\n"
        chunk = header + content + "\n\n"
        if total + len(chunk) > max_chars:
            remaining = max_chars - total - len(header) - 100
            if remaining > 200:
                parts.append(header + content[:remaining] + "\n…[truncated]\n\n")
            break
        parts.append(chunk)
        total += len(chunk)

    if not parts and sections.raw_text:
        parts.append(sections.raw_text[:max_chars])
    return "".join(parts)
