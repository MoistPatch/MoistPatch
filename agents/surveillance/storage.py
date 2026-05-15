"""SQLite storage for surveillance agent."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .models import MarketAlert, NewsItem, Relevance, Sentiment, SurveillanceReport

DB_PATH = Path(__file__).parent / "surveillance.db"


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
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                source TEXT,
                published_at TEXT,
                summary TEXT,
                relevance TEXT DEFAULT 'medium',
                sentiment TEXT DEFAULT 'neutral',
                tags TEXT,
                fetched_at TEXT,
                analysed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS market_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT,
                headline TEXT,
                detail TEXT,
                source_url TEXT,
                sentiment TEXT,
                created_at TEXT,
                acknowledged INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS surveillance_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT,
                items_analysed INTEGER,
                executive_summary TEXT,
                opportunities TEXT,
                threats TEXT,
                key_trends TEXT,
                action_items TEXT
            );
        """)


def save_news_item(item: NewsItem) -> NewsItem:
    with _db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO news_items
                   (title, url, source, published_at, summary, relevance, sentiment,
                    tags, fetched_at, analysed)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (item.title, item.url, item.source,
                 item.published_at.isoformat() if item.published_at else None,
                 item.summary, item.relevance.value, item.sentiment.value,
                 json.dumps(item.tags), item.fetched_at.isoformat(), int(item.analysed)),
            )
            item.id = cur.lastrowid
        except sqlite3.IntegrityError:
            pass  # duplicate URL — skip silently
    return item


def update_news_analysis(item_id: int, relevance: Relevance, sentiment: Sentiment,
                          summary: str, tags: list[str]) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE news_items SET relevance=?, sentiment=?, summary=?, tags=?, analysed=1 WHERE id=?",
            (relevance.value, sentiment.value, summary, json.dumps(tags), item_id),
        )


def get_unanalysed_items(limit: int = 30) -> list[NewsItem]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM news_items WHERE analysed=0 ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_to_item(r) for r in rows]


def get_recent_news(limit: int = 30, min_relevance: Relevance = Relevance.MEDIUM) -> list[NewsItem]:
    relevance_order = {"high": 0, "medium": 1, "low": 2, "irrelevant": 3}
    min_rank = relevance_order[min_relevance.value]
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM news_items WHERE analysed=1 ORDER BY fetched_at DESC LIMIT ?",
            (limit * 2,),
        ).fetchall()
    items = [_to_item(r) for r in rows]
    return [i for i in items if relevance_order.get(i.relevance.value, 9) <= min_rank][:limit]


def _to_item(row: sqlite3.Row) -> NewsItem:
    d = _row(row)
    d["relevance"] = Relevance(d["relevance"])
    d["sentiment"] = Sentiment(d["sentiment"])
    d["tags"] = json.loads(d["tags"] or "[]")
    d["analysed"] = bool(d["analysed"])
    if d.get("published_at"):
        d["published_at"] = datetime.fromisoformat(d["published_at"])
    if d.get("fetched_at"):
        d["fetched_at"] = datetime.fromisoformat(d["fetched_at"])
    return NewsItem(**d)


def save_alert(a: MarketAlert) -> MarketAlert:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO market_alerts
               (alert_type, headline, detail, source_url, sentiment, created_at, acknowledged)
               VALUES (?,?,?,?,?,?,?)""",
            (a.alert_type, a.headline, a.detail, a.source_url,
             a.sentiment.value, a.created_at.isoformat(), int(a.acknowledged)),
        )
        a.id = cur.lastrowid
    return a


def get_alerts(limit: int = 20, unacknowledged_only: bool = False) -> list[MarketAlert]:
    with _db() as conn:
        if unacknowledged_only:
            rows = conn.execute(
                "SELECT * FROM market_alerts WHERE acknowledged=0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM market_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_to_alert(r) for r in rows]


def _to_alert(row: sqlite3.Row) -> MarketAlert:
    d = _row(row)
    d["sentiment"] = Sentiment(d["sentiment"])
    d["acknowledged"] = bool(d["acknowledged"])
    if d.get("created_at"):
        d["created_at"] = datetime.fromisoformat(d["created_at"])
    return MarketAlert(**d)


def save_report(r: SurveillanceReport) -> SurveillanceReport:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO surveillance_reports
               (generated_at, items_analysed, executive_summary,
                opportunities, threats, key_trends, action_items)
               VALUES (?,?,?,?,?,?,?)""",
            (r.generated_at.isoformat(), r.items_analysed, r.executive_summary,
             json.dumps(r.opportunities), json.dumps(r.threats),
             json.dumps(r.key_trends), json.dumps(r.action_items)),
        )
        r.id = cur.lastrowid
    return r


def get_latest_report() -> Optional[SurveillanceReport]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM surveillance_reports ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    return _to_report(row) if row else None


def _to_report(row: sqlite3.Row) -> SurveillanceReport:
    d = _row(row)
    for f in ("opportunities", "threats", "key_trends", "action_items"):
        d[f] = json.loads(d[f] or "[]")
    if d.get("generated_at"):
        d["generated_at"] = datetime.fromisoformat(d["generated_at"])
    return SurveillanceReport(**d)
