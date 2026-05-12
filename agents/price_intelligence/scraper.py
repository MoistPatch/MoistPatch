from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .extractor import ExtractionError, extract_price
from .models import Competitor, ScrapeResult, Sku


log = logging.getLogger(__name__)


class RobotsCache:
    """In-memory robots.txt cache, one parser per scheme+host."""

    def __init__(self, user_agent: str) -> None:
        self._cache: dict[str, RobotFileParser] = {}
        self._user_agent = user_agent

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        key = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._cache.get(key)
        if rp is None:
            rp = RobotFileParser()
            try:
                resp = await client.get(
                    f"{key}/robots.txt", timeout=10.0, follow_redirects=True
                )
                if resp.status_code < 400:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])
            except (httpx.RequestError, asyncio.TimeoutError) as exc:
                log.warning("robots fetch failed for %s: %s", key, exc)
                rp.parse([])
            self._cache[key] = rp
        return rp.can_fetch(self._user_agent, url)


class HttpScraper:
    """Polite, rate-limited HTTP scraper. No credentials stored or sent.

    Per-host rate limit between rate_limit_min_s and rate_limit_max_s
    (uniform random) — matches spec 'random delay between requests (5-15 seconds)'.
    """

    def __init__(
        self,
        competitor: Competitor,
        *,
        timeout_s: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        self.competitor = competitor
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._robots = RobotsCache(user_agent=competitor.user_agent)
        self._lock = asyncio.Lock()  # serialises requests per scraper instance
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HttpScraper":
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self.competitor.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-AU,en;q=0.9",
            },
            timeout=self.timeout_s,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client:
            await self._client.aclose()

    async def fetch(self, sku: Sku) -> ScrapeResult:
        """Fetch and extract one SKU. Returns a ScrapeResult (success or failure)."""
        assert self._client is not None, "use scraper as 'async with'"
        url = str(sku.url)

        async with self._lock:
            allowed = await self._robots.allowed(self._client, url)
            if not allowed:
                return ScrapeResult(
                    sku=sku,
                    success=False,
                    error=f"robots.txt disallows fetching {url}",
                )

            delay = random.uniform(
                self.competitor.rate_limit_min_s,
                self.competitor.rate_limit_max_s,
            )
            log.debug("polite delay %.1fs before %s", delay, url)
            await asyncio.sleep(delay)

            html, status, err = await self._get_with_retries(url)

        if html is None:
            return ScrapeResult(
                sku=sku,
                success=False,
                http_status=status,
                error=err or "fetch failed",
            )

        try:
            point = extract_price(html, sku)
        except ExtractionError as exc:
            return ScrapeResult(
                sku=sku,
                success=False,
                http_status=status,
                error=f"extraction failed: {exc}",
            )

        return ScrapeResult(
            sku=sku,
            success=True,
            point=point,
            http_status=status,
        )

    async def _get_with_retries(
        self, url: str
    ) -> tuple[Optional[str], Optional[int], Optional[str]]:
        assert self._client is not None
        backoff = 1.0
        last_err = "unknown"
        last_status: Optional[int] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self._client.get(url)
                last_status = resp.status_code
                if resp.status_code == 429:
                    last_err = f"rate limited (429), backoff {backoff}s"
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                if resp.status_code >= 500:
                    last_err = f"server error {resp.status_code}, backoff {backoff}s"
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                if resp.status_code >= 400:
                    return None, resp.status_code, f"http {resp.status_code}"
                return resp.text, resp.status_code, None
            except (httpx.RequestError, asyncio.TimeoutError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        return None, last_status, last_err
