"""Pricing strategies. Each takes (sku, competitor_prices) and returns
(recommended_price, rationale_string).

Strategies must NEVER recommend below sku.min_price. Guardrail enforcement
lives in the agent class, but well-behaved strategies should respect the
floor themselves and explain the reasoning.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .models import CompetitorPrice, OurSku


def _in_stock(competitors: Iterable[CompetitorPrice]) -> list[CompetitorPrice]:
    return [c for c in competitors if c.in_stock is not False]


def _summarise(competitors: list[CompetitorPrice]) -> str:
    if not competitors:
        return "no competitor data"
    prices = sorted(c.price for c in competitors)
    return f"{len(competitors)} competitors, range ${prices[0]} – ${prices[-1]}"


def competitive_floor(
    sku: OurSku,
    competitors: list[CompetitorPrice],
) -> tuple[Decimal, str]:
    """Match the cheapest in-stock competitor; never breach margin floor.

    - If no competitor data: hold current price.
    - If all competitors are OOS: hold current (no demand-side signal to match).
    - If cheapest in-stock < our min_price: hold floor; explain why.
    - Otherwise: match cheapest in-stock exactly.

    Note: we DON'T undercut by $1 — that's a race-to-bottom trigger that
    other vendors will respond to. Matching is the steady-state equilibrium.
    """
    if not competitors:
        return sku.current_price, "No competitor data available; held current price."

    in_stock = _in_stock(competitors)
    if not in_stock:
        cheapest_oos = min(competitors, key=lambda c: c.price)
        return sku.current_price, (
            f"All {len(competitors)} competitors out of stock "
            f"(cheapest OOS ${cheapest_oos.price} @ {cheapest_oos.competitor}). "
            f"Held current price — no demand-side signal to match."
        )

    cheapest = min(in_stock, key=lambda c: c.price)
    floor = sku.min_price

    if sku.msrp is not None and cheapest.price > sku.msrp:
        # Cheapest is above MSRP — unusual, hold MSRP
        return sku.msrp, (
            f"Cheapest in-stock ${cheapest.price} @ {cheapest.competitor} "
            f"is above MSRP ${sku.msrp}. Held at MSRP."
        )

    if cheapest.price < floor:
        return floor, (
            f"Cheapest in-stock ${cheapest.price} @ {cheapest.competitor} "
            f"is below our margin floor (${floor}, "
            f"COGS ${sku.cogs} at {sku.min_margin_pct:.0f}% margin). "
            f"Held floor — will not match without breaching minimum margin."
        )

    target = cheapest.price
    margin_pct = float((target - sku.cogs) / target * 100)
    return target, (
        f"Matched cheapest in-stock ${cheapest.price} @ {cheapest.competitor}. "
        f"New margin {margin_pct:.1f}% (above {sku.min_margin_pct:.0f}% floor). "
        f"Market: {_summarise(in_stock)}."
    )


def match_cheapest(
    sku: OurSku,
    competitors: list[CompetitorPrice],
) -> tuple[Decimal, str]:
    """Always match the cheapest in-stock competitor, even if it means
    breaching margin floor (will still be clamped by guardrails in agent).

    Use this only if you're explicitly OK with margin compression on
    selected loss-leader SKUs.
    """
    in_stock = _in_stock(competitors)
    if not in_stock:
        return sku.current_price, "No in-stock competitors; held current."
    cheapest = min(in_stock, key=lambda c: c.price)
    return cheapest.price, (
        f"Matched cheapest in-stock ${cheapest.price} @ {cheapest.competitor} "
        f"(margin floor may be breached and clamped by guardrails)."
    )


def margin_target(
    sku: OurSku,
    competitors: list[CompetitorPrice],
    target_margin_pct: float = 30.0,
) -> tuple[Decimal, str]:
    """Hold a target margin regardless of competitor positioning.

    Useful for accessories / high-margin SKUs where the spec says
    'high-margin accessories are the profit engine'.
    """
    target = sku.cogs / (Decimal("1") - Decimal(str(target_margin_pct / 100.0)))
    target = target.quantize(Decimal("0.01"))
    floor = sku.min_price
    final = max(target, floor)
    return final, (
        f"Margin-anchored: target {target_margin_pct:.0f}% margin "
        f"on COGS ${sku.cogs} → ${target}. "
        f"Market context: {_summarise(competitors)}."
    )


STRATEGIES = {
    "competitive_floor": competitive_floor,
    "match_cheapest": match_cheapest,
    "margin_target": margin_target,
}
