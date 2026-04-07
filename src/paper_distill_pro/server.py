"""
paper-distill-pro — MCP server entry point.

Tools:
  search    — search_papers, batch_search
  fulltext  — fetch_fulltext, compare_papers, extract_contributions
  graph     — get_citation_tree, trace_lineage
  trend     — analyze_trend, compare_trends
  sync      — sync_to_zotero, pull_from_zotero,
              sync_to_mendeley, pull_from_mendeley,
              sync_to_notion,   pull_from_notion,
              sync_to_obsidian, pull_from_obsidian
  push      — send_digest

Start:
  paper-distill-pro                       # stdio (Claude Desktop / Cursor)
  paper-distill-pro --transport http --port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from paper_distill_pro.config import settings
from paper_distill_pro.models import DigestConfig

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = Server("paper-distill-pro")

# ── Tool definitions ──────────────────────────────────────────────────────────


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── search ────────────────────────────────────────────────────────────
        Tool(
            name="search_papers",
            description=(
                "Search academic papers across up to 11 databases in parallel "
                "(OpenAlex, arXiv, Semantic Scholar, PubMed, CrossRef, Europe PMC, "
                "bioRxiv, DBLP, Papers with Code, IEEE Xplore, ACM DL, SSRN). "
                "Returns deduplicated, relevance-scored results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max papers to return",
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific sources to search. Available: openalex, arxiv, semantic_scholar, "
                            "pubmed, crossref, europe_pmc, biorxiv, dblp, papers_with_code, ieee, acm, ssrn. "
                            "Empty = all free sources."
                        ),
                    },
                    "since_year": {
                        "type": "integer",
                        "description": "Filter to papers from this year onward",
                    },
                    "min_citations": {
                        "type": "integer",
                        "default": 0,
                        "description": "Minimum citation count",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="batch_search",
            description="Run multiple search queries concurrently and return combined deduplicated results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "List of queries to run in parallel",
                    },
                    "max_results_per_query": {"type": "integer", "default": 10},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["queries"],
            },
        ),
        # ── fulltext ──────────────────────────────────────────────────────────
        Tool(
            name="fetch_fulltext",
            description=(
                "Download the PDF for a paper and extract structured sections "
                "(abstract, introduction, methods, results, discussion, conclusion). "
                "Returns a Markdown context string ready for AI question-answering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "doi": {"type": "string", "description": "e.g. 10.1145/xxx"},
                    "arxiv_id": {"type": "string", "description": "e.g. 2303.08774"},
                    "oa_url": {"type": "string", "description": "Direct open-access URL"},
                    "pdf_url": {"type": "string", "description": "Direct PDF URL"},
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which sections to include. Empty = all.",
                    },
                    "max_tokens": {"type": "integer", "default": 80000},
                    "use_llm": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use LLM sub-agent for enhanced parsing (requires SUB_AGENT_API_KEY)",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="compare_papers",
            description="Fetch full-text context for multiple papers and align them side-by-side for comparison.",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "doi": {"type": "string"},
                                "arxiv_id": {"type": "string"},
                                "oa_url": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                        "description": "2–5 papers to compare",
                    },
                    "aspect": {
                        "type": "string",
                        "enum": ["methodology", "results", "contribution", "full"],
                        "default": "methodology",
                    },
                    "use_llm": {"type": "boolean", "default": False},
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="extract_contributions",
            description="Fetch and summarise the main contributions of a single paper.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "doi": {"type": "string"},
                    "arxiv_id": {"type": "string"},
                    "oa_url": {"type": "string"},
                    "use_llm": {"type": "boolean", "default": False},
                },
                "required": ["title"],
            },
        ),
        # ── citation graph ────────────────────────────────────────────────────
        Tool(
            name="get_citation_tree",
            description="Build a citation tree for a paper — citing papers and references, with influential ancestors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "S2 ID, DOI (prefix DOI:), or arXiv ID (prefix ARXIV:)",
                    },
                    "depth": {"type": "integer", "default": 1, "minimum": 1, "maximum": 3},
                    "max_per_level": {"type": "integer", "default": 20},
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="trace_lineage",
            description="Walk back through reference chains to find the intellectual ancestors of a paper.",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string"},
                    "generations": {"type": "integer", "default": 2, "minimum": 1, "maximum": 4},
                },
                "required": ["paper_id"],
            },
        ),
        # ── trends ────────────────────────────────────────────────────────────
        Tool(
            name="analyze_trend",
            description="Analyse annual paper counts and citations for a keyword; compute CAGR.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "years": {"type": "integer", "default": 10},
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="compare_trends",
            description="Compare growth trends for multiple keywords.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "years": {"type": "integer", "default": 5},
                },
                "required": ["keywords"],
            },
        ),
        # ── sync ──────────────────────────────────────────────────────────────
        Tool(
            name="sync_to_zotero",
            description="Push papers to Zotero library (skips duplicates by DOI).",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {"type": "array", "items": {"type": "object"}},
                    "collection": {
                        "type": "string",
                        "description": "Collection name (created if absent)",
                    },
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="pull_from_zotero",
            description="Pull papers from a Zotero library or collection and return as structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection name (empty = whole library)",
                    },
                    "limit": {"type": "integer", "default": 100},
                },
            },
        ),
        Tool(
            name="sync_to_mendeley",
            description="Push papers to Mendeley library (skips duplicates by DOI).",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {"type": "array", "items": {"type": "object"}},
                    "folder": {
                        "type": "string",
                        "description": "Mendeley folder name (created if absent)",
                    },
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="pull_from_mendeley",
            description="Pull papers from a Mendeley library or folder and return as structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Folder name (empty = whole library)",
                    },
                    "limit": {"type": "integer", "default": 100},
                },
            },
        ),
        Tool(
            name="sync_to_notion",
            description="Add papers to a Notion database (skips duplicate titles).",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {"type": "array", "items": {"type": "object"}},
                    "database_id": {"type": "string", "description": "Notion database ID"},
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="pull_from_notion",
            description="Pull papers from a Notion database and return as structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 100},
                },
            },
        ),
        Tool(
            name="sync_to_obsidian",
            description="Write papers as Markdown notes with YAML frontmatter to a local Obsidian vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {"type": "array", "items": {"type": "object"}},
                    "folder": {
                        "type": "string",
                        "description": "Subfolder inside the vault (created if absent)",
                    },
                    "include_abstract": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include abstract in the note body",
                    },
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="pull_from_obsidian",
            description="Pull papers from an Obsidian vault (or subfolder) and return as structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Subfolder name inside the vault"},
                    "limit": {"type": "integer", "default": 100},
                },
            },
        ),
        # ── push ──────────────────────────────────────────────────────────────
        Tool(
            name="send_digest",
            description=(
                "Build a paper digest for given keywords and push to configured channels "
                "(slack, telegram, email, wecom)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "channels": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["slack", "telegram", "email", "wecom", "feishu"],
                        },
                    },
                    "max_papers_per_keyword": {"type": "integer", "default": 5},
                    "since_days": {"type": "integer", "default": 7},
                    "title": {"type": "string", "default": "Scholar Digest"},
                },
                "required": ["keywords"],
            },
        ),
    ]


# ── Tool dispatcher ───────────────────────────────────────────────────────────


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = f"Error in {name}: {exc}"
    return [TextContent(type="text", text=str(result))]


async def _dispatch(name: str, args: dict) -> str:  # noqa: C901
    if name == "search_papers":
        from paper_distill_pro.search.engine import search_papers

        papers = await search_papers(
            query=args["query"],
            max_results=args.get("max_results", 20),
            sources=args.get("sources"),
            since_year=args.get("since_year"),
            min_citations=args.get("min_citations", 0),
        )
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    if name == "batch_search":
        from paper_distill_pro.search.dedup import deduplicate
        from paper_distill_pro.search.engine import search_papers

        tasks = [
            search_papers(
                q, max_results=args.get("max_results_per_query", 10), sources=args.get("sources")
            )
            for q in args["queries"]
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        all_papers = []
        for r in results_list:
            if not isinstance(r, Exception):
                all_papers.extend(r)
        return json.dumps(
            [p.model_dump() for p in deduplicate(all_papers)], ensure_ascii=False, indent=2
        )

    if name == "fetch_fulltext":
        from paper_distill_pro.fulltext import (
            build_qa_context,
            fetch_pdf_bytes,
            parse_pdf,
            parse_pdf_llm,
        )
        from paper_distill_pro.models import Paper

        paper = Paper(
            title=args["title"],
            doi=args.get("doi"),
            arxiv_id=args.get("arxiv_id"),
            oa_url=args.get("oa_url"),
            pdf_url=args.get("pdf_url") or args.get("oa_url"),
        )
        pdf = await fetch_pdf_bytes(paper)
        if pdf:
            if args.get("use_llm"):
                sections = await parse_pdf_llm(pdf, paper=paper)
            else:
                sections = parse_pdf(pdf, paper=paper)
            ctx = build_qa_context(
                sections, include=args.get("sections"), max_tokens=args.get("max_tokens", 80_000)
            )
            if ctx.strip():
                return ctx
        return f"## Abstract\n\n{paper.abstract or '*(No full text or abstract available)*'}"

    if name == "compare_papers":
        from paper_distill_pro.fulltext import (
            build_qa_context,
            fetch_pdf_bytes,
            parse_pdf,
            parse_pdf_llm,
        )
        from paper_distill_pro.models import Paper

        aspect_map = {
            "methodology": ["abstract", "methods"],
            "results": ["abstract", "results"],
            "contribution": ["abstract", "introduction", "conclusion"],
            "full": None,
        }
        sections_filter = aspect_map.get(args.get("aspect", "methodology"), ["abstract", "methods"])
        use_llm = args.get("use_llm", False)
        parts: list[str] = []
        for p_args in args["papers"]:
            paper = Paper(
                title=p_args["title"],
                doi=p_args.get("doi"),
                arxiv_id=p_args.get("arxiv_id"),
                oa_url=p_args.get("oa_url"),
            )
            pdf = await fetch_pdf_bytes(paper)
            if pdf:
                secs = await (parse_pdf_llm if use_llm else parse_pdf)(pdf, paper=paper)
                ctx = build_qa_context(secs, include=sections_filter, max_tokens=20_000)
            else:
                ctx = f"## Abstract\n\n{paper.abstract or '*(unavailable)*'}"
            parts.append(f"# {paper.title}\n\n{ctx}\n\n---\n")
        return "\n".join(parts)

    if name == "extract_contributions":
        from paper_distill_pro.fulltext import (
            build_qa_context,
            fetch_pdf_bytes,
            parse_pdf,
            parse_pdf_llm,
        )
        from paper_distill_pro.models import Paper

        paper = Paper(
            title=args["title"],
            doi=args.get("doi"),
            arxiv_id=args.get("arxiv_id"),
            oa_url=args.get("oa_url"),
        )
        pdf = await fetch_pdf_bytes(paper)
        if pdf:
            secs = await (parse_pdf_llm if args.get("use_llm") else parse_pdf)(pdf, paper=paper)
            ctx = build_qa_context(
                secs, include=["abstract", "introduction", "conclusion"], max_tokens=10_000
            )
        else:
            ctx = paper.abstract or "*(No content available)*"
        return f"**Paper:** {paper.title}\n\n{ctx}"

    if name == "get_citation_tree":
        from paper_distill_pro.search.sources.semantic_scholar import SemanticScholarConnector

        s2 = SemanticScholarConnector()
        paper_id = args["paper_id"]
        max_per = args.get("max_per_level", 20)
        root = await s2.get_paper(paper_id)
        if not root:
            return "Paper not found"
        citing = await s2.get_citations(paper_id, limit=max_per)
        refs = await s2.get_references(paper_id, limit=max_per)
        influential = sorted(
            [p for p in citing + refs if p.citation_count >= 50],
            key=lambda p: p.citation_count,
            reverse=True,
        )[:10]
        return json.dumps(
            {
                "root": root.model_dump(),
                "citing": [p.model_dump() for p in citing],
                "references": [p.model_dump() for p in refs],
                "influential": [p.model_dump() for p in influential],
            },
            ensure_ascii=False,
            indent=2,
        )

    if name == "trace_lineage":
        from paper_distill_pro.search.sources.semantic_scholar import SemanticScholarConnector

        s2 = SemanticScholarConnector()
        visited: dict[str, object] = {}
        frontier = [args["paper_id"]]
        for _ in range(args.get("generations", 2)):
            next_frontier: list[str] = []
            results_list = await asyncio.gather(
                *[s2.get_references(pid, limit=20) for pid in frontier], return_exceptions=True
            )
            for result in results_list:
                if isinstance(result, Exception):
                    continue
                for paper in result:
                    key = paper.dedup_key
                    if key not in visited:
                        visited[key] = paper
                        if paper.arxiv_id:
                            next_frontier.append(f"ARXIV:{paper.arxiv_id}")
                        elif paper.doi:
                            next_frontier.append(f"DOI:{paper.doi}")
            frontier = next_frontier[:10]
        papers = sorted(visited.values(), key=lambda p: p.citation_count, reverse=True)  # type: ignore[attr-defined]
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    if name == "analyze_trend":
        from datetime import datetime as dt

        import httpx as hx

        keyword = args["keyword"]
        years_n = args.get("years", 10)
        current = dt.utcnow().year
        year_range = range(current - years_n, current + 1)
        annual_counts: dict[int, int] = {}
        annual_citations: dict[int, int] = {}
        async with hx.AsyncClient(timeout=15.0) as client:
            for year in year_range:
                try:
                    resp = await client.get(
                        "https://api.openalex.org/works",
                        params={
                            "filter": f"title_and_abstract.search:{keyword},publication_year:{year}",
                            "select": "id,cited_by_count",
                            "per-page": 50,
                        },
                    )
                    data = resp.json()
                    cnt = data.get("meta", {}).get("count", 0)
                    annual_counts[year] = cnt
                    annual_citations[year] = sum(
                        int(r.get("cited_by_count", 0)) for r in data.get("results", [])
                    )
                except Exception:
                    annual_counts[year] = 0
                    annual_citations[year] = 0
        sorted_years = sorted(annual_counts.keys())

        def cagr(d: dict[int, int]) -> float:
            vals = [d[y] for y in sorted_years if d.get(y)]
            if len(vals) < 2 or vals[0] == 0:
                return 0.0
            n = len(vals) - 1
            return round((vals[-1] / vals[0]) ** (1 / n) - 1, 4)

        return json.dumps(
            {
                "keyword": keyword,
                "annual_counts": annual_counts,
                "annual_citations": annual_citations,
                "cagr_papers": cagr(annual_counts),
                "cagr_citations": cagr(annual_citations),
            },
            ensure_ascii=False,
            indent=2,
        )

    if name == "compare_trends":
        results_list = await asyncio.gather(
            *[
                _dispatch("analyze_trend", {"keyword": kw, "years": args.get("years", 5)})
                for kw in args["keywords"]
            ],
            return_exceptions=True,
        )
        reports = [r for r in results_list if not isinstance(r, Exception)]
        return json.dumps(reports, ensure_ascii=False, indent=2)

    # ── Sync tools ──────────────────────────────────────────────────────────
    if name in (
        "sync_to_zotero",
        "pull_from_zotero",
        "sync_to_mendeley",
        "pull_from_mendeley",
        "sync_to_notion",
        "pull_from_notion",
        "sync_to_obsidian",
        "pull_from_obsidian",
    ):
        return await _dispatch_sync(name, args)

    if name == "send_digest":
        from paper_distill_pro.push.digest import build_digest
        from paper_distill_pro.push.dispatcher import dispatch

        cfg = DigestConfig(
            keywords=args["keywords"],
            max_papers_per_keyword=args.get("max_papers_per_keyword", 5),
            since_days=args.get("since_days", 7),
        )
        digest = await build_digest(cfg, title=args.get("title", "Scholar Digest"))
        results = await dispatch(digest, channels=args.get("channels"))
        return json.dumps(
            {"total_papers": digest.total_papers(), "channels": results}, ensure_ascii=False
        )

    return f"Unknown tool: {name}"


async def _dispatch_sync(name: str, args: dict) -> str:
    if name == "sync_to_zotero":
        from paper_distill_pro.models import Paper
        from paper_distill_pro.sync.zotero import sync_to_zotero

        papers = [
            Paper(**{k: v for k, v in p.items() if k in Paper.model_fields}) for p in args["papers"]
        ]
        result = await sync_to_zotero(papers, collection_name=args.get("collection"))
        return json.dumps(result.model_dump(), ensure_ascii=False)

    if name == "pull_from_zotero":
        from paper_distill_pro.sync.zotero import pull_from_zotero

        papers = await pull_from_zotero(
            collection_name=args.get("collection"), limit=args.get("limit", 100)
        )
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    if name == "sync_to_mendeley":
        from paper_distill_pro.models import Paper
        from paper_distill_pro.sync.mendeley import sync_to_mendeley

        papers = [
            Paper(**{k: v for k, v in p.items() if k in Paper.model_fields}) for p in args["papers"]
        ]
        result = await sync_to_mendeley(papers, folder_name=args.get("folder"))
        return json.dumps(result.model_dump(), ensure_ascii=False)

    if name == "pull_from_mendeley":
        from paper_distill_pro.sync.mendeley import pull_from_mendeley

        papers = await pull_from_mendeley(
            folder_name=args.get("folder"), limit=args.get("limit", 100)
        )
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    if name == "sync_to_notion":
        from paper_distill_pro.models import Paper
        from paper_distill_pro.sync.notion import sync_to_notion

        papers = [
            Paper(**{k: v for k, v in p.items() if k in Paper.model_fields}) for p in args["papers"]
        ]
        result = await sync_to_notion(papers, database_id=args.get("database_id"))
        return json.dumps(result.model_dump(), ensure_ascii=False)

    if name == "pull_from_notion":
        from paper_distill_pro.sync.notion import pull_from_notion

        papers = await pull_from_notion(
            database_id=args.get("database_id"), limit=args.get("limit", 100)
        )
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    if name == "sync_to_obsidian":
        from paper_distill_pro.models import Paper
        from paper_distill_pro.sync.obsidian import sync_to_obsidian

        papers = [
            Paper(**{k: v for k, v in p.items() if k in Paper.model_fields}) for p in args["papers"]
        ]
        result = await sync_to_obsidian(
            papers,
            folder=args.get("folder"),
            include_abstract=args.get("include_abstract", True),
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)

    if name == "pull_from_obsidian":
        from paper_distill_pro.sync.obsidian import pull_from_obsidian

        papers = await pull_from_obsidian(folder=args.get("folder"), limit=args.get("limit", 100))
        return json.dumps([p.model_dump() for p in papers], ensure_ascii=False, indent=2)

    return f"Unknown sync tool: {name}"


# ── Server startup ────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="paper-distill-pro MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    parsed = parser.parse_args()

    if parsed.transport == "http":
        try:
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route

            sse = SseServerTransport("/messages")

            async def handle_sse(request):
                async with sse.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    await app.run(streams[0], streams[1], app.create_initialization_options())

            starlette_app = Starlette(
                routes=[
                    Route("/sse", endpoint=handle_sse),
                    Mount("/messages", app=sse.handle_post_message),
                ]
            )
            logger.info("HTTP server on port %d", parsed.port)
            uvicorn.run(starlette_app, host="0.0.0.0", port=parsed.port)
        except ImportError as e:
            logger.error(
                "HTTP mode requires uvicorn and starlette: pip install uvicorn starlette — %s", e
            )
    else:
        logger.info("stdio mode")
        asyncio.run(_run_stdio())


async def _run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
