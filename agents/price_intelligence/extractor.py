from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import PricePoint, Sku


PRICE_REGEX = re.compile(
    r"""
    (?:AUD|USD|NZD|\$|A\$)?      # optional currency
    \s*
    (?P<num>\d{1,3}(?:[, ]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)
    """,
    re.VERBOSE,
)


class ExtractionError(Exception):
    pass


def _normalise_amount(raw: str) -> Decimal:
    """Convert messy price strings to Decimal. '$1,499.00' -> Decimal('1499.00')."""
    if raw is None:
        raise ExtractionError("price value is None")
    cleaned = (
        str(raw)
        .replace("\xa0", " ")
        .replace(",", "")
        .replace("$", "")
        .replace("AUD", "")
        .replace("A$", "")
        .strip()
    )
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        raise ExtractionError("empty price string after normalisation")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ExtractionError(f"not a number: {raw!r}") from exc


def _validate_against_sku(price: Decimal, currency: str, sku: Sku) -> None:
    """Hard validation per spec: reject prices outside expected range or wrong currency."""
    if price < sku.expected_price_min:
        raise ExtractionError(
            f"price ${price} below expected min ${sku.expected_price_min}"
        )
    if price > sku.expected_price_max:
        raise ExtractionError(
            f"price ${price} above expected max ${sku.expected_price_max}"
        )
    if currency.upper() != sku.expected_currency.upper():
        raise ExtractionError(
            f"currency {currency!r} does not match expected {sku.expected_currency!r}"
        )


def _excerpt(html: str, anchor: Optional[str], window: int = 200) -> str:
    if not anchor:
        return html[:window]
    idx = html.find(anchor)
    if idx < 0:
        return html[:window]
    start = max(0, idx - window // 2)
    return html[start : start + window]


# ---------------------------------------------------------------- JSON-LD


def _extract_jsonld(soup: BeautifulSoup) -> Optional[tuple[Decimal, str, Optional[bool]]]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            graph = entry.get("@graph", [entry])
            if not isinstance(graph, list):
                graph = [graph]
            for node in graph:
                if not isinstance(node, dict):
                    continue
                t = node.get("@type", "")
                if isinstance(t, list):
                    is_product = "Product" in t
                else:
                    is_product = t == "Product"
                if not is_product and "offers" not in node:
                    continue
                offers = node.get("offers", node)
                offers = offers if isinstance(offers, list) else [offers]
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    raw_price = (
                        offer.get("price")
                        or offer.get("lowPrice")
                        or offer.get("highPrice")
                    )
                    if raw_price is None:
                        continue
                    try:
                        price = _normalise_amount(raw_price)
                    except ExtractionError:
                        continue
                    currency = (
                        offer.get("priceCurrency")
                        or offer.get("currency")
                        or "AUD"
                    )
                    availability = offer.get("availability", "")
                    in_stock = None
                    if isinstance(availability, str):
                        a = availability.lower()
                        if "instock" in a:
                            in_stock = True
                        elif "outofstock" in a or "soldout" in a:
                            in_stock = False
                    return price, currency, in_stock
    return None


# ---------------------------------------------------------------- OpenGraph


def _extract_opengraph(
    soup: BeautifulSoup,
) -> Optional[tuple[Decimal, str, Optional[bool]]]:
    price_tag = soup.find("meta", property="product:price:amount") or soup.find(
        "meta", property="og:price:amount"
    )
    cur_tag = soup.find("meta", property="product:price:currency") or soup.find(
        "meta", property="og:price:currency"
    )
    if not price_tag or not price_tag.get("content"):
        return None
    try:
        price = _normalise_amount(price_tag["content"])
    except ExtractionError:
        return None
    currency = (cur_tag["content"] if cur_tag and cur_tag.get("content") else "AUD")
    avail = soup.find("meta", property="product:availability")
    in_stock: Optional[bool] = None
    if avail and avail.get("content"):
        a = avail["content"].lower()
        if "in stock" in a or "instock" in a:
            in_stock = True
        elif "out of stock" in a or "outofstock" in a:
            in_stock = False
    return price, currency, in_stock


# ---------------------------------------------------------------- Microdata


def _extract_microdata(
    soup: BeautifulSoup,
) -> Optional[tuple[Decimal, str, Optional[bool]]]:
    tag = soup.find(attrs={"itemprop": "price"})
    if not tag:
        return None
    raw = tag.get("content") or tag.get_text(strip=True)
    try:
        price = _normalise_amount(raw)
    except ExtractionError:
        return None
    cur_tag = soup.find(attrs={"itemprop": "priceCurrency"})
    currency = (
        cur_tag.get("content")
        if cur_tag and cur_tag.get("content")
        else (cur_tag.get_text(strip=True) if cur_tag else "AUD")
    )
    return price, currency, None


# ---------------------------------------------------------------- Selector / regex


def _extract_selector(
    soup: BeautifulSoup, selector: str
) -> Optional[tuple[Decimal, str, Optional[bool]]]:
    tag: Optional[Tag] = soup.select_one(selector)
    if not tag:
        return None
    raw = tag.get("content") or tag.get_text(" ", strip=True)
    try:
        price = _normalise_amount(raw)
    except ExtractionError:
        return None
    return price, "AUD", None


def _extract_regex(html: str) -> Optional[tuple[Decimal, str, Optional[bool]]]:
    """Last-resort: pull the largest plausible AUD-shaped number from the page."""
    candidates: list[Decimal] = []
    for m in PRICE_REGEX.finditer(html):
        try:
            v = _normalise_amount(m.group("num"))
        except ExtractionError:
            continue
        if Decimal("5") <= v <= Decimal("50000"):
            candidates.append(v)
    if not candidates:
        return None
    candidates.sort()
    median = candidates[len(candidates) // 2]
    return median, "AUD", None


# ---------------------------------------------------------------- Public API


def extract_price(html: str, sku: Sku) -> PricePoint:
    """Run the extraction chain. Raises ExtractionError if all methods fail
    or the result fails hard validation.

    Safety property: if any structured method (jsonld/opengraph/microdata)
    declares an explicit currency that doesn't match sku.expected_currency,
    extraction is aborted entirely. We do NOT fall back to a method that
    might guess AUD on a page priced in USD.
    """
    soup = BeautifulSoup(html, "lxml")

    structured: list[tuple[str, float, Optional[tuple[Decimal, str, Optional[bool]]]]] = [
        ("jsonld", 0.98, _extract_jsonld(soup)),
        ("opengraph", 0.92, _extract_opengraph(soup)),
        ("microdata", 0.88, _extract_microdata(soup)),
    ]

    fallback: list[tuple[str, float, Optional[tuple[Decimal, str, Optional[bool]]]]] = []
    price_selector = sku.selectors.get("price")
    if price_selector:
        fallback.append(
            ("selector", 0.80, _extract_selector(soup, price_selector))
        )
    fallback.append(("regex", 0.40, _extract_regex(html)))

    last_error = "no extraction method matched"

    for method, confidence, result in structured:
        if result is None:
            continue
        price, currency, in_stock = result
        if currency.upper() != sku.expected_currency.upper():
            raise ExtractionError(
                f"{method} declares currency {currency!r}, expected "
                f"{sku.expected_currency!r}; refusing to fall back to AUD assumption"
            )
        try:
            _validate_against_sku(price, currency, sku)
        except ExtractionError as exc:
            last_error = f"{method}: {exc}"
            continue
        return PricePoint(
            our_sku=sku.our_sku,
            competitor=sku.competitor,
            url=str(sku.url),
            price=price,
            currency=currency.upper(),
            in_stock=in_stock,
            extractor_method=method,
            confidence=confidence,
            raw_html_excerpt=_excerpt(html, str(price)),
        )

    for method, confidence, result in fallback:
        if result is None:
            continue
        price, currency, in_stock = result
        try:
            _validate_against_sku(price, currency, sku)
        except ExtractionError as exc:
            last_error = f"{method}: {exc}"
            continue
        return PricePoint(
            our_sku=sku.our_sku,
            competitor=sku.competitor,
            url=str(sku.url),
            price=price,
            currency=currency.upper(),
            in_stock=in_stock,
            extractor_method=method,
            confidence=confidence,
            raw_html_excerpt=_excerpt(html, str(price)),
        )

    raise ExtractionError(last_error)
