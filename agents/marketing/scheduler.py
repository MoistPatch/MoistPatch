"""Post scheduler — polls SQLite every minute and publishes due posts."""
from __future__ import annotations

import time
from datetime import datetime

from .models import PostStatus
from .social import publish_post
from .storage import get_due_posts, save_post


def run_scheduler(poll_interval: int = 60) -> None:
    """Blocking scheduler loop. Checks for due posts every poll_interval seconds."""
    print(f"[scheduler] Started — polling every {poll_interval}s. Press Ctrl+C to stop.")
    while True:
        _tick()
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
