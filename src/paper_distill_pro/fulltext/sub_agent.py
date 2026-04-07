"""Sub-agent LLM client for enhanced PDF section extraction.

Supports Anthropic (Claude) and OpenAI-compatible endpoints via configurable base URL.
"""

from __future__ import annotations

import json
import logging

import httpx

from paper_distill_pro.config import settings
from paper_distill_pro.models import Sections

logger = logging.getLogger(__name__)

_PROMPT = """You are a scientific paper analyzer. Given the text of a research paper, extract and return its structured sections.

Return ONLY valid JSON (no markdown fences, no commentary):
{
  "abstract": "...",
  "introduction": "...",
  "methods": "...",
  "results": "...",
  "discussion": "...",
  "conclusion": "...",
  "references": ["ref 1", "ref 2", ...]
}

Rules:
- If a section is missing or unclear, use null (not empty string)
- Truncate each section to 6000 characters if longer
- References: extract up to 20 formatted references as plain strings
- Return null for any section you cannot confidently extract
- Output valid JSON only
"""


def _anthropic_headers() -> dict:
    return {
        "x-api-key": settings.sub_agent_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def _openai_headers() -> dict:
    return {
        "authorization": f"Bearer {settings.sub_agent_api_key or ''}",
        "content-type": "application/json",
    }


async def _call_anthropic(content_text: str) -> str:
    """Call Anthropic Messages API (Claude)."""
    body = {
        "model": settings.sub_agent_model,
        "max_tokens": settings.sub_agent_max_tokens,
        "system": _PROMPT,
        "messages": [{"role": "user", "content": f"PAPER TEXT:\n\n{content_text[:120_000]}"}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.sub_agent_base_url.rstrip('/')}/v1/messages",
            headers=_anthropic_headers(),
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def _call_openai_compatible(content_text: str) -> str:
    """Call OpenAI-compatible /v1/chat/completions endpoint (works with Groq, local servers, etc.)."""
    body = {
        "model": settings.sub_agent_model,
        "max_tokens": settings.sub_agent_max_tokens,
        "messages": [
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": f"PAPER TEXT:\n\n{content_text[:120_000]}"},
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.sub_agent_base_url.rstrip('/')}/v1/chat/completions",
            headers=_openai_headers(),
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def parse_with_llm(text: str, paper_title: str = "") -> Sections | None:
    """
    Use an LLM sub-agent to extract structured sections from raw paper text.

    Falls back to regex-based parsing if the API is not configured or fails.
    Returns a Sections object with all extracted fields.
    """
    if not settings.sub_agent_api_key:
        logger.debug("SUB_AGENT_API_KEY not set — skipping LLM parsing")
        return None

    # Determine API type from base URL
    base = settings.sub_agent_base_url.lower()
    if "anthropic" in base or "anthropic" in settings.sub_agent_model:
        call = _call_anthropic
    else:
        call = _call_openai_compatible

    try:
        raw = await call(text)
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            raw = raw.lstrip("json").lstrip("\n").rstrip("`")

        parsed = json.loads(raw)
        return Sections(
            abstract=parsed.get("abstract"),
            introduction=parsed.get("introduction"),
            methods=parsed.get("methods"),
            results=parsed.get("results"),
            discussion=parsed.get("discussion"),
            conclusion=parsed.get("conclusion"),
            references=parsed.get("references") or [],
            raw_text=text[:60_000],
        )
    except Exception as exc:
        logger.warning("LLM parsing failed: %s — falling back to regex", exc)
        return None
