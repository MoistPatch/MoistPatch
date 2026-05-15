"""SQLite-backed storage for posts, campaigns, and leads."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

from .models import Campaign, CampaignStatus, Lead, Platform, PostMetrics, PostStatus, SocialPost, StrategyInsight

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

            CREATE TABLE IF NOT EXISTS post_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                fetched_at TEXT,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                FOREIGN KEY (post_id) REFERENCES posts(id)
            );

            CREATE TABLE IF NOT EXISTS strategy_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT,
                posts_analysed INTEGER,
                summary TEXT,
                recommendations TEXT,
                best_platform TEXT,
                best_tone TEXT,
                best_posting_hour INTEGER,
                top_hashtags TEXT,
                avoid_hashtags TEXT,
                applied INTEGER DEFAULT 0
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


# ── Metrics ───────────────────────────────────────────────────────────────

def save_metrics(m: PostMetrics) -> PostMetrics:
    with _db() as conn:
        if m.id is None:
            cur = conn.execute(
                """INSERT INTO post_metrics
                   (post_id, fetched_at, likes, comments, shares, reach, impressions, clicks)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (m.post_id, m.fetched_at.isoformat(), m.likes, m.comments,
                 m.shares, m.reach, m.impressions, m.clicks),
            )
            m.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE post_metrics SET fetched_at=?, likes=?, comments=?, shares=?,
                   reach=?, impressions=?, clicks=? WHERE id=?""",
                (m.fetched_at.isoformat(), m.likes, m.comments, m.shares,
                 m.reach, m.impressions, m.clicks, m.id),
            )
    return m


def get_latest_metrics(post_id: int) -> Optional[PostMetrics]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM post_metrics WHERE post_id=? ORDER BY fetched_at DESC LIMIT 1",
            (post_id,),
        ).fetchone()
    return _row_to_metrics(row) if row else None


def get_all_metrics_with_posts(min_impressions: int = 0) -> list[tuple[SocialPost, PostMetrics]]:
    """Return (post, latest_metrics) for every published post that has metrics."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT p.*, m.id AS m_id, m.fetched_at, m.likes, m.comments,
                   m.shares, m.reach, m.impressions, m.clicks
            FROM posts p
            JOIN (
                SELECT post_id, MAX(fetched_at) AS latest FROM post_metrics GROUP BY post_id
            ) latest_m ON p.id = latest_m.post_id
            JOIN post_metrics m ON m.post_id = p.id AND m.fetched_at = latest_m.latest
            WHERE p.status = 'published' AND m.impressions >= ?
            ORDER BY m.impressions DESC
        """, (min_impressions,)).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        post = _row_to_post_from_dict({
            "id": d["id"], "platform": d["platform"], "content": d["content"],
            "hashtags": d["hashtags"], "image_url": d["image_url"],
            "image_path": d["image_path"], "scheduled_at": d["scheduled_at"],
            "published_at": d["published_at"], "status": d["status"],
            "platform_post_id": d["platform_post_id"], "campaign_id": d["campaign_id"],
            "created_at": d["created_at"],
        })
        metrics = PostMetrics(
            id=d["m_id"],
            post_id=d["id"],
            fetched_at=datetime.fromisoformat(d["fetched_at"]),
            likes=d["likes"], comments=d["comments"], shares=d["shares"],
            reach=d["reach"], impressions=d["impressions"], clicks=d["clicks"],
        )
        results.append((post, metrics))
    return results


def get_published_posts_without_metrics() -> list[SocialPost]:
    """Return published posts that have never had metrics fetched."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT p.* FROM posts p
            LEFT JOIN post_metrics m ON m.post_id = p.id
            WHERE p.status = 'published' AND p.platform_post_id IS NOT NULL
              AND m.id IS NULL
        """).fetchall()
    return [_row_to_post(r) for r in rows]


def get_stale_metrics_posts(min_age_hours: int = 6) -> list[SocialPost]:
    """Return published posts whose metrics haven't been refreshed recently."""
    cutoff = (datetime.utcnow() - timedelta(hours=min_age_hours)).isoformat()
    with _db() as conn:
        rows = conn.execute("""
            SELECT p.* FROM posts p
            JOIN (
                SELECT post_id, MAX(fetched_at) AS latest FROM post_metrics GROUP BY post_id
            ) lm ON p.id = lm.post_id
            WHERE p.status = 'published' AND p.platform_post_id IS NOT NULL
              AND lm.latest < ?
        """, (cutoff,)).fetchall()
    return [_row_to_post(r) for r in rows]


def _row_to_metrics(row: sqlite3.Row) -> PostMetrics:
    d = _row_to_dict(row)
    if d.get("fetched_at"):
        d["fetched_at"] = datetime.fromisoformat(d["fetched_at"])
    return PostMetrics(**d)


def _row_to_post_from_dict(d: dict) -> SocialPost:
    d["hashtags"] = json.loads(d["hashtags"] or "[]")
    d["platform"] = Platform(d["platform"])
    d["status"] = PostStatus(d["status"])
    for f in ("scheduled_at", "published_at", "created_at"):
        if d[f]:
            d[f] = datetime.fromisoformat(d[f])
    return SocialPost(**d)


# ── Strategy Insights ─────────────────────────────────────────────────────

def save_insight(insight: StrategyInsight) -> StrategyInsight:
    with _db() as conn:
        if insight.id is None:
            cur = conn.execute(
                """INSERT INTO strategy_insights
                   (generated_at, posts_analysed, summary, recommendations,
                    best_platform, best_tone, best_posting_hour,
                    top_hashtags, avoid_hashtags, applied)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    insight.generated_at.isoformat(),
                    insight.posts_analysed,
                    insight.summary,
                    json.dumps(insight.recommendations),
                    insight.best_platform,
                    insight.best_tone,
                    insight.best_posting_hour,
                    json.dumps(insight.top_hashtags),
                    json.dumps(insight.avoid_hashtags),
                    int(insight.applied),
                ),
            )
            insight.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE strategy_insights SET applied=? WHERE id=?",
                (int(insight.applied), insight.id),
            )
    return insight


def get_latest_insight() -> Optional[StrategyInsight]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_insights ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    return _row_to_insight(row) if row else None


def get_all_insights(limit: int = 20) -> list[StrategyInsight]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM strategy_insights ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_insight(r) for r in rows]


def _row_to_insight(row: sqlite3.Row) -> StrategyInsight:
    d = _row_to_dict(row)
    d["recommendations"] = json.loads(d["recommendations"] or "[]")
    d["top_hashtags"] = json.loads(d["top_hashtags"] or "[]")
    d["avoid_hashtags"] = json.loads(d["avoid_hashtags"] or "[]")
    d["applied"] = bool(d["applied"])
    if d["generated_at"]:
        d["generated_at"] = datetime.fromisoformat(d["generated_at"])
    return StrategyInsight(**d)


def lead_counts_by_source() -> dict[str, int]:
    """Count leads grouped by source platform for attribution analysis."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM leads GROUP BY source"
        ).fetchall()
    return {r["source"]: r["cnt"] for r in rows}
