from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

Renderer = Literal["http", "playwright"]
Severity = Literal["low", "medium", "high"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competitor(BaseModel):
    name: str
    domain: str
    base_url: HttpUrl
    user_agent: str = (
        "NeuralHardwareBot/0.1 (+https://neuralhardware.com.au/bot; price-research)"
    )
    rate_limit_min_s: float = Field(default=5.0, ge=1.0, le=120.0)
    rate_limit_max_s: float = Field(default=15.0, ge=1.0, le=300.0)
    renderer: Renderer = "http"
    enabled: bool = True

    # ----- Discovery / crawl config (Phase 1) -----
    sitemap_url: Optional[HttpUrl] = Field(
        default=None,
        description="Override for sitemap URL. Falls back to robots.txt then /sitemap.xml.",
    )
    product_url_patterns: list[str] = Field(
        default_factory=list,
        description="fnmatch globs for URLs that look like product pages (e.g. '*/product/*'). "
                    "Empty = accept all URLs from the sitemap.",
    )
    crawl_default_currency: str = "AUD"
    crawl_price_min: Decimal = Decimal("1.00")
    crawl_price_max: Decimal = Decimal("50000.00")
    crawl_max_products: int = Field(default=500, ge=1, le=5000)

    @field_validator("rate_limit_max_s")
    @classmethod
    def _max_gt_min(cls, v: float, info) -> float:
        mn = info.data.get("rate_limit_min_s", 5.0)
        if v < mn:
            raise ValueError("rate_limit_max_s must be >= rate_limit_min_s")
        return v


class Sku(BaseModel):
    """One product on one competitor site."""

    our_sku: str = Field(description="Neural Hardware internal SKU (e.g., NH-RTX5090)")
    competitor: str = Field(description="Competitor name (must match a Competitor.name)")
    product_name: str
    url: HttpUrl
    category: str = "uncategorised"

    selectors: dict[str, str] = Field(
        default_factory=dict,
        description="Optional CSS selectors. Falls back to JSON-LD/regex if empty.",
    )

    expected_price_min: Decimal = Decimal("5.00")
    expected_price_max: Decimal = Decimal("50000.00")
    expected_currency: str = "AUD"

    enabled: bool = True

    @field_validator("our_sku")
    @classmethod
    def _sku_format(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid sku format: {v!r}")
        return v.upper()


class PricePoint(BaseModel):
    """A single observed price for one SKU at one moment."""

    our_sku: str
    competitor: str
    url: str
    price: Decimal
    currency: str
    in_stock: Optional[bool] = None
    captured_at: datetime = Field(default_factory=utcnow)
    extractor_method: str = Field(
        description="Which extraction path succeeded: jsonld | opengraph | microdata | selector | regex"
    )
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    raw_html_excerpt: str = Field(
        default="",
        description="A short HTML snippet around the extracted price, for human verification.",
    )

    @field_validator("price")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"price must be positive, got {v}")
        return v.quantize(Decimal("0.01"))

    @field_validator("currency")
    @classmethod
    def _currency_format(cls, v: str) -> str:
        v = v.upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError(f"currency must be a 3-letter ISO code, got {v!r}")
        return v


class PriceChange(BaseModel):
    our_sku: str
    competitor: str
    old_price: Decimal
    new_price: Decimal
    change_amount: Decimal
    change_percent: float
    detected_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_points(cls, old: PricePoint, new: PricePoint) -> "PriceChange":
        diff = new.price - old.price
        pct = float(diff / old.price * 100) if old.price else 0.0
        return cls(
            our_sku=new.our_sku,
            competitor=new.competitor,
            old_price=old.price,
            new_price=new.price,
            change_amount=diff,
            change_percent=pct,
        )


class Anomaly(BaseModel):
    our_sku: str
    competitor: str
    price: Decimal
    reason: str
    severity: Severity
    zscore: Optional[float] = None
    detected_at: datetime = Field(default_factory=utcnow)


class ScrapeResult(BaseModel):
    """What the scraper returns to the agent."""

    sku: Sku
    success: bool
    point: Optional[PricePoint] = None
    error: Optional[str] = None
    http_status: Optional[int] = None
    fetched_at: datetime = Field(default_factory=utcnow)


class DiscoveredProduct(BaseModel):
    """A product found by crawling, with no pre-existing internal SKU.

    `external_id` is the most stable identifier we could extract from the
    page (JSON-LD `sku` / `mpn` / `gtin` / `productID`, falling back to the
    URL slug). `our_sku` is synthesised as `EXT-{COMP}-{external_id}` so
    discovered products share the same `price_points` table as tracked SKUs.
    """

    competitor: str
    external_id: str
    product_name: str
    url: str
    category: str = "discovered"
    our_sku: str  # synthesised; see synthesise_our_sku()
    first_seen: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow)


def synthesise_our_sku(competitor: str, external_id: str) -> str:
    """Build a stable internal SKU for a discovered product.

    Format: EXT-{COMP-INITIALS}-{slugified-id}
    Example: ("Centre Com", "RTX5090-MSI") -> "EXT-CC-RTX5090-MSI"
    """
    initials = "".join(w[0] for w in competitor.split() if w)[:6].upper() or "X"
    clean = "".join(c if (c.isalnum() or c in "-_") else "-" for c in external_id)
    clean = clean.strip("-").upper()[:60] or "UNKNOWN"
    return f"EXT-{initials}-{clean}"
