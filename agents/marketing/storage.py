"""SQLite-backed storage for posts, campaigns, and leads."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .models import Campaign, CampaignStatus, Lead, Platform, PostStatus, SocialPost

DB_PATH = Path(__file__).parent / "marketing.db"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(zip(row.keys(), row))


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
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                product TEXT,
                target_audience TEXT,
                platforms TEXT,
                budget_aud REAL,
                start_date TEXT,
                end_date TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                hashtags TEXT,
                image_url TEXT,
                image_path TEXT,
                scheduled_at TEXT,
                published_at TEXT,
                status TEXT DEFAULT 'draft',
                platform_post_id TEXT,
                campaign_id INTEGER,
                created_at TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            );

            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                name TEXT,
                email TEXT,
                company TEXT,
                product_interest TEXT,
                quantity_mt REAL,
                message TEXT,
                forwarded INTEGER DEFAULT 0,
                created_at TEXT
            );
        """)


def save_post(post: SocialPost) -> SocialPost:
    with _db() as conn:
        if post.id is None:
            cur = conn.execute(
                """INSERT INTO posts
                   (platform, content, hashtags, image_url, image_path,
                    scheduled_at, published_at, status, platform_post_id,
                    campaign_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post.platform.value,
                    post.content,
                    json.dumps(post.hashtags),
                    post.image_url,
                    post.image_path,
                    post.scheduled_at.isoformat() if post.scheduled_at else None,
                    post.published_at.isoformat() if post.published_at else None,
                    post.status.value,
                    post.platform_post_id,
                    post.campaign_id,
                    post.created_at.isoformat(),
                ),
            )
            post.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE posts SET platform=?, content=?, hashtags=?, image_url=?,
                   image_path=?, scheduled_at=?, published_at=?, status=?,
                   platform_post_id=?, campaign_id=? WHERE id=?""",
                (
                    post.platform.value,
                    post.content,
                    json.dumps(post.hashtags),
                    post.image_url,
                    post.image_path,
                    post.scheduled_at.isoformat() if post.scheduled_at else None,
                    post.published_at.isoformat() if post.published_at else None,
                    post.status.value,
                    post.platform_post_id,
                    post.campaign_id,
                    post.id,
                ),
            )
    return post


def get_due_posts() -> list[SocialPost]:
    now = datetime.utcnow().isoformat()
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at <= ?",
            (now,),
        ).fetchall()
    return [_row_to_post(r) for r in rows]


def get_posts(status: Optional[PostStatus] = None, limit: int = 50) -> list[SocialPost]:
    with _db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM posts WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_post(r) for r in rows]


def _row_to_post(row: sqlite3.Row) -> SocialPost:
    d = _row_to_dict(row)
    d["hashtags"] = json.loads(d["hashtags"] or "[]")
    d["platform"] = Platform(d["platform"])
    d["status"] = PostStatus(d["status"])
    for f in ("scheduled_at", "published_at", "created_at"):
        if d[f]:
            d[f] = datetime.fromisoformat(d[f])
    return SocialPost(**d)


def save_campaign(campaign: Campaign) -> Campaign:
    with _db() as conn:
        if campaign.id is None:
            cur = conn.execute(
                """INSERT INTO campaigns
                   (name, description, product, target_audience, platforms,
                    budget_aud, start_date, end_date, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    campaign.name,
                    campaign.description,
                    campaign.product,
                    campaign.target_audience,
                    json.dumps([p.value for p in campaign.platforms]),
                    campaign.budget_aud,
                    campaign.start_date.isoformat(),
                    campaign.end_date.isoformat() if campaign.end_date else None,
                    campaign.status.value,
                    campaign.created_at.isoformat(),
                ),
            )
            campaign.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE campaigns SET name=?, description=?, product=?,
                   target_audience=?, platforms=?, budget_aud=?, start_date=?,
                   end_date=?, status=? WHERE id=?""",
                (
                    campaign.name,
                    campaign.description,
                    campaign.product,
                    campaign.target_audience,
                    json.dumps([p.value for p in campaign.platforms]),
                    campaign.budget_aud,
                    campaign.start_date.isoformat(),
                    campaign.end_date.isoformat() if campaign.end_date else None,
                    campaign.status.value,
                    campaign.id,
                ),
            )
    return campaign


def save_lead(lead: Lead) -> Lead:
    with _db() as conn:
        if lead.id is None:
            cur = conn.execute(
                """INSERT INTO leads
                   (source, name, email, company, product_interest,
                    quantity_mt, message, forwarded, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    lead.source,
                    lead.name,
                    lead.email,
                    lead.company,
                    lead.product_interest,
                    lead.quantity_mt,
                    lead.message,
                    int(lead.forwarded),
                    lead.created_at.isoformat(),
                ),
            )
            lead.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE leads SET forwarded=? WHERE id=?", (int(lead.forwarded), lead.id)
            )
    return lead


def get_unforwarded_leads() -> list[Lead]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE forwarded=0 ORDER BY created_at ASC"
        ).fetchall()
    return [_row_to_lead(r) for r in rows]


def get_leads(limit: int = 50) -> list[Lead]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_lead(r) for r in rows]


def _row_to_lead(row: sqlite3.Row) -> Lead:
    d = _row_to_dict(row)
    d["forwarded"] = bool(d["forwarded"])
    if d["created_at"]:
        d["created_at"] = datetime.fromisoformat(d["created_at"])
    return Lead(**d)
