"""Fetch fertiliser prices from free public sources (no API key required)."""
from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .models import PricePoint, PriceSource
from .storage import save_price

# IndexMundi commodity slugs → our internal product keys
_INDEXMUNDI = {
    "urea":                    "urea",
    "diammonium-phosphate":    "dap",
    "potassium-chloride":      "mop",
    "phosphate-rock":          "phosphate_rock",
    "ammonia":                 "ammonia",
}

_FRED_SERIES = {
    # PPI: Fertilizer and agricultural chemical manufacturing
    "PCU325311325311": "fertiliser_ppi",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VantyxPricingAgent/1.0; +https://vantyx.com.au)"
}


def fetch_indexmundi_price(commodity_slug: str) -> Optional[PricePoint]:
    """Scrape the latest price from an IndexMundi commodity page."""
    url = f"https://www.indexmundi.com/commodities/?commodity={commodity_slug}&months=3&currency=usd"
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # The data table has class "tblData"
        table = soup.find("table", {"class": "tblData"})
        if not table:
            return None

        rows = table.find_all("tr")
        # rows[0] is header, last data row is most recent
        data_rows = [r for r in rows[1:] if r.find_all("td")]
        if not data_rows:
            return None

        last_row = data_rows[-1]
        cells = last_row.find_all("td")
        if len(cells) < 2:
            return None

        date_str = cells[0].get_text(strip=True)  # e.g. "Apr 2025"
        price_str = cells[1].get_text(strip=True).replace(",", "")

        try:
            price = float(price_str)
        except ValueError:
            return None

        try:
            source_date = datetime.strptime(date_str, "%b %Y")
        except ValueError:
            source_date = datetime.utcnow()

        product = _INDEXMUNDI.get(commodity_slug, commodity_slug)
        return PricePoint(
            product=product,
            price_usd_mt=price,
            source=PriceSource.INDEXMUNDI,
            source_date=source_date,
            notes=f"IndexMundi — {commodity_slug}",
        )
    except Exception as exc:
        print(f"[pricing/fetcher] IndexMundi {commodity_slug} failed: {exc}")
        return None


def fetch_fred_series(series_id: str) -> Optional[PricePoint]:
    """Fetch latest value from FRED CSV (no API key needed)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()

        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        if len(rows) < 2:
            return None

        # Last non-empty row with valid data
        data_rows = [(row[0], row[1]) for row in rows[1:] if len(row) >= 2 and row[1].strip() and row[1] != "."]
        if not data_rows:
            return None

        date_str, value_str = data_rows[-1]
        try:
            value = float(value_str)
            source_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

        product = _FRED_SERIES.get(series_id, series_id.lower())
        return PricePoint(
            product=product,
            price_usd_mt=value,
            source=PriceSource.FRED,
            source_date=source_date,
            notes=f"FRED {series_id} — PPI index (2012=100)",
        )
    except Exception as exc:
        print(f"[pricing/fetcher] FRED {series_id} failed: {exc}")
        return None


def fetch_all_prices() -> list[PricePoint]:
    """Fetch prices from all free sources and save to DB. Returns saved points."""
    saved = []

    for slug in _INDEXMUNDI:
        p = fetch_indexmundi_price(slug)
        if p:
            saved.append(save_price(p))
            print(f"[pricing] {p.product}: ${p.price_usd_mt:.0f}/MT (IndexMundi, {p.source_date.strftime('%b %Y')})")

    for series_id in _FRED_SERIES:
        p = fetch_fred_series(series_id)
        if p:
            saved.append(save_price(p))
            print(f"[pricing] {p.product}: index {p.price_usd_mt:.1f} (FRED, {p.source_date.strftime('%b %Y')})")

    return saved


def add_manual_price(product: str, price_usd_mt: float, notes: str = "") -> PricePoint:
    """Record a manually entered price (e.g. from a supplier quote)."""
    p = PricePoint(
        product=product,
        price_usd_mt=price_usd_mt,
        source=PriceSource.MANUAL,
        source_date=datetime.utcnow(),
        notes=notes or "Manual entry",
    )
    return save_price(p)
