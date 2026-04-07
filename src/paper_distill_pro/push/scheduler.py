"""
Scheduler CLI — build a digest and push to all configured channels.

Usage:
    paper-distill-push                      # reads from .env / environment variables
    python -m paper_distill_pro.push.scheduler

    # Override via CLI flags
    paper-distill-push --keywords "LLM,RAG" --channels feishu --days 7

Environment variables (fallback when CLI flags not provided):
    PUSH_KEYWORDS          — comma-separated keywords
    PUSH_CHANNELS          — slack,telegram,email,wecom,feishu
    PUSH_SINCE_DAYS        — look-back window (default 7)
    PUSH_MAX_PAPERS_PER_KEYWORD
    PUSH_DIGEST_TITLE
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

import rich.logging

from paper_distill_pro.config import settings
from paper_distill_pro.models import DigestConfig

from .digest import build_digest
from .dispatcher import dispatch

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(message)s",
    handlers=[rich.logging.RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("paper_distill_pro.scheduler")


async def run(
    keywords: list[str] | None = None,
    channels: list[str] | None = None,
    since_days: int | None = None,
    max_papers: int | None = None,
    title: str | None = None,
) -> int:
    """
    Build and dispatch a paper digest.

    Args:
        keywords:  Override PUSH_KEYWORDS (list of search terms)
        channels:  Override PUSH_CHANNELS (list of channel names)
        since_days: Override PUSH_SINCE_DAYS
        max_papers: Override PUSH_MAX_PAPERS_PER_KEYWORD
        title:     Override PUSH_DIGEST_TITLE
    """
    kw = keywords or settings.keywords_list
    if not kw:
        logger.error("No keywords. Set PUSH_KEYWORDS env var or --keywords flag.")
        return 1

    ch = channels or settings.channels_list
    sd = since_days if since_days is not None else settings.push_since_days
    mp = max_papers if max_papers is not None else settings.push_max_papers_per_keyword
    t = title or settings.push_digest_title

    logger.info("Starting digest | keywords=%s | since_days=%d | channels=%s", kw, sd, ch)

    cfg = DigestConfig(
        keywords=kw,
        max_papers_per_keyword=mp,
        since_days=sd,
    )
    digest = await build_digest(cfg, title=t)

    if digest.total_papers() == 0:
        logger.warning("No papers found — nothing to push.")
        return 0

    logger.info("Digest built: %d sections, %d papers", len(digest.sections), digest.total_papers())
    results = await dispatch(digest, channels=ch)

    failed = [ch_name for ch_name, ok in results.items() if not ok]
    if failed:
        logger.error("Failed channels: %s", failed)
        return 1

    logger.info("✓ Digest dispatched at %s", datetime.utcnow().isoformat())
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="paper-distill-pro daily digest pusher")
    parser.add_argument(
        "--keywords", type=str, help="Comma-separated keywords (overrides PUSH_KEYWORDS)"
    )
    parser.add_argument(
        "--channels", type=str, help="Comma-separated channel names (overrides PUSH_CHANNELS)"
    )
    parser.add_argument("--days", type=int, help="Look-back days (overrides PUSH_SINCE_DAYS)")
    parser.add_argument(
        "--max-papers",
        type=int,
        help="Max papers per keyword (overrides PUSH_MAX_PAPERS_PER_KEYWORD)",
    )
    parser.add_argument("--title", type=str, help="Digest title (overrides PUSH_DIGEST_TITLE)")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
    channels = [c.strip() for c in args.channels.split(",")] if args.channels else None

    sys.exit(
        asyncio.run(
            run(
                keywords=keywords,
                channels=channels,
                since_days=args.days,
                max_papers=args.max_papers,
                title=args.title,
            )
        )
    )


if __name__ == "__main__":
    main()
