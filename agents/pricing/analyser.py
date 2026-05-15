"""Claude-powered pricing analysis and alert generation."""
from __future__ import annotations

import json
import os
import re

import anthropic

from .models import AlertSeverity, PriceAlert, PricingAnalysis, PRODUCT_LABELS
from .storage import (
    get_all_latest_prices,
    get_alerts,
    get_latest_analysis,
    get_price_history,
    save_alert,
    save_analysis,
)

_SIGNIFICANT_MOVE_PCT = 5.0  # alert if price moves > 5% from previous reading


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def detect_alerts() -> list[PriceAlert]:
    """Compare latest prices to prior readings; generate alerts for significant moves."""
    new_alerts: list[PriceAlert] = []

    latest = get_all_latest_prices()
    for product, current in latest.items():
        history = get_price_history(product, months=3)
        if len(history) < 2:
            continue

        # Previous reading (second-to-last)
        prev = history[-2] if len(history) >= 2 else None
        if not prev:
            continue

        change_pct = ((current.price_usd_mt - prev.price_usd_mt) / prev.price_usd_mt) * 100
        if abs(change_pct) < _SIGNIFICANT_MOVE_PCT:
            continue

        label = PRODUCT_LABELS.get(product, product)
        if change_pct >= 15:
            severity, atype = AlertSeverity.CRITICAL, "spike"
            msg = f"{label} surged {change_pct:+.1f}% to ${current.price_usd_mt:.0f}/MT — review cost pricing immediately"
        elif change_pct >= 5:
            severity, atype = AlertSeverity.WARNING, "rise"
            msg = f"{label} rose {change_pct:+.1f}% to ${current.price_usd_mt:.0f}/MT"
        elif change_pct <= -15:
            severity, atype = AlertSeverity.INFO, "drop"
            msg = f"{label} dropped {change_pct:+.1f}% to ${current.price_usd_mt:.0f}/MT — potential buying opportunity"
        else:
            severity, atype = AlertSeverity.INFO, "decline"
            msg = f"{label} fell {change_pct:+.1f}% to ${current.price_usd_mt:.0f}/MT"

        alert = save_alert(PriceAlert(
            product=product,
            alert_type=atype,
            severity=severity,
            message=msg,
            price_usd_mt=current.price_usd_mt,
            previous_price_usd_mt=prev.price_usd_mt,
            change_pct=change_pct,
        ))
        new_alerts.append(alert)
        print(f"[pricing] Alert [{severity.value.upper()}] {msg}")

    return new_alerts


def _build_price_table(latest: dict) -> str:
    lines = ["| Product | Price USD/MT | Source | Date |",
             "|---|---|---|---|"]
    for product, p in sorted(latest.items()):
        label = PRODUCT_LABELS.get(product, product)
        lines.append(f"| {label} | ${p.price_usd_mt:,.0f} | {p.source.value} | {p.source_date.strftime('%b %Y')} |")
    return "\n".join(lines)


def _build_history_summary(products: list[str]) -> str:
    lines = []
    for product in products:
        history = get_price_history(product, months=6)
        if len(history) < 2:
            continue
        label = PRODUCT_LABELS.get(product, product)
        prices = [f"${p.price_usd_mt:.0f}" for p in history[-6:]]
        direction = "↑" if history[-1].price_usd_mt > history[0].price_usd_mt else "↓"
        lines.append(f"- {label}: {' → '.join(prices)} {direction}")
    return "\n".join(lines) if lines else "(insufficient history)"


def analyse_market(force: bool = False) -> PricingAnalysis | None:
    """Run Claude analysis of current pricing data. Returns None if no data."""
    latest = get_all_latest_prices()
    if not latest and not force:
        print("[pricing] No price data yet. Run fetch_all_prices() first.")
        return None

    price_table = _build_price_table(latest)
    history_summary = _build_history_summary(list(latest.keys()))
    recent_alerts = get_alerts(limit=10, unacknowledged_only=False)
    alerts_text = "\n".join(f"- [{a.severity.value}] {a.message}" for a in recent_alerts[:5]) or "(none)"

    prompt = f"""You are a commodity market analyst for Vantyx Pty Ltd — an Australian International Commodity Trader
and Importer/Exporter of agricultural fertilisers (based in Melbourne, ABN 84 544 119 830).

Vantyx sources globally and sells to Australian and international agricultural buyers.
Your role: interpret current fertiliser pricing data and advise Sam on strategy.

## Current Market Prices

{price_table}

## Recent Price Trends (6-month history)

{history_summary}

## Recent Alerts

{alerts_text}

## Analysis Request

Provide a comprehensive market analysis covering:
1. Overall market direction (bullish/bearish/neutral/mixed)
2. Key price drivers you can infer from the data
3. Specific buying/sourcing opportunities for Vantyx
4. Risk warnings Sam should act on
5. Forward-looking outlook and strategy recommendations

Be specific and practical. Reference actual prices and products. Think from the perspective of
a trader who needs to advise on: when to stock up, when to wait, what to quote buyers at.

Respond in this EXACT JSON format — no text outside the JSON:

{{
  "market_summary": "3-4 paragraph analysis of current market conditions",
  "recommendations": [
    "Specific actionable recommendation #1 for Sam",
    "Recommendation #2",
    "Recommendation #3",
    "Recommendation #4"
  ],
  "buying_opportunities": [
    "Product X is at a 6-month low — consider stocking up before prices recover",
    "..."
  ],
  "risk_warnings": [
    "Warning about a risk that needs attention",
    "..."
  ],
  "outlook": "bullish|bearish|neutral|mixed"
}}"""

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned non-JSON: {raw[:200]}")

    data = json.loads(match.group())
    analysis = save_analysis(PricingAnalysis(
        products_analysed=len(latest),
        market_summary=data["market_summary"],
        recommendations=data.get("recommendations", []),
        buying_opportunities=data.get("buying_opportunities", []),
        risk_warnings=data.get("risk_warnings", []),
        outlook=data.get("outlook", "neutral"),
    ))
    print(f"[pricing] Analysis complete: {analysis.outlook} market ({len(latest)} products)")
    return analysis
