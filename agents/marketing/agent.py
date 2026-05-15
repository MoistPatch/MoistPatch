"""Vantyx Marketing Agent — main orchestration class."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from .analytics import fetch_metrics_for_post, refresh_all_metrics
from .campaigns import launch_campaign
from .insights import analyse_performance, get_strategy_context, should_reanalyse
from .leads import capture_lead, forward_pending_leads
from .models import Campaign, ContentRequest, Lead, Platform, PostStatus, PostTone, SocialPost, StrategyInsight
from .scheduler import run_scheduler
from .storage import get_all_insights, get_latest_insight, get_leads, get_posts, init_db, save_post


class MarketingAgent:
    """Top-level agent. Call start() to boot the scheduler in a background thread."""

    def __init__(self) -> None:
        init_db()
        self._scheduler_thread: Optional[threading.Thread] = None

    def start(self, scheduler_poll: int = 60) -> None:
        """Start the background scheduler thread."""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            print("[agent] Scheduler already running.")
            return
        self._scheduler_thread = threading.Thread(
            target=run_scheduler,
            args=(scheduler_poll,),
            daemon=True,
            name="vantyx-scheduler",
        )
        self._scheduler_thread.start()
        print("[agent] Marketing agent started. Scheduler running in background.")

    # ── Content & Posting ──────────────────────────────────────────────────

    def draft_post(
        self,
        product: str,
        platform: Platform,
        tone: PostTone = PostTone.PROFESSIONAL,
        schedule_at: Optional[datetime] = None,
        image_url: Optional[str] = None,
    ) -> SocialPost:
        """Generate a post with Claude and optionally schedule it."""
        from .content import generate_post

        content = generate_post(ContentRequest(
            product=product,
            tone=tone,
            platform=platform,
            include_cta=True,
        ))

        status = PostStatus.SCHEDULED if schedule_at else PostStatus.DRAFT
        post = SocialPost(
            platform=platform,
            content=content.post_text,
            hashtags=content.hashtags,
            image_url=image_url,
            scheduled_at=schedule_at,
            status=status,
        )
        return save_post(post)

    def publish_now(self, post: SocialPost) -> SocialPost:
        """Immediately publish a post to its platform."""
        from .social import publish_post

        pid = publish_post(post)
        post.platform_post_id = pid
        post.published_at = datetime.utcnow()
        post.status = PostStatus.PUBLISHED
        return save_post(post)

    # ── Campaigns ─────────────────────────────────────────────────────────

    def run_campaign(
        self,
        name: str,
        product: str,
        target_audience: str,
        platforms: list[Platform],
        budget_aud: float,
        duration_days: int = 30,
        context: Optional[str] = None,
        google_ads_daily: float = 50.0,
    ) -> Campaign:
        """Launch a full multi-channel campaign."""
        return launch_campaign(
            name=name,
            product=product,
            target_audience=target_audience,
            platforms=platforms,
            budget_aud=budget_aud,
            duration_days=duration_days,
            campaign_context=context,
            google_ads_daily_budget=google_ads_daily,
        )

    # ── Leads ─────────────────────────────────────────────────────────────

    def record_lead(
        self,
        source: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        company: Optional[str] = None,
        product_interest: Optional[str] = None,
        quantity_mt: Optional[float] = None,
        message: Optional[str] = None,
    ) -> Lead:
        """Capture and immediately forward a lead to sam@vantyx.com.au."""
        return capture_lead(
            source=source,
            name=name,
            email=email,
            company=company,
            product_interest=product_interest,
            quantity_mt=quantity_mt,
            message=message,
        )

    def flush_leads(self) -> int:
        """Forward any queued leads that haven't been sent yet."""
        return forward_pending_leads()

    # ── Analytics & Learning ──────────────────────────────────────────────

    def refresh_metrics(self, min_age_hours: int = 0) -> int:
        """Pull fresh engagement metrics from all platform APIs. Returns post count updated."""
        return refresh_all_metrics(min_age_hours=min_age_hours)

    def analyse(self, force: bool = False) -> StrategyInsight | None:
        """
        Run Claude performance analysis and store updated strategy rules.
        Pass force=True to analyse even if there aren't many posts yet.
        """
        return analyse_performance(force=force)

    def strategy(self) -> str:
        """Return the current learned strategy as a human-readable string."""
        insight = get_latest_insight()
        if not insight:
            return "No strategy insights yet. Publish some posts and run agent.analyse() first."
        lines = [
            f"Strategy Insight #{insight.id} — {insight.generated_at.strftime('%Y-%m-%d %H:%M')} UTC",
            f"Based on {insight.posts_analysed} posts\n",
            insight.summary,
            "\nRecommendations:",
        ]
        for rec in insight.recommendations:
            lines.append(f"  • {rec}")
        if insight.best_platform:
            lines.append(f"\nBest platform: {insight.best_platform}")
        if insight.best_tone:
            lines.append(f"Best tone: {insight.best_tone}")
        if insight.best_posting_hour is not None:
            lines.append(f"Best hour (UTC): {insight.best_posting_hour:02d}:00")
        if insight.top_hashtags:
            lines.append(f"Top hashtags: {', '.join(insight.top_hashtags)}")
        if insight.avoid_hashtags:
            lines.append(f"Avoid: {', '.join(insight.avoid_hashtags)}")
        return "\n".join(lines)

    def insight_history(self) -> list[StrategyInsight]:
        """Return all past strategy insights, newest first."""
        return get_all_insights()

    # ── Reporting ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        scheduled = get_posts(PostStatus.SCHEDULED)
        published = get_posts(PostStatus.PUBLISHED)
        leads = get_leads()
        latest_insight = get_latest_insight()
        return {
            "scheduler_running": bool(
                self._scheduler_thread and self._scheduler_thread.is_alive()
            ),
            "posts_scheduled": len(scheduled),
            "posts_published": len(published),
            "leads_total": len(leads),
            "leads_unforwarded": sum(1 for l in leads if not l.forwarded),
            "insights_generated": len(get_all_insights()),
            "last_analysis": latest_insight.generated_at.isoformat() if latest_insight else None,
            "ready_to_reanalyse": should_reanalyse(),
        }
