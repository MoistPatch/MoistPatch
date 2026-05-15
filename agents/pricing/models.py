"""Pydantic models for the Vantyx pricing agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PriceSource(str, Enum):
    INDEXMUNDI = "indexmundi"
    FRED = "fred"
    MANUAL = "manual"
    ESTIMATED = "estimated"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


TRACKED_PRODUCTS = [
    "urea",
    "dap",
    "map",
    "mop",
    "phosphate_rock",
    "ammonia",
    "ammonium_sulphate",
    "tsp",
]

PRODUCT_LABELS = {
    "urea": "Urea 46% N (Granular)",
    "dap": "DAP 18-46-0",
    "map": "MAP 12-61-0",
    "mop": "MOP (Muriate of Potash) 60% K₂O",
    "phosphate_rock": "Phosphate Rock",
    "ammonia": "Ammonia (Anhydrous)",
    "ammonium_sulphate": "Ammonium Sulphate 21% N",
    "tsp": "TSP (Triple Superphosphate)",
}


class PricePoint(BaseModel):
    id: Optional[int] = None
    product: str
    price_usd_mt: float
    source: PriceSource
    source_date: datetime
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None


class PriceAlert(BaseModel):
    id: Optional[int] = None
    product: str
    alert_type: str  # "spike", "drop", "new_low", "new_high", "trend_reversal"
    severity: AlertSeverity
    message: str
    price_usd_mt: float
    previous_price_usd_mt: Optional[float] = None
    change_pct: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False


class PricingAnalysis(BaseModel):
    id: Optional[int] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    products_analysed: int
    market_summary: str
    recommendations: list[str]
    buying_opportunities: list[str]
    risk_warnings: list[str]
    outlook: str  # "bullish" | "bearish" | "neutral" | "mixed"
