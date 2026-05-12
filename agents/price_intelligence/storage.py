from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

from .models import PriceChange, PricePoint


SCHEMA = """
CREATE TABLE IF NOT EXISTS price_points (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    our_sku         TEXT NOT NULL,
    competitor      TEXT NOT NULL,
    url             TEXT NOT NULL,
    price           NUMERIC NOT NULL,
    currency        TEXT NOT NULL,
    in_stock        INTEGER,
    captured_at     TEXT NOT NULL,
    extractor_method TEXT NOT NULL,
    confidence      REAL NOT NULL,
    raw_html_excerpt TEXT
);
CREATE INDEX IF NOT EXISTS idx_price_points_sku_comp_ts
    ON price_points(our_sku, competitor, captured_at);

CREATE TABLE IF NOT EXISTS price_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    our_sku         TEXT NOT NULL,
    competitor      TEXT NOT NULL,
    old_price       NUMERIC NOT NULL,
    new_price       NUMERIC NOT NULL,
    change_amount   NUMERIC NOT NULL,
    change_percent  REAL NOT NULL,
    detected_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_changes_sku_ts
    ON price_changes(our_sku, detected_at);

CREATE TABLE IF NOT EXISTS scrape_failures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    our_sku         TEXT NOT NULL,
    competitor      TEXT NOT NULL,
    url             TEXT NOT NULL,
    http_status     INTEGER,
    error           TEXT,
    failed_at       TEXT NOT NULL
);
"""


class PriceStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record_point(self, point: PricePoint) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO price_points
                   (our_sku, competitor, url, price, currency, in_stock,
                    captured_at, extractor_method, confidence, raw_html_excerpt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    point.our_sku,
                    point.competitor,
                    point.url,
                    str(point.price),
                    point.currency,
                    None if point.in_stock is None else int(point.in_stock),
                    point.captured_at.isoformat(),
                    point.extractor_method,
                    point.confidence,
                    point.raw_html_excerpt[:2000],
                ),
            )
            return cur.lastrowid or 0

    def record_change(self, change: PriceChange) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO price_changes
                   (our_sku, competitor, old_price, new_price,
                    change_amount, change_percent, detected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    change.our_sku,
                    change.competitor,
                    str(change.old_price),
                    str(change.new_price),
                    str(change.change_amount),
                    change.change_percent,
                    change.detected_at.isoformat(),
                ),
            )
            return cur.lastrowid or 0

    def record_failure(
        self,
        *,
        our_sku: str,
        competitor: str,
        url: str,
        http_status: int | None,
        error: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO scrape_failures
                   (our_sku, competitor, url, http_status, error, failed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    our_sku,
                    competitor,
                    url,
                    http_status,
                    error[:1000],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def latest_point(self, our_sku: str, competitor: str) -> Optional[PricePoint]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM price_points
                   WHERE our_sku = ? AND competitor = ?
                   ORDER BY captured_at DESC LIMIT 1""",
                (our_sku, competitor),
            ).fetchone()
        return self._row_to_point(row) if row else None

    def history(
        self, our_sku: str, competitor: str, days: int = 30
    ) -> list[PricePoint]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM price_points
                   WHERE our_sku = ? AND competitor = ? AND captured_at >= ?
                   ORDER BY captured_at ASC""",
                (our_sku, competitor, cutoff),
            ).fetchall()
        return [self._row_to_point(r) for r in rows]

    def recent_changes(self, hours: int = 24) -> list[dict]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM price_changes
                   WHERE detected_at >= ?
                   ORDER BY detected_at DESC""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_point(row: sqlite3.Row) -> PricePoint:
        return PricePoint(
            our_sku=row["our_sku"],
            competitor=row["competitor"],
            url=row["url"],
            price=Decimal(row["price"]),
            currency=row["currency"],
            in_stock=None if row["in_stock"] is None else bool(row["in_stock"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
            extractor_method=row["extractor_method"],
            confidence=row["confidence"],
            raw_html_excerpt=row["raw_html_excerpt"] or "",
        )
