"""SQLite persistence for the Currency Monitor agent."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

DB_PATH = Path(__file__).parent / "currency.db"


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS rate_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            currency_code TEXT NOT NULL,
            rate        REAL NOT NULL,
            fetched_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snap_lookup
            ON rate_snapshots(currency_code, fetched_at);

        CREATE TABLE IF NOT EXISTS rate_alerts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            currency_code TEXT NOT NULL,
            condition     TEXT NOT NULL,
            threshold     REAL NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            triggered_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS alert_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            currency_code TEXT NOT NULL,
            rate          REAL NOT NULL,
            threshold     REAL NOT NULL,
            condition     TEXT NOT NULL,
            triggered_at  TEXT NOT NULL
        );
        """)


def save_snapshots(rates: dict[str, float]) -> None:
    now = datetime.utcnow().isoformat()
    with _db() as conn:
        conn.executemany(
            "INSERT INTO rate_snapshots(currency_code, rate, fetched_at) VALUES(?,?,?)",
            [(code, rate, now) for code, rate in rates.items()],
        )


def get_latest_rates() -> dict[str, dict]:
    """Most recent rate for every currency we've ever stored."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT currency_code, rate, fetched_at
            FROM rate_snapshots
            WHERE (currency_code, fetched_at) IN (
                SELECT currency_code, MAX(fetched_at)
                FROM rate_snapshots
                GROUP BY currency_code
            )
        """).fetchall()
    return {r["currency_code"]: {"rate": r["rate"], "fetched_at": r["fetched_at"]} for r in rows}


def get_rate_at(code: str, at: datetime) -> Optional[float]:
    """Most recent rate for *code* at or before *at*."""
    with _db() as conn:
        row = conn.execute(
            """SELECT rate FROM rate_snapshots
               WHERE currency_code=? AND fetched_at<=?
               ORDER BY fetched_at DESC LIMIT 1""",
            (code, at.isoformat()),
        ).fetchone()
    return row["rate"] if row else None


def get_daily_rates(code: str, days: int = 7) -> list[float]:
    """One averaged rate per calendar day for the past *days* days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _db() as conn:
        rows = conn.execute(
            """SELECT DATE(fetched_at) AS day, AVG(rate) AS rate
               FROM rate_snapshots
               WHERE currency_code=? AND fetched_at>=?
               GROUP BY day ORDER BY day ASC""",
            (code, since),
        ).fetchall()
    return [r["rate"] for r in rows]


def get_rate_history(code: str, days: int = 30) -> list[dict]:
    """Daily averaged rates for charting."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _db() as conn:
        rows = conn.execute(
            """SELECT DATE(fetched_at) AS day, AVG(rate) AS rate
               FROM rate_snapshots
               WHERE currency_code=? AND fetched_at>=?
               GROUP BY day ORDER BY day ASC""",
            (code, since),
        ).fetchall()
    return [{"date": r["day"], "rate": round(r["rate"], 6)} for r in rows]


def save_alert(code: str, condition: str, threshold: float) -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO rate_alerts(currency_code, condition, threshold, created_at) VALUES(?,?,?,?)",
            (code, condition, threshold, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def get_active_alerts() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, currency_code, condition, threshold, created_at FROM rate_alerts WHERE active=1"
        ).fetchall()
    return [dict(r) for r in rows]


def deactivate_alert(alert_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE rate_alerts SET active=0, triggered_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), alert_id),
        )


def delete_alert(alert_id: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM rate_alerts WHERE id=?", (alert_id,))


def save_alert_trigger(code: str, rate: float, threshold: float, condition: str) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO alert_history(currency_code, rate, threshold, condition, triggered_at) VALUES(?,?,?,?,?)",
            (code, rate, threshold, condition, datetime.utcnow().isoformat()),
        )


def get_alert_history(limit: int = 20) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """SELECT id, currency_code, rate, threshold, condition, triggered_at
               FROM alert_history ORDER BY triggered_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def snapshot_count() -> int:
    with _db() as conn:
        return conn.execute("SELECT COUNT(DISTINCT fetched_at) FROM rate_snapshots").fetchone()[0]
