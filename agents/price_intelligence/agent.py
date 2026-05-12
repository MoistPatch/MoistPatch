from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .anomaly import detect_anomaly
from .audit import AuditLog
from .models import Anomaly, Competitor, PriceChange, ScrapeResult, Sku
from .scraper import HttpScraper
from .storage import PriceStore


log = logging.getLogger(__name__)


@dataclass
class ScanReport:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    changes: list[PriceChange] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    errors: list[tuple[str, str, str]] = field(default_factory=list)  # (sku, competitor, error)

    def summary(self) -> str:
        return (
            f"scanned {self.total} SKUs · "
            f"{self.succeeded} ok · "
            f"{self.failed} failed · "
            f"{len(self.changes)} price changes · "
            f"{len(self.anomalies)} anomalies"
        )


class PriceIntelligenceAgent:
    """Agent 1C: Competitor Price Intelligence.

    Per spec:
      - Detect price changes within 15 minutes (caller schedules scans)
      - Validate all prices against source HTML (extractor does this)
      - 99.5% accuracy target (anomalies are flagged, not silently kept)
      - Respect robots.txt, random 5-15s delay (scraper does this)
      - No credential storage (scraper sends no auth headers)
    """

    AGENT_ID = "price-intelligence-1c"

    def __init__(
        self,
        config_path: Path | str,
        *,
        data_dir: Path | str = "data",
    ) -> None:
        self.config_path = Path(config_path)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.competitors: dict[str, Competitor] = {}
        self.skus: list[Sku] = []
        self._load_config()

        self.store = PriceStore(self.data_dir / "prices.db")
        self.audit = AuditLog(self.data_dir / "audit.jsonl")

    def _load_config(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"config not found: {self.config_path}")
        with self.config_path.open() as f:
            cfg = yaml.safe_load(f)

        self.competitors = {
            c["name"]: Competitor(**c) for c in cfg.get("competitors", [])
        }
        self.skus = [Sku(**s) for s in cfg.get("skus", [])]

        unknown = {s.competitor for s in self.skus} - set(self.competitors)
        if unknown:
            raise ValueError(
                f"SKUs reference unknown competitors: {sorted(unknown)}"
            )

    def _enabled_skus(self) -> list[Sku]:
        return [
            s for s in self.skus
            if s.enabled and self.competitors[s.competitor].enabled
        ]

    async def scan_all(self) -> ScanReport:
        report = ScanReport()
        skus = self._enabled_skus()
        report.total = len(skus)

        self.audit.append(
            agent=self.AGENT_ID,
            action="scan_started",
            params={"sku_count": len(skus)},
        )

        # group by competitor so each competitor's scraper handles rate limiting
        grouped: dict[str, list[Sku]] = {}
        for sku in skus:
            grouped.setdefault(sku.competitor, []).append(sku)

        tasks = [
            self._scan_competitor(self.competitors[name], comp_skus, report)
            for name, comp_skus in grouped.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=False)

        self.audit.append(
            agent=self.AGENT_ID,
            action="scan_finished",
            result={
                "total": report.total,
                "succeeded": report.succeeded,
                "failed": report.failed,
                "changes": len(report.changes),
                "anomalies": len(report.anomalies),
            },
        )
        return report

    async def _scan_competitor(
        self,
        competitor: Competitor,
        skus: list[Sku],
        report: ScanReport,
    ) -> None:
        async with HttpScraper(competitor) as scraper:
            for sku in skus:
                try:
                    result = await scraper.fetch(sku)
                except Exception as exc:
                    log.exception("scraper crashed on %s", sku.our_sku)
                    self.store.record_failure(
                        our_sku=sku.our_sku,
                        competitor=competitor.name,
                        url=str(sku.url),
                        http_status=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    report.failed += 1
                    report.errors.append(
                        (sku.our_sku, competitor.name, str(exc))
                    )
                    continue

                self._process_result(result, report)

    def _process_result(self, result: ScrapeResult, report: ScanReport) -> None:
        sku = result.sku
        if not result.success or result.point is None:
            self.store.record_failure(
                our_sku=sku.our_sku,
                competitor=sku.competitor,
                url=str(sku.url),
                http_status=result.http_status,
                error=result.error or "unknown",
            )
            self.audit.append(
                agent=self.AGENT_ID,
                action="scrape_failed",
                params={"sku": sku.our_sku, "competitor": sku.competitor},
                result={"error": result.error, "status": result.http_status},
            )
            report.failed += 1
            report.errors.append(
                (sku.our_sku, sku.competitor, result.error or "unknown")
            )
            return

        new_point = result.point
        previous = self.store.latest_point(sku.our_sku, sku.competitor)
        self.store.record_point(new_point)
        report.succeeded += 1

        change = None
        if previous is not None and previous.price != new_point.price:
            change = PriceChange.from_points(previous, new_point)
            self.store.record_change(change)
            report.changes.append(change)
            self.audit.append(
                agent=self.AGENT_ID,
                action="price_change",
                params={
                    "sku": sku.our_sku,
                    "competitor": sku.competitor,
                    "old": str(change.old_price),
                    "new": str(change.new_price),
                    "pct": round(change.change_percent, 2),
                },
            )

        history = self.store.history(sku.our_sku, sku.competitor, days=30)
        anomaly = detect_anomaly(new_point, history[:-1])  # exclude the point we just added
        if anomaly is not None:
            report.anomalies.append(anomaly)
            self.audit.append(
                agent=self.AGENT_ID,
                action="anomaly_detected",
                params={
                    "sku": sku.our_sku,
                    "competitor": sku.competitor,
                    "price": str(anomaly.price),
                    "reason": anomaly.reason,
                    "severity": anomaly.severity,
                },
            )

    def list_skus(self) -> list[Sku]:
        return list(self.skus)

    def list_competitors(self) -> list[Competitor]:
        return list(self.competitors.values())
