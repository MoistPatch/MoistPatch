from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

import httpx

from .anomaly import detect_anomaly
from .audit import AuditLog
from .discovery import discover_product_urls
from .extractor import ExtractionError, extract_product_info
from .models import (
    Anomaly,
    Competitor,
    DiscoveredProduct,
    PriceChange,
    PricePoint,
    ScrapeResult,
    Sku,
    synthesise_our_sku,
    utcnow,
)
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


@dataclass
class CrawlReport:
    competitor: str
    urls_discovered: int = 0
    products_extracted: int = 0
    products_skipped: int = 0   # no Product schema on page
    products_failed: int = 0    # fetched but extraction error
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, error)

    def summary(self) -> str:
        return (
            f"crawled {self.competitor}: "
            f"{self.urls_discovered} URLs discovered · "
            f"{self.products_extracted} products priced · "
            f"{self.products_skipped} skipped (no schema) · "
            f"{self.products_failed} failed"
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

    # ----------------------------------------------------------------
    # Discovery / crawl
    # ----------------------------------------------------------------
    async def crawl_competitor(
        self,
        competitor_name: str,
        *,
        limit: Optional[int] = None,
        progress: Optional[Any] = None,
    ) -> CrawlReport:
        """Discover and price every product on one competitor's site.

        Discovery: sitemap.xml (config override → robots.txt → defaults).
        Extraction: JSON-LD Product schema only (no regex fallback).
        Persistence: writes to discovered_products and price_points.
        """
        if competitor_name not in self.competitors:
            raise KeyError(f"unknown competitor: {competitor_name!r}")
        competitor = self.competitors[competitor_name]
        max_products = min(limit or competitor.crawl_max_products,
                           competitor.crawl_max_products)

        report = CrawlReport(competitor=competitor.name)

        self.audit.append(
            agent=self.AGENT_ID,
            action="crawl_started",
            params={
                "competitor": competitor.name,
                "limit": max_products,
                "patterns": competitor.product_url_patterns,
            },
        )

        async with HttpScraper(competitor) as scraper:
            # Discovery uses the same httpx client (with the polite UA) but
            # bypasses the per-fetch jitter — sitemap fetches don't need that
            # since there are only a handful of XML files.
            assert scraper._client is not None
            urls = await discover_product_urls(
                scraper._client,
                str(competitor.base_url),
                sitemap_url=str(competitor.sitemap_url) if competitor.sitemap_url else None,
                include_patterns=competitor.product_url_patterns,
                max_urls=max_products,
            )
            report.urls_discovered = len(urls)
            log.info(
                "discovered %d candidate URLs for %s (limit %d)",
                len(urls), competitor.name, max_products,
            )

            self.audit.append(
                agent=self.AGENT_ID,
                action="crawl_discovered",
                params={
                    "competitor": competitor.name,
                    "url_count": len(urls),
                },
            )

            for idx, url in enumerate(urls, start=1):
                if progress:
                    progress(idx, len(urls), url)
                await self._crawl_one(scraper, competitor, url, report)

        self.audit.append(
            agent=self.AGENT_ID,
            action="crawl_finished",
            result={
                "competitor": competitor.name,
                "discovered": report.urls_discovered,
                "extracted": report.products_extracted,
                "skipped": report.products_skipped,
                "failed": report.products_failed,
            },
        )
        return report

    async def _crawl_one(
        self,
        scraper: HttpScraper,
        competitor: Competitor,
        url: str,
        report: CrawlReport,
    ) -> None:
        # Reuse the scraper's polite-fetch machinery but call _get_with_retries
        # directly (we don't have a Sku object yet — discovery hasn't run on this URL).
        import asyncio
        import random
        from .scraper import RobotsCache  # already exists

        try:
            allowed = await scraper._robots.allowed(scraper._client, url)
        except Exception as exc:
            report.products_failed += 1
            report.errors.append((url, f"robots check failed: {exc}"))
            return
        if not allowed:
            report.products_failed += 1
            report.errors.append((url, "robots.txt disallows"))
            self.store.record_failure(
                our_sku="EXT-UNKNOWN",
                competitor=competitor.name,
                url=url,
                http_status=None,
                error="robots.txt disallows",
            )
            return

        await asyncio.sleep(
            random.uniform(competitor.rate_limit_min_s, competitor.rate_limit_max_s)
        )

        html, status, err = await scraper._get_with_retries(url)
        if html is None:
            report.products_failed += 1
            report.errors.append((url, err or f"http {status}"))
            self.store.record_failure(
                our_sku="EXT-UNKNOWN",
                competitor=competitor.name,
                url=url,
                http_status=status,
                error=err or f"http {status}",
            )
            return

        try:
            info = extract_product_info(
                html, url,
                default_currency=competitor.crawl_default_currency,
                price_min=competitor.crawl_price_min,
                price_max=competitor.crawl_price_max,
            )
        except ExtractionError as exc:
            report.products_failed += 1
            report.errors.append((url, f"extract: {exc}"))
            self.store.record_failure(
                our_sku="EXT-UNKNOWN",
                competitor=competitor.name,
                url=url,
                http_status=status,
                error=f"extract: {exc}",
            )
            return

        if info is None:
            # Page didn't have JSON-LD Product schema — that's expected for
            # category pages, blog posts, etc. Don't treat as a failure.
            report.products_skipped += 1
            return

        our_sku = synthesise_our_sku(competitor.name, info["external_id"])
        now = utcnow()

        self.store.upsert_discovered(
            DiscoveredProduct(
                competitor=competitor.name,
                external_id=info["external_id"],
                our_sku=our_sku,
                product_name=info["name"],
                url=url,
                first_seen=now,
                last_seen=now,
            )
        )

        point = PricePoint(
            our_sku=our_sku,
            competitor=competitor.name,
            url=url,
            price=info["price"],
            currency=info["currency"],
            in_stock=info["in_stock"],
            captured_at=now,
            extractor_method=info["extractor_method"],
            confidence=info["confidence"],
            raw_html_excerpt="",
        )

        previous = self.store.latest_point(our_sku, competitor.name)
        self.store.record_point(point)
        report.products_extracted += 1

        if previous is not None and previous.price != point.price:
            change = PriceChange.from_points(previous, point)
            self.store.record_change(change)
            self.audit.append(
                agent=self.AGENT_ID,
                action="price_change_discovered",
                params={
                    "our_sku": our_sku,
                    "competitor": competitor.name,
                    "old": str(change.old_price),
                    "new": str(change.new_price),
                    "pct": round(change.change_percent, 2),
                },
            )

    def list_skus(self) -> list[Sku]:
        return list(self.skus)

    def list_competitors(self) -> list[Competitor]:
        return list(self.competitors.values())

    def list_discovered(
        self, competitor: Optional[str] = None, limit: int = 200
    ) -> list[dict]:
        return self.store.list_discovered(competitor=competitor, limit=limit)
