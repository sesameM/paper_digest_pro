"""Slack push channel — Block Kit formatted digest via incoming webhook."""

from __future__ import annotations

import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Digest

logger = logging.getLogger(__name__)


def _build_payload(digest: Digest) -> dict:
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📚 {digest.title} — {digest.date}"},
        },
        {"type": "divider"},
    ]
    for section in digest.sections:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔍 {section.keyword}* — {len(section.papers)} papers",
                },
            }
        )
        for paper in section.papers[:5]:
            authors_str = ", ".join(a.name for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += " et al."
            url = paper.oa_url or paper.url or ""
            title_text = f"<{url}|{paper.title}>" if url else paper.title
            snippet = (paper.abstract or "")[:150].rstrip() + "…" if paper.abstract else ""
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"• *{title_text}*\n"
                            f"  {authors_str} ({paper.year}) · ⭐ {paper.citation_count}\n"
                            f"  _{snippet}_"
                        ),
                    },
                }
            )
        blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"_paper-distill-pro · {digest.generated_at[:10]}_"}
            ],
        }
    )
    return {"blocks": blocks}


async def send_slack(digest: Digest) -> bool:
    if not settings.slack_webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping")
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(settings.slack_webhook_url, json=_build_payload(digest))
            resp.raise_for_status()
            logger.info("Slack digest sent (%d papers)", digest.total_papers())
            return True
    except Exception as exc:
        logger.error("Slack push failed: %s", exc)
        return False
