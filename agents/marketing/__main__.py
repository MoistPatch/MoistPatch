"""CLI entry point: python -m agents.marketing <command> [options]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load .env from repo root before anything else
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from .agent import MarketingAgent
from .models import Platform, PostTone


def _platform(s: str) -> Platform:
    try:
        return Platform(s.lower())
    except ValueError:
        choices = [p.value for p in Platform]
        raise argparse.ArgumentTypeError(f"Invalid platform '{s}'. Choose from: {choices}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m agents.marketing",
        description="Vantyx Marketing Agent CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ── status ──────────────────────────────────────────────────────────
    sub.add_parser("status", help="Show agent status and stats")

    # ── draft ───────────────────────────────────────────────────────────
    p_draft = sub.add_parser("draft", help="Generate and optionally schedule a post")
    p_draft.add_argument("product", help="Product to write about (e.g. 'Urea 46%')")
    p_draft.add_argument("platform", type=_platform, help="facebook|instagram|twitter|linkedin|google_ads")
    p_draft.add_argument("--tone", default="professional",
                         choices=[t.value for t in PostTone], help="Content tone")
    p_draft.add_argument("--schedule", metavar="HOURS",
                         type=int, help="Schedule post N hours from now")
    p_draft.add_argument("--image-url", help="Public image URL to attach")

    # ── publish ─────────────────────────────────────────────────────────
    p_pub = sub.add_parser("publish", help="Immediately publish a draft post by ID")
    p_pub.add_argument("post_id", type=int)

    # ── campaign ────────────────────────────────────────────────────────
    p_camp = sub.add_parser("campaign", help="Launch a multi-channel campaign")
    p_camp.add_argument("name", help="Campaign name")
    p_camp.add_argument("product", help="Product being marketed")
    p_camp.add_argument("--audience", default="agricultural buyers and distributors globally")
    p_camp.add_argument("--platforms", nargs="+", type=_platform,
                        default=[Platform.FACEBOOK, Platform.LINKEDIN, Platform.TWITTER],
                        metavar="PLATFORM")
    p_camp.add_argument("--budget", type=float, default=500.0, help="Total budget AUD")
    p_camp.add_argument("--days", type=int, default=30, help="Campaign duration in days")
    p_camp.add_argument("--context", help="Additional context for content generation")
    p_camp.add_argument("--ads-daily", type=float, default=50.0,
                        help="Google Ads daily budget AUD (if google_ads in platforms)")

    # ── lead ────────────────────────────────────────────────────────────
    p_lead = sub.add_parser("lead", help="Manually record and forward a lead")
    p_lead.add_argument("--source", default="cli")
    p_lead.add_argument("--name")
    p_lead.add_argument("--email")
    p_lead.add_argument("--company")
    p_lead.add_argument("--product")
    p_lead.add_argument("--qty", type=float, help="Quantity in metric tonnes")
    p_lead.add_argument("--message")

    # ── flush-leads ──────────────────────────────────────────────────────
    sub.add_parser("flush-leads", help="Forward all queued leads to sam@vantyx.com.au")

    # ── scheduler ────────────────────────────────────────────────────────
    p_sched = sub.add_parser("scheduler", help="Run the scheduler (blocking)")
    p_sched.add_argument("--poll", type=int, default=60, help="Poll interval in seconds")

    # ── posts ────────────────────────────────────────────────────────────
    p_posts = sub.add_parser("posts", help="List posts")
    p_posts.add_argument("--status", choices=["draft", "scheduled", "published", "failed"])

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY") and args.cmd in ("draft", "campaign"):
        print("ERROR: ANTHROPIC_API_KEY is not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    agent = MarketingAgent()

    if args.cmd == "status":
        s = agent.status()
        print(json.dumps(s, indent=2))

    elif args.cmd == "draft":
        schedule_at = (
            datetime.utcnow() + timedelta(hours=args.schedule) if args.schedule else None
        )
        post = agent.draft_post(
            product=args.product,
            platform=args.platform,
            tone=PostTone(args.tone),
            schedule_at=schedule_at,
            image_url=args.image_url,
        )
        print(f"Post #{post.id} [{post.status.value}] on {post.platform.value}:")
        print(post.content)
        if post.hashtags:
            print(" ".join(post.hashtags))
        if post.scheduled_at:
            print(f"Scheduled: {post.scheduled_at.isoformat()} UTC")

    elif args.cmd == "publish":
        from .storage import get_posts
        from .models import PostStatus

        posts = get_posts()
        match = next((p for p in posts if p.id == args.post_id), None)
        if not match:
            print(f"Post #{args.post_id} not found.", file=sys.stderr)
            sys.exit(1)
        result = agent.publish_now(match)
        print(f"Published post #{result.id} → platform ID: {result.platform_post_id}")

    elif args.cmd == "campaign":
        camp = agent.run_campaign(
            name=args.name,
            product=args.product,
            target_audience=args.audience,
            platforms=args.platforms,
            budget_aud=args.budget,
            duration_days=args.days,
            context=args.context,
            google_ads_daily=args.ads_daily,
        )
        print(f"Campaign #{camp.id} '{camp.name}' launched ({camp.status.value})")

    elif args.cmd == "lead":
        lead = agent.record_lead(
            source=args.source,
            name=args.name,
            email=args.email,
            company=args.company,
            product_interest=args.product,
            quantity_mt=args.qty,
            message=args.message,
        )
        print(f"Lead #{lead.id} recorded and forwarded={lead.forwarded}")

    elif args.cmd == "flush-leads":
        count = agent.flush_leads()
        print(f"Forwarded {count} lead(s).")

    elif args.cmd == "scheduler":
        agent.start(scheduler_poll=args.poll)
        # Keep main thread alive
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[agent] Stopping.")

    elif args.cmd == "posts":
        from .models import PostStatus
        from .storage import get_posts

        status = PostStatus(args.status) if args.status else None
        posts = get_posts(status=status)
        if not posts:
            print("No posts found.")
        for p in posts:
            ts = p.scheduled_at or p.published_at or p.created_at
            print(f"  #{p.id:4d} [{p.status.value:10s}] {p.platform.value:12s} {ts.strftime('%Y-%m-%d %H:%M')} — {p.content[:60]}...")


if __name__ == "__main__":
    main()
