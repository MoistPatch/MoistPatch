"""
Dicker Data agent data models.
Plain dataclasses — no external dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Product:
    sku: str
    part_number: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    unit_price_aud: Optional[float] = None
    cost_price_aud: Optional[float] = None
    stock_qty: Optional[int] = None
    stock_status: Optional[str] = None
    weight_kg: Optional[float] = None
    image_url: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass
class OrderLine:
    sku: str
    quantity: int
    unit_price_aud: Optional[float] = None


@dataclass
class Order:
    reference: str
    lines: List[OrderLine] = field(default_factory=list)
    id: Optional[int] = None
    status: Optional[str] = None
    total_aud: Optional[float] = None
    created_at: Optional[datetime] = None
    tracking_number: Optional[str] = None


@dataclass
class StockAlert:
    sku: str
    description: Optional[str] = None
    threshold: Optional[int] = None
    current_qty: Optional[int] = None
    triggered_at: Optional[datetime] = None
