"""Pydantic models for the Vantyx market surveillance agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Relevance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IRRELEVANT = "irrelevant"


class Sentiment(str, Enum):
    OPPORTUNITY = "opportunity"
    THREAT = "threat"
    NEUTRAL = "neutral"


class NewsItem(BaseModel):
    id: Optional[int] = None
    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    relevance: Relevance = Relevance.MEDIUM
    sentiment: Sentiment = Sentiment.NEUTRAL
    tags: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    analysed: bool = False


class MarketAlert(BaseModel):
    id: Optional[int] = None
    alert_type: str  # "supply_disruption", "price_signal", "competitor", "regulation", "opportunity"
    headline: str
    detail: str
    source_url: Optional[str] = None
    sentiment: Sentiment
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False


class SurveillanceReport(BaseModel):
    id: Optional[int] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    items_analysed: int
    executive_summary: str
    opportunities: list[str]
    threats: list[str]
    key_trends: list[str]
    action_items: list[str]
