from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional


@dataclass
class CompetitorPrice:
    competitor: str
    price: Decimal
    currency: str
    in_stock: Optional[bool]
    captured_at: datetime
    confidence: float
    extractor_method: str
    url: str


@dataclass
class PriceComparison:
    our_sku: str
    product_name: str
    prices: list[CompetitorPrice]

    @property
    def cheapest(self) -> Optional[CompetitorPrice]:
        in_stock = [p for p in self.prices if p.in_stock is not False]
        pool = in_stock if in_stock else self.prices
        return min(pool, key=lambda p: p.price) if pool else None

    @property
    def dearest(self) -> Optional[CompetitorPrice]:
        return max(self.prices, key=lambda p: p.price) if self.prices else None

    @property
    def spread_pct(self) -> Optional[float]:
        if len(self.prices) < 2:
            return None
        cheapest = self.cheapest
        dearest = self.dearest
        if cheapest is None or dearest is None or cheapest.price == 0:
            return None
        return float(
            (dearest.price - cheapest.price) / cheapest.price * 100
        )


@dataclass
class ChangeRow:
    our_sku: str
    competitor: str
    old_price: Decimal
    new_price: Decimal
    change_amount: Decimal
    change_percent: float
    detected_at: datetime


@dataclass
class AnomalyRow:
    our_sku: str
    competitor: str
    price: Decimal
    reason: str
    severity: str
    detected_at: datetime


@dataclass
class FailureRow:
    competitor: str
    count: int
    last_error: str


@dataclass
class DailyReport:
    period_start: datetime
    period_end: datetime
    is_demo: bool = False

    skus_tracked: int = 0
    competitors_tracked: int = 0
    scans_succeeded: int = 0
    scans_failed: int = 0

    comparisons: list[PriceComparison] = field(default_factory=list)
    changes: list[ChangeRow] = field(default_factory=list)
    anomalies: list[AnomalyRow] = field(default_factory=list)
    failures: list[FailureRow] = field(default_factory=list)

    avg_confidence: float = 0.0
    audit_chain_ok: Optional[bool] = None
    audit_entries: int = 0

    # ---------------- derived
    @property
    def success_rate(self) -> float:
        total = self.scans_succeeded + self.scans_failed
        return (self.scans_succeeded / total * 100) if total else 0.0

    @property
    def hallucination_risk(self) -> str:
        """Translate avg confidence to a coarse risk band.

        Note: this is a proxy until Agent 2C (LLM-as-judge) is live.
        avg confidence -> risk:
          >= 0.95   very low
          0.85-0.94 low
          0.70-0.84 moderate
          0.50-0.69 elevated
          < 0.50    high
        """
        c = self.avg_confidence
        if c >= 0.95:
            return "very low"
        if c >= 0.85:
            return "low"
        if c >= 0.70:
            return "moderate"
        if c >= 0.50:
            return "elevated"
        return "high"

    @property
    def biggest_drop(self) -> Optional[ChangeRow]:
        drops = [c for c in self.changes if c.change_amount < 0]
        return min(drops, key=lambda c: c.change_percent) if drops else None

    @property
    def biggest_rise(self) -> Optional[ChangeRow]:
        rises = [c for c in self.changes if c.change_amount > 0]
        return max(rises, key=lambda c: c.change_percent) if rises else None


class ReportCompiler:
    """Compiles Agent 1C's SQLite output into a DailyReport.

    Pure read-only — never writes to the price DB.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"price database not found at {self.db_path}. "
                f"Run `python -m agents.price_intelligence scan` first."
            )
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def compile(
        self,
        *,
        hours: int = 24,
        product_filter: Optional[list[str]] = None,
        is_demo: bool = False,
    ) -> DailyReport:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)

        with self._conn() as conn:
            report = DailyReport(
                period_start=start,
                period_end=end,
                is_demo=is_demo,
            )

            # SKU / competitor / scan counts
            report.skus_tracked = conn.execute(
                "SELECT COUNT(DISTINCT our_sku) FROM price_points"
            ).fetchone()[0]
            report.competitors_tracked = conn.execute(
                "SELECT COUNT(DISTINCT competitor) FROM price_points"
            ).fetchone()[0]
            report.scans_succeeded = conn.execute(
                "SELECT COUNT(*) FROM price_points WHERE captured_at >= ?",
                (start.isoformat(),),
            ).fetchone()[0]
            report.scans_failed = conn.execute(
                "SELECT COUNT(*) FROM scrape_failures WHERE failed_at >= ?",
                (start.isoformat(),),
            ).fetchone()[0]

            # Average confidence (proxy for hallucination risk)
            avg = conn.execute(
                "SELECT AVG(confidence) FROM price_points WHERE captured_at >= ?",
                (start.isoformat(),),
            ).fetchone()[0]
            report.avg_confidence = float(avg) if avg is not None else 0.0

            # Per-SKU current price comparison across competitors
            sku_filter_clause = ""
            sku_filter_params: tuple = ()
            if product_filter:
                placeholders = ",".join("?" for _ in product_filter)
                sku_filter_clause = f" WHERE our_sku IN ({placeholders})"
                sku_filter_params = tuple(s.upper() for s in product_filter)

            skus = [
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT our_sku FROM price_points{sku_filter_clause}",
                    sku_filter_params,
                )
            ]

            for sku in skus:
                rows = conn.execute(
                    """SELECT p.*
                       FROM price_points p
                       JOIN (
                           SELECT competitor, MAX(captured_at) AS latest
                           FROM price_points
                           WHERE our_sku = ?
                           GROUP BY competitor
                       ) latest ON latest.competitor = p.competitor
                                AND latest.latest = p.captured_at
                       WHERE p.our_sku = ?
                       ORDER BY p.price ASC""",
                    (sku, sku),
                ).fetchall()
                if not rows:
                    continue
                prices = [
                    CompetitorPrice(
                        competitor=r["competitor"],
                        price=Decimal(r["price"]),
                        currency=r["currency"],
                        in_stock=None if r["in_stock"] is None else bool(r["in_stock"]),
                        captured_at=datetime.fromisoformat(r["captured_at"]),
                        confidence=r["confidence"],
                        extractor_method=r["extractor_method"],
                        url=r["url"],
                    )
                    for r in rows
                ]
                # product_name lookup: use the row's url-derived name or sku
                product_name = sku  # we don't store product_name in price_points
                report.comparisons.append(
                    PriceComparison(our_sku=sku, product_name=product_name, prices=prices)
                )

            # Recent changes
            change_rows = conn.execute(
                """SELECT * FROM price_changes
                   WHERE detected_at >= ?
                   ORDER BY ABS(change_percent) DESC""",
                (start.isoformat(),),
            ).fetchall()
            report.changes = [
                ChangeRow(
                    our_sku=r["our_sku"],
                    competitor=r["competitor"],
                    old_price=Decimal(r["old_price"]),
                    new_price=Decimal(r["new_price"]),
                    change_amount=Decimal(r["change_amount"]),
                    change_percent=r["change_percent"],
                    detected_at=datetime.fromisoformat(r["detected_at"]),
                )
                for r in change_rows
            ]

            # Failures grouped by competitor
            fail_rows = conn.execute(
                """SELECT competitor, COUNT(*) AS n,
                          (SELECT error FROM scrape_failures f2
                           WHERE f2.competitor = f1.competitor AND f2.failed_at >= ?
                           ORDER BY failed_at DESC LIMIT 1) AS last_err
                   FROM scrape_failures f1
                   WHERE failed_at >= ?
                   GROUP BY competitor
                   ORDER BY n DESC""",
                (start.isoformat(), start.isoformat()),
            ).fetchall()
            report.failures = [
                FailureRow(
                    competitor=r["competitor"],
                    count=r["n"],
                    last_error=(r["last_err"] or "")[:200],
                )
                for r in fail_rows
            ]

        return report
