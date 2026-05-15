"""SQLite storage for pricing agent."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

from .models import AlertSeverity, PriceAlert, PricePoint, PriceSource, PricingAnalysis

DB_PATH = Path(__file__).parent / "pricing.db"


def _row(r: sqlite3.Row) -> dict:
    return dict(zip(r.keys(), r))


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                price_usd_mt REAL NOT NULL,
                source TEXT,
                source_date TEXT,
                fetched_at TEXT,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_pp_product ON price_points(product);
            CREATE INDEX IF NOT EXISTS idx_pp_source_date ON price_points(source_date DESC);

            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT,
                alert_type TEXT,
                severity TEXT,
                message TEXT,
                price_usd_mt REAL,
                previous_price_usd_mt REAL,
                change_pct REAL,
                created_at TEXT,
                acknowledged INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pricing_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT,
                products_analysed INTEGER,
                market_summary TEXT,
                recommendations TEXT,
                buying_opportunities TEXT,
                risk_warnings TEXT,
                outlook TEXT
            );
        """)


def save_price(p: PricePoint) -> PricePoint:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO price_points
               (product, price_usd_mt, source, source_date, fetched_at, notes)
               VALUES (?,?,?,?,?,?)""",
            (p.product, p.price_usd_mt, p.source.value,
             p.source_date.isoformat(), p.fetched_at.isoformat(), p.notes),
        )
        p.id = cur.lastrowid
    return p


def get_latest_price(product: str) -> Optional[PricePoint]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM price_points WHERE product=? ORDER BY source_date DESC LIMIT 1",
            (product,),
        ).fetchone()
    return _to_price(row) if row else None


def get_price_history(product: str, months: int = 12) -> list[PricePoint]:
    cutoff = (datetime.utcnow() - timedelta(days=months * 30)).isoformat()
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM price_points WHERE product=? AND source_date >= ? ORDER BY source_date ASC",
            (product, cutoff),
        ).fetchall()
    return [_to_price(r) for r in rows]


def get_all_latest_prices() -> dict[str, PricePoint]:
    with _db() as conn:
        rows = conn.execute("""
            SELECT p.* FROM price_points p
            JOIN (SELECT product, MAX(source_date) AS latest FROM price_points GROUP BY product) lp
              ON p.product = lp.product AND p.source_date = lp.latest
        """).fetchall()
    return {r["product"]: _to_price(r) for r in rows}


def _to_price(row: sqlite3.Row) -> PricePoint:
    d = _row(row)
    d["source"] = PriceSource(d["source"])
    for f in ("source_date", "fetched_at"):
        if d.get(f):
            d[f] = datetime.fromisoformat(d[f])
    return PricePoint(**d)


def save_alert(a: PriceAlert) -> PriceAlert:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO price_alerts
               (product, alert_type, severity, message, price_usd_mt,
                previous_price_usd_mt, change_pct, created_at, acknowledged)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (a.product, a.alert_type, a.severity.value, a.message,
             a.price_usd_mt, a.previous_price_usd_mt, a.change_pct,
             a.created_at.isoformat(), int(a.acknowledged)),
        )
        a.id = cur.lastrowid
    return a


def get_alerts(limit: int = 20, unacknowledged_only: bool = False) -> list[PriceAlert]:
    with _db() as conn:
        if unacknowledged_only:
            rows = conn.execute(
                "SELECT * FROM price_alerts WHERE acknowledged=0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM price_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_to_alert(r) for r in rows]


def _to_alert(row: sqlite3.Row) -> PriceAlert:
    d = _row(row)
    d["severity"] = AlertSeverity(d["severity"])
    d["acknowledged"] = bool(d["acknowledged"])
    if d.get("created_at"):
        d["created_at"] = datetime.fromisoformat(d["created_at"])
    return PriceAlert(**d)


def save_analysis(a: PricingAnalysis) -> PricingAnalysis:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO pricing_analyses
               (generated_at, products_analysed, market_summary, recommendations,
                buying_opportunities, risk_warnings, outlook)
               VALUES (?,?,?,?,?,?,?)""",
            (a.generated_at.isoformat(), a.products_analysed, a.market_summary,
             json.dumps(a.recommendations), json.dumps(a.buying_opportunities),
             json.dumps(a.risk_warnings), a.outlook),
        )
        a.id = cur.lastrowid
    return a


def get_latest_analysis() -> Optional[PricingAnalysis]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM pricing_analyses ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    return _to_analysis(row) if row else None


def _to_analysis(row: sqlite3.Row) -> PricingAnalysis:
    d = _row(row)
    d["recommendations"] = json.loads(d["recommendations"] or "[]")
    d["buying_opportunities"] = json.loads(d["buying_opportunities"] or "[]")
    d["risk_warnings"] = json.loads(d["risk_warnings"] or "[]")
    if d.get("generated_at"):
        d["generated_at"] = datetime.fromisoformat(d["generated_at"])
    return PricingAnalysis(**d)
