from __future__ import annotations

import fnmatch
import gzip
import logging
from typing import Optional
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx


log = logging.getLogger(__name__)


SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DEFAULT_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")
MAX_URLS_HARD_CAP = 5000
MAX_INDEX_DEPTH = 2  # how many levels of <sitemapindex> nesting to follow


async def _fetch_robots_sitemaps(
    client: httpx.AsyncClient, base_url: str
) -> list[str]:
    """Parse Sitemap: directives from /robots.txt."""
    try:
        resp = await client.get(
            urljoin(base_url, "/robots.txt"),
            timeout=10.0,
            follow_redirects=True,
        )
    except (httpx.RequestError, TimeoutError) as exc:
        log.warning("robots.txt fetch failed for %s: %s", base_url, exc)
        return []
    if resp.status_code >= 400:
        return []
    sitemaps = []
    for line in resp.text.splitlines():
        s = line.strip()
        if s.lower().startswith("sitemap:"):
            sitemaps.append(s.split(":", 1)[1].strip())
    return sitemaps


async def _fetch_sitemap_xml(
    client: httpx.AsyncClient, url: str
) -> Optional[bytes]:
    """Fetch a sitemap URL. Handles gzipped responses transparently."""
    try:
        resp = await client.get(url, timeout=30.0, follow_redirects=True)
    except (httpx.RequestError, TimeoutError) as exc:
        log.warning("sitemap fetch %s failed: %s", url, exc)
        return None
    if resp.status_code >= 400:
        log.info("sitemap %s -> HTTP %d", url, resp.status_code)
        return None
    content = resp.content
    ctype = resp.headers.get("content-type", "").lower()
    if url.endswith(".gz") or "x-gzip" in ctype or "gzip" in ctype:
        try:
            content = gzip.decompress(content)
        except (OSError, EOFError) as exc:
            log.warning("gzip decompress failed for %s: %s", url, exc)
            return None
    return content


def parse_sitemap(xml_bytes: bytes) -> tuple[list[str], list[str]]:
    """Parse a sitemap XML document.

    Returns (page_urls, child_sitemap_urls).
    Handles both <urlset> (regular sitemap) and <sitemapindex>.
    Tolerates documents with or without the standard namespace.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        log.warning("sitemap parse error: %s", exc)
        return [], []

    urls: list[str] = []
    sub_sitemaps: list[str] = []

    # Try with the standard namespace first
    for loc in root.findall(".//sm:url/sm:loc", SITEMAP_NS):
        if loc.text:
            urls.append(loc.text.strip())
    for loc in root.findall(".//sm:sitemap/sm:loc", SITEMAP_NS):
        if loc.text:
            sub_sitemaps.append(loc.text.strip())

    # Fallback for sitemaps that omit the namespace
    if not urls and not sub_sitemaps:
        for loc in root.findall(".//url/loc"):
            if loc.text:
                urls.append(loc.text.strip())
        for loc in root.findall(".//sitemap/loc"):
            if loc.text:
                sub_sitemaps.append(loc.text.strip())

    return urls, sub_sitemaps


def match_any(url: str, patterns: list[str]) -> bool:
    """Does the URL match any of the fnmatch glob patterns?

    Empty pattern list = accept all.
    """
    if not patterns:
        return True
    return any(fnmatch.fnmatch(url, p) for p in patterns)


async def discover_product_urls(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    sitemap_url: Optional[str] = None,
    include_patterns: Optional[list[str]] = None,
    max_urls: int = MAX_URLS_HARD_CAP,
) -> list[str]:
    """Discover product URLs for a competitor.

    Discovery order:
      1. explicit `sitemap_url` arg (from config)
      2. `Sitemap:` directives in /robots.txt
      3. /sitemap.xml, /sitemap_index.xml, /sitemap-index.xml

    Recurses into <sitemapindex> entries up to MAX_INDEX_DEPTH levels.
    Filters by fnmatch globs (e.g. '*/product/*').
    Hard-capped at max_urls (default 5000).
    """
    max_urls = min(max_urls, MAX_URLS_HARD_CAP)
    include_patterns = include_patterns or []

    candidates: list[str] = []
    if sitemap_url:
        candidates.append(sitemap_url)
    candidates.extend(await _fetch_robots_sitemaps(client, base_url))
    for path in DEFAULT_SITEMAP_PATHS:
        candidates.append(urljoin(base_url, path))

    seen: set[str] = set()
    matched: list[str] = []

    async def walk(url: str, depth: int) -> None:
        if depth > MAX_INDEX_DEPTH:
            return
        if url in seen:
            return
        seen.add(url)
        if len(matched) >= max_urls:
            return
        content = await _fetch_sitemap_xml(client, url)
        if not content:
            return
        urls, sub_sitemaps = parse_sitemap(content)
        for u in urls:
            if len(matched) >= max_urls:
                return
            if match_any(u, include_patterns):
                matched.append(u)
        for sub in sub_sitemaps:
            if len(matched) >= max_urls:
                return
            await walk(sub, depth + 1)

    for src in candidates:
        if len(matched) >= max_urls:
            break
        await walk(src, 0)
        if matched:
            # First candidate that returned anything wins — don't keep falling
            # through to additional sources (avoids double-fetching the same site)
            break

    return matched
