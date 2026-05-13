from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


Strategy = Literal["competitive_floor", "match_cheapest", "margin_target"]
DecisionStatus = Literal[
    "no_change",
    "auto_applied",
    "pending_approval",
    "approved",
    "rejected",
    "applied",
    "no_data",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


class OurSku(BaseModel):
    """One of our products with pricing constraints."""

    our_sku: str
    product_name: str
    cogs: Decimal = Field(description="Cost of goods sold (incl. inbound landed cost)")
    msrp: Optional[Decimal] = Field(default=None, description="Manufacturer suggested retail price (ceiling)")
    current_price: Decimal = Field(description="Current Shopify list price")
    min_margin_pct: float = Field(default=20.0, ge=0.0, le=80.0,
                                   description="Minimum gross margin % we will hold")
    strategy: Strategy = "competitive_floor"
    enabled: bool = True

    @field_validator("cogs", "current_price", "msrp", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        return None if v is None else _d(v)

    @field_validator("our_sku")
    @classmethod
    def _sku_format(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid sku format: {v!r}")
        return v.upper()

    @property
    def min_price(self) -> Decimal:
        """The lowest price we may sell at, respecting min_margin_pct.

        margin = (price - cogs) / price
        => price = cogs / (1 - margin)
        """
        if self.min_margin_pct >= 100:
            raise ValueError("min_margin_pct must be < 100")
        floor = self.cogs / (Decimal("1") - Decimal(str(self.min_margin_pct / 100.0)))
        return floor.quantize(Decimal("0.01"))

    @property
    def current_margin_pct(self) -> float:
        if self.current_price <= 0:
            return 0.0
        return float((self.current_price - self.cogs) / self.current_price * 100)


class CompetitorPrice(BaseModel):
    """A competitor's latest price for one of our SKUs."""

    competitor: str
    price: Decimal
    in_stock: Optional[bool]
    captured_at: datetime
    url: str
    confidence: float = 1.0


class PricingDecision(BaseModel):
    """The agent's recommendation for one SKU.

    Persisted in pricing_decisions table; goes through approval workflow
    for changes that exceed the auto-apply threshold."""

    our_sku: str
    product_name: str
    current_price: Decimal
    recommended_price: Decimal
    cogs: Decimal
    min_price: Decimal
    change_amount: Decimal
    change_pct: float
    new_margin_pct: float
    competitors_seen: int = 0
    cheapest_competitor: Optional[str] = None
    cheapest_in_stock_price: Optional[Decimal] = None
    our_position: Optional[int] = Field(
        default=None,
        description="Where our recommended price ranks among in-stock competitors (1 = cheapest)",
    )
    strategy: Strategy = "competitive_floor"
    rationale: str = ""
    status: DecisionStatus = "no_change"
    auto_apply_threshold_pct: float = 5.0
    created_at: datetime = Field(default_factory=utcnow)
    reviewed_at: Optional[datetime] = None
    reviewer: Optional[str] = None
    review_reason: Optional[str] = None

    @field_validator(
        "current_price", "recommended_price", "cogs", "min_price",
        "change_amount", "cheapest_in_stock_price", mode="before",
    )
    @classmethod
    def _to_decimal(cls, v):
        return None if v is None else _d(v)

    @property
    def is_change(self) -> bool:
        return abs(self.change_amount) >= Decimal("0.01")

    @property
    def is_safe_to_auto_apply(self) -> bool:
        return abs(self.change_pct) <= self.auto_apply_threshold_pct

    @property
    def is_below_floor(self) -> bool:
        return self.recommended_price < self.min_price
