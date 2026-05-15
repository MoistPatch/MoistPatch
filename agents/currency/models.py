"""Data models for the Currency Monitor agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RateAlert:
    id: Optional[int]
    currency_code: str
    condition: str          # "above" | "below"
    threshold: float
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    triggered_at: Optional[datetime] = None


@dataclass
class AlertHistoryItem:
    id: int
    currency_code: str
    rate: float
    threshold: float
    condition: str
    triggered_at: datetime
