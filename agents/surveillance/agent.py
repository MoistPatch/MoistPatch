"""Vantyx Market Surveillance Agent."""
from __future__ import annotations

from typing import Optional

from .analyser import analyse_unanalysed, generate_report, run_full_scan
from .models import MarketAlert, NewsItem, SurveillanceReport
from .storage import (
    get_alerts,
    get_latest_report,
    get_recent_news,
    init_db,
    Relevance,
)


class SurveillanceAgent:

    def __init__(self) -> None:
        init_db()

    def scan(self) -> dict:
        """Full pipeline: fetch news → classify → generate briefing report."""
        return run_full_scan()

    def news(self, limit: int = 20) -> list[NewsItem]:
        return get_recent_news(limit=limit, min_relevance=Relevance.MEDIUM)

    def alerts(self, unacknowledged_only: bool = False) -> list[MarketAlert]:
        return get_alerts(limit=30, unacknowledged_only=unacknowledged_only)

    def report(self) -> Optional[SurveillanceReport]:
        return get_latest_report()

    def status(self) -> dict:
        report = get_latest_report()
        alerts = get_alerts(unacknowledged_only=True)
        recent = get_recent_news(limit=5)
        return {
            "unacknowledged_alerts": len(alerts),
            "last_scan": report.generated_at.isoformat() if report else None,
            "recent_news_count": len(recent),
            "last_report_id": report.id if report else None,
        }
