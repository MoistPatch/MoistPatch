from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from .models import Anomaly, PricePoint


def detect_anomaly(
    new_point: PricePoint,
    history: list[PricePoint],
    *,
    zscore_threshold: float = 2.5,
    rapid_change_pct: float = 25.0,
    rapid_change_window_hours: int = 24,
) -> Optional[Anomaly]:
    """Three checks, in order of severity:

    1. Rapid change: >rapid_change_pct% within rapid_change_window_hours -> high.
    2. Z-score outlier vs rolling history -> medium/high based on magnitude.
    3. Otherwise no anomaly.
    """
    if not history:
        return None

    recent = [
        p for p in history
        if new_point.captured_at - p.captured_at
        <= timedelta(hours=rapid_change_window_hours)
        and p.captured_at < new_point.captured_at
    ]
    if recent:
        # use the oldest within-window observation as the comparison baseline
        baseline = recent[0]
        if baseline.price > 0:
            pct = float(
                (new_point.price - baseline.price) / baseline.price * 100
            )
            if abs(pct) >= rapid_change_pct:
                return Anomaly(
                    our_sku=new_point.our_sku,
                    competitor=new_point.competitor,
                    price=new_point.price,
                    reason=(
                        f"{pct:+.1f}% change in {rapid_change_window_hours}h "
                        f"(from ${baseline.price} to ${new_point.price})"
                    ),
                    severity="high",
                    detected_at=new_point.captured_at,
                )

    if len(history) >= 5:
        prices = [float(p.price) for p in history]
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        stdev = math.sqrt(variance)
        if stdev > 0:
            z = (float(new_point.price) - mean) / stdev
            if abs(z) >= zscore_threshold:
                severity = "high" if abs(z) >= 4.0 else "medium"
                return Anomaly(
                    our_sku=new_point.our_sku,
                    competitor=new_point.competitor,
                    price=new_point.price,
                    reason=(
                        f"z-score {z:+.2f} vs rolling mean ${Decimal(mean):.2f} "
                        f"(stdev ${Decimal(stdev):.2f}, n={len(history)})"
                    ),
                    severity=severity,
                    zscore=z,
                    detected_at=new_point.captured_at,
                )

    return None
