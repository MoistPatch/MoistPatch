"""Fetch market news from free RSS feeds (no API key required)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from .models import NewsItem
from .storage import save_news_item

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VantyxSurveillanceAgent/1.0; +https://vantyx.com.au)"
}

# Google News RSS feeds — no key, freely accessible
RSS_FEEDS = [
    ("Google News: Fertiliser Price",
     "https://news.google.com/rss/search?q=fertilizer+fertiliser+price+market&hl=en&gl=US&ceid=US:en"),
    ("Google News: Urea Market",
     "https://news.google.com/rss/search?q=urea+nitrogen+fertilizer+market+2025&hl=en&gl=US&ceid=US:en"),
    ("Google News: DAP MAP",
     "https://news.google.com/rss/search?q=DAP+MAP+phosphate+fertilizer+price&hl=en&gl=US&ceid=US:en"),
    ("Google News: Potash",
     "https://news.google.com/rss/search?q=potash+MOP+potassium+fertilizer&hl=en&gl=US&ceid=US:en"),
    ("Google News: Australia Agriculture",
     "https://news.google.com/rss/search?q=australia+agricultural+fertiliser+import&hl=en-AU&gl=AU&ceid=AU:en"),
    ("Google News: Supply Chain",
     "https://news.google.com/rss/search?q=fertilizer+supply+chain+shortage+2025&hl=en&gl=US&ceid=US:en"),
]


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


def fetch_rss_feed(name: str, url: str) -> list[NewsItem]:
    """Fetch and parse a single RSS feed. Returns new NewsItem objects."""
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as exc:
        print(f"[surveillance/fetcher] {name} failed: {exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for entry in channel.findall("item"):
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        pub = _parse_date(entry.findtext("pubDate"))
        description = (entry.findtext("description") or "").strip()

        if not title or not link:
            continue

        # Strip HTML from description
        import re
        clean_desc = re.sub(r"<[^>]+>", "", description)[:500]

        item = save_news_item(NewsItem(
            title=title,
            url=link,
            source=name,
            published_at=pub,
            summary=clean_desc or None,
        ))
        if item.id:
            items.append(item)

    return items


def fetch_all_feeds() -> list[NewsItem]:
    """Fetch all RSS feeds and save new items. Returns newly saved items."""
    all_new = []
    for name, url in RSS_FEEDS:
        new = fetch_rss_feed(name, url)
        if new:
            print(f"[surveillance] {name}: {len(new)} new items")
        all_new.extend(new)
    print(f"[surveillance] Total new items: {len(all_new)}")
    return all_new
