"""Telegram push channel — HTML formatted, auto-splits at 4000 chars."""

from __future__ import annotations

import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Digest

logger = logging.getLogger(__name__)


def _format(digest: Digest) -> str:
    lines: list[str] = [f"<b>📚 {digest.title}</b>", f"<i>{digest.date}</i>", ""]
    for section in digest.sections:
        lines.append(f"<b>🔍 {section.keyword}</b>")
        for paper in section.papers[:4]:
            authors_str = ", ".join(a.name for a in paper.authors[:2])
            if len(paper.authors) > 2:
                authors_str += " et al."
            url = paper.oa_url or paper.url
            title_line = f'<a href="{url}">{paper.title}</a>' if url else paper.title
            lines.append(
                f"• {title_line}\n  {authors_str} ({paper.year}) · ⭐ {paper.citation_count}"
            )
        lines.append("")
    lines.append(f"<i>paper-distill-pro · {digest.generated_at[:10]}</i>")
    return "\n".join(lines)


async def send_telegram(digest: Digest) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram credentials not set — skipping")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    full_text = _format(digest)
    chunks = [full_text[i : i + 4000] for i in range(0, len(full_text), 4000)]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for chunk in chunks:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": settings.telegram_chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                resp.raise_for_status()
        logger.info("Telegram digest sent (%d papers)", digest.total_papers())
        return True
    except Exception as exc:
        logger.error("Telegram push failed: %s", exc)
        return False
