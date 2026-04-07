"""Obsidian vault sync — push papers to and pull papers from a local Obsidian vault."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from paper_distill_pro.config import settings
from paper_distill_pro.models import Author, Paper, SyncResult

logger = logging.getLogger(__name__)


def _vault() -> Path | None:
    if not settings.obsidian_vault_path:
        return None
    p = Path(settings.obsidian_vault_path).expanduser().resolve()
    return p if p.exists() else None


def _safe_filename(title: str) -> str:
    """Convert a paper title to a safe Obsidian filename."""
    name = unicodedata.normalize("NFKC", title)
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    if len(name) > 200:
        name = name[:200].rsplit(" ", 1)[0]
    return name


def _paper_frontmatter(paper: Paper) -> str:
    """Generate YAML frontmatter for a paper note."""
    lines = ["---"]
    lines.append(f'title: "{paper.title}"')
    if paper.authors:
        author_str = "; ".join(a.name for a in paper.authors)
        lines.append(f'authors: "{author_str}"')
    if paper.year:
        lines.append(f"year: {paper.year}")
    if paper.doi:
        lines.append(f'doi: "{paper.doi}"')
    if paper.arxiv_id:
        lines.append(f'arxiv: "{paper.arxiv_id}"')
    if paper.venue:
        lines.append(f'venue: "{paper.venue}"')
    if paper.citation_count:
        lines.append(f"citation_count: {paper.citation_count}")
    if paper.url:
        lines.append(f'url: "{paper.url}"')
    if paper.oa_url:
        lines.append(f'open_access_url: "{paper.oa_url}"')
    if paper.pdf_url:
        lines.append(f'pdf_url: "{paper.pdf_url}"')
    if paper.fields_of_study:
        tags = ", ".join("#" + t.replace(" ", "-").lower() for t in paper.fields_of_study[:5])
        lines.append(f"tags: [{tags}]")
    lines.append(f'source: "{paper.source}"')
    lines.append("type: paper")
    lines.append("---")
    return "\n".join(lines)


def _paper_to_obsidian(paper: Paper, include_abstract: bool = True) -> str:
    """Convert a Paper to an Obsidian note string with YAML frontmatter."""
    frontmatter = _paper_frontmatter(paper)
    body = f"# {paper.title}\n\n"
    if include_abstract and paper.abstract:
        body += f"## Abstract\n\n{paper.abstract}\n"
    return f"{frontmatter}\n\n{body}"


def _obsidian_to_paper(file_path: Path) -> Paper | None:
    """Parse an Obsidian note (YAML frontmatter) back into a Paper model."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None

    fm_text = m.group(1)
    fm_lines = fm_text.splitlines()
    fm: dict[str, str] = {}
    for raw in fm_lines:
        if ":" not in raw:
            continue
        idx = raw.index(":")
        key = raw[:idx].strip()
        val = raw[idx + 1 :].strip().strip('"').strip("'")
        if val:
            fm[key] = val

    # Parse authors
    authors: list[Author] = []
    raw_authors = fm.get("authors", "")
    if raw_authors:
        for name in re.split(r"[;,]", raw_authors):
            name = name.strip()
            if name:
                authors.append(Author(name=name))

    # Parse year
    year: int | None = None
    raw_year = fm.get("year", "")
    if raw_year.isdigit():
        year = int(raw_year)

    # Parse tags → fields_of_study
    fields: list[str] = []
    raw_tags = fm.get("tags", "")
    for tag in re.findall(r"#([\w\s-]+)", raw_tags):
        fields.append(tag.replace("-", " ").strip())

    # Extract abstract from note body
    abstract: str | None = None
    body = text[m.end() :].strip()
    abs_m = re.search(r"##\s*Abstract\s*\n+(.*?)(?=\n##|\Z)", body, re.IGNORECASE | re.DOTALL)
    if abs_m:
        abstract = abs_m.group(1).strip()

    return Paper(
        title=fm.get("title", file_path.stem),
        authors=authors,
        year=year,
        doi=fm.get("doi"),
        arxiv_id=fm.get("arxiv"),
        abstract=abstract,
        venue=fm.get("venue"),
        url=fm.get("url"),
        oa_url=fm.get("open_access_url"),
        pdf_url=fm.get("pdf_url"),
        citation_count=int(fm["citation_count"]) if fm.get("citation_count", "").isdigit() else 0,
        fields_of_study=fields,
        source=fm.get("source", "obsidian"),
    )


# ── Push (write to Obsidian) ───────────────────────────────────────────────────


async def sync_to_obsidian(
    papers: list[Paper],
    folder: str | None = None,
    include_abstract: bool = True,
) -> SyncResult:
    """
    Write papers as Markdown notes to an Obsidian vault.

    Each paper is saved as ``{folder}/{safe_title}.md`` with YAML frontmatter
    containing all metadata. Duplicates are detected by DOI, arXiv ID, or
    normalized title and skipped.
    """
    vault = _vault()
    if not vault:
        return SyncResult(
            failed=len(papers),
            details=["OBSIDIAN_VAULT_PATH is not set or the path does not exist"],
        )

    result = SyncResult()

    target_dir = vault
    if folder:
        target_dir = vault / folder
        target_dir.mkdir(parents=True, exist_ok=True)

    # Build existing dedup keys
    existing: set[str] = set()
    for fp in target_dir.glob("*.md"):
        paper = _obsidian_to_paper(fp)
        if paper:
            existing.add(paper.dedup_key)

    for paper in papers:
        key = paper.dedup_key
        if key in existing:
            result.skipped += 1
            result.details.append(f"Skipped (duplicate): {paper.title[:60]}")
            continue

        filename = _safe_filename(paper.title) + ".md"
        filepath = target_dir / filename

        # Handle filename collisions
        suffix = 1
        while filepath.exists():
            existing_paper = _obsidian_to_paper(filepath)
            if existing_paper and existing_paper.dedup_key == key:
                result.skipped += 1
                result.details.append(f"Skipped (duplicate): {paper.title[:60]}")
                break
            filepath = target_dir / f"{_safe_filename(paper.title)} ({suffix}).md"
            suffix += 1
        else:
            try:
                text = _paper_to_obsidian(paper, include_abstract=include_abstract)
                filepath.write_text(text, encoding="utf-8")
                result.synced += 1
                result.details.append(f"Synced: {paper.title[:60]}")
                existing.add(key)
            except Exception as exc:
                result.failed += 1
                result.details.append(f"Failed: {paper.title[:60]} — {exc}")
                logger.warning("Failed to write %s: %s", filepath, exc)

    return result


# ── Pull (read from Obsidian) ──────────────────────────────────────────────────


async def pull_from_obsidian(
    folder: str | None = None,
    limit: int = 100,
) -> list[Paper]:
    """
    Read all paper notes from an Obsidian vault (optionally filtered to a
    subfolder) and return as Paper objects.
    """
    vault = _vault()
    if not vault:
        logger.warning("OBSIDIAN_VAULT_PATH is not set or not found")
        return []

    target_dir = vault
    if folder:
        target_dir = vault / folder
        if not target_dir.exists():
            logger.warning("Obsidian folder '%s' not found in vault", folder)
            return []

    papers: list[Paper] = []
    for fp in sorted(target_dir.glob("*.md")):
        if len(papers) >= limit:
            break
        paper = _obsidian_to_paper(fp)
        if paper:
            papers.append(paper)

    return papers
