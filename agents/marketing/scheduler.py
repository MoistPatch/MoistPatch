"""Post scheduler — polls SQLite every minute, publishes due posts, and drives the learning loop."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from .models import PostStatus
from .social import publish_post
from .storage import get_due_posts, save_post

# Metrics refresh: every 6 hours
_METRICS_INTERVAL = timedelta(hours=6)
_last_metrics_refresh: datetime | None = None

# Re-analyse strategy every time 10 new posts have metrics
_REANALYSE_THRESHOLD = 10


def run_scheduler(poll_interval: int = 60) -> None:
    """Blocking scheduler loop. Checks for due posts every poll_interval seconds."""
    print(f"[scheduler] Started — polling every {poll_interval}s. Press Ctrl+C to stop.")
    while True:
        _tick()
        _maybe_refresh_metrics()
        time.sleep(poll_interval)


def _tick() -> None:
    due = get_due_posts()
    if not due:
        return

    print(f"[scheduler] {len(due)} post(s) due at {datetime.utcnow().isoformat()}")
    for post in due:
        try:
            platform_id = publish_post(post)
            post.platform_post_id = platform_id
            post.published_at = datetime.utcnow()
            post.status = PostStatus.PUBLISHED
            print(f"[scheduler] Published post {post.id} on {post.platform.value} → {platform_id}")
        except Exception as exc:
            post.status = PostStatus.FAILED
            print(f"[scheduler] Failed post {post.id} on {post.platform.value}: {exc}")
        save_post(post)


def _maybe_refresh_metrics() -> None:
    """Refresh metrics every _METRICS_INTERVAL, then re-analyse strategy if warranted."""
    global _last_metrics_refresh

    now = datetime.utcnow()
    if _last_metrics_refresh and now - _last_metrics_refresh < _METRICS_INTERVAL:
        return

    _last_metrics_refresh = now
    try:
        from .analytics import refresh_all_metrics
        updated = refresh_all_metrics(min_age_hours=6)

        if updated > 0:
            from .insights import should_reanalyse, analyse_performance
            if should_reanalyse(new_posts_threshold=_REANALYSE_THRESHOLD):
                print("[scheduler] Triggering strategy re-analysis...")
                analyse_performance()
    except Exception as exc:
        print(f"[scheduler] Learning loop error: {exc}")
