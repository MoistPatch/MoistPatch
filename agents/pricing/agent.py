"""Vantyx Pricing Agent — main orchestration class."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .analyser import analyse_market, detect_alerts
from .fetcher import add_manual_price, fetch_all_prices
from .models import PriceAlert, PricingAnalysis, PRODUCT_LABELS
from .storage import (
    get_alerts,
    get_all_latest_prices,
    get_latest_analysis,
    get_price_history,
    init_db,
)


class PricingAgent:

    def __init__(self) -> None:
        init_db()

    def refresh(self) -> dict:
        """Fetch latest prices from all free public sources and check for alerts."""
        prices = fetch_all_prices()
        alerts = detect_alerts()
        return {"prices_fetched": len(prices), "alerts_generated": len(alerts)}

    def add_price(self, product: str, price_usd_mt: float, notes: str = "") -> None:
        """Manually record a price (e.g. from a supplier quote)."""
        if product not in PRODUCT_LABELS:
            raise ValueError(f"Unknown product '{product}'. Valid: {list(PRODUCT_LABELS)}")
        add_manual_price(product, price_usd_mt, notes)
        print(f"[pricing] Manual price recorded: {PRODUCT_LABELS[product]} = ${price_usd_mt:.0f}/MT")
        detect_alerts()

    def analyse(self, force: bool = False) -> Optional[PricingAnalysis]:
        """Run Claude market analysis."""
        return analyse_market(force=force)

    def prices(self) -> dict:
        """Return current prices for all tracked products."""
        latest = get_all_latest_prices()
        return {
            product: {
                "label": PRODUCT_LABELS.get(product, product),
                "price_usd_mt": p.price_usd_mt,
                "source": p.source.value,
                "date": p.source_date.strftime("%b %Y"),
            }
            for product, p in latest.items()
        }

    def alerts(self, unacknowledged_only: bool = False) -> list[PriceAlert]:
        return get_alerts(limit=50, unacknowledged_only=unacknowledged_only)

    def analysis(self) -> Optional[PricingAnalysis]:
        return get_latest_analysis()

    def status(self) -> dict:
        latest = get_all_latest_prices()
        alerts = get_alerts(unacknowledged_only=True)
        analysis = get_latest_analysis()
        return {
            "products_tracked": len(latest),
            "unacknowledged_alerts": len(alerts),
            "last_analysis": analysis.generated_at.isoformat() if analysis else None,
            "market_outlook": analysis.outlook if analysis else "unknown",
        }
