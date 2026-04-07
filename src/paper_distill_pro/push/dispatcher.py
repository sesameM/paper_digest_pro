"""Dispatcher — fan-out a Digest to all configured push channels."""

from __future__ import annotations

import asyncio
import logging

from paper_distill_pro.config import settings
from paper_distill_pro.models import Digest

from .channels.email import send_email
from .channels.feishu import send_feishu
from .channels.slack import send_slack
from .channels.telegram import send_telegram
from .channels.wecom import send_wecom

logger = logging.getLogger(__name__)

_CHANNEL_MAP = {
    "slack": send_slack,
    "telegram": send_telegram,
    "email": send_email,
    "wecom": send_wecom,
    "feishu": send_feishu,
}


async def dispatch(digest: Digest, channels: list[str] | None = None) -> dict[str, bool]:
    active = channels or settings.channels_list
    tasks = {name: _CHANNEL_MAP[name](digest) for name in active if name in _CHANNEL_MAP}

    unknown = [c for c in active if c not in _CHANNEL_MAP]
    if unknown:
        logger.warning("Unknown push channels: %s", unknown)

    if not tasks:
        logger.info("No push channels configured — digest not sent")
        return {}

    outcomes = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results: dict[str, bool] = {}
    for name, outcome in zip(tasks.keys(), outcomes, strict=True):
        if isinstance(outcome, Exception):
            logger.error("Channel %s raised: %s", name, outcome)
            results[name] = False
        else:
            results[name] = bool(outcome)

    successes = sum(v for v in results.values())
    logger.info("Dispatch: %d/%d channels succeeded", successes, len(results))
    return results
