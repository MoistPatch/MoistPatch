from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

from .models import PricingDecision


SCHEMA = """
CREATE TABLE IF NOT EXISTS pricing_decisions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    our_sku                  TEXT NOT NULL,
    product_name             TEXT NOT NULL,
    current_price            NUMERIC NOT NULL,
    recommended_price        NUMERIC NOT NULL,
    cogs                     NUMERIC NOT NULL,
    min_price                NUMERIC NOT NULL,
    change_amount            NUMERIC NOT NULL,
    change_pct               REAL NOT NULL,
    new_margin_pct           REAL NOT NULL,
    competitors_seen         INTEGER NOT NULL,
    cheapest_competitor      TEXT,
    cheapest_in_stock_price  NUMERIC,
    our_position             INTEGER,
    strategy                 TEXT NOT NULL,
    rationale                TEXT NOT NULL,
    status                   TEXT NOT NULL,
    auto_apply_threshold_pct REAL NOT NULL,
    created_at               TEXT NOT NULL,
    reviewed_at              TEXT,
    reviewer                 TEXT,
    review_reason            TEXT
);
CREATE INDEX IF NOT EXISTS idx_pd_sku_created ON pricing_decisions(our_sku, created_at);
CREATE INDEX IF NOT EXISTS idx_pd_status      ON pricing_decisions(status, created_at);
"""


class DecisionStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record(self, d: PricingDecision) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO pricing_decisions
                   (our_sku, product_name, current_price, recommended_price,
                    cogs, min_price, change_amount, change_pct, new_margin_pct,
                    competitors_seen, cheapest_competitor, cheapest_in_stock_price,
                    our_position, strategy, rationale, status,
                    auto_apply_threshold_pct, created_at, reviewed_at, reviewer,
                    review_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d.our_sku, d.product_name,
                    str(d.current_price), str(d.recommended_price),
                    str(d.cogs), str(d.min_price),
                    str(d.change_amount), d.change_pct, d.new_margin_pct,
                    d.competitors_seen, d.cheapest_competitor,
                    str(d.cheapest_in_stock_price) if d.cheapest_in_stock_price is not None else None,
                    d.our_position, d.strategy, d.rationale, d.status,
                    d.auto_apply_threshold_pct, d.created_at.isoformat(),
                    d.reviewed_at.isoformat() if d.reviewed_at else None,
                    d.reviewer, d.review_reason,
                ),
            )
            return cur.lastrowid or 0

    def get(self, decision_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pricing_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_by_status(self, status: str, limit: int = 100) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM pricing_decisions
                   WHERE status = ? ORDER BY created_at DESC LIMIT ?""",
                (status, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_status(
        self,
        decision_id: int,
        status: str,
        *,
        reviewer: Optional[str] = None,
        review_reason: Optional[str] = None,
    ) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE pricing_decisions
                   SET status = ?, reviewed_at = ?, reviewer = ?, review_reason = ?
                   WHERE id = ?""",
                (
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    reviewer, review_reason, decision_id,
                ),
            )
            return cur.rowcount > 0

    def latest_for_sku(self, our_sku: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM pricing_decisions
                   WHERE our_sku = ? ORDER BY created_at DESC LIMIT 1""",
                (our_sku,),
            ).fetchone()
        return dict(row) if row else None
