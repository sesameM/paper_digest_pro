"""Abstract base connector for all academic source connectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from paper_distill_pro.config import settings
from paper_distill_pro.models import Paper

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.http_timeout,
                headers={"User-Agent": settings.user_agent},
                follow_redirects=True,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        # Handle rate limiting (429) - don't raise, just log and return empty later
        if resp.status_code == 429:
            logger.warning("[%s] Rate limited (429) for %s - skipping", self.name, url)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def _post(self, url: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        resp = await client.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    async def search(self, query: str, max_results: int = 20) -> list[Paper]: ...

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _safe_year(self, value) -> int | None:
        try:
            return int(str(value)[:4])
        except (TypeError, ValueError):
            return None

    def _safe_int(self, value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
