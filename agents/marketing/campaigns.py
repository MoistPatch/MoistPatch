"""Multi-channel campaign orchestration."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .content import generate_campaign_posts
from .google_ads import (
    FERTILISER_KEYWORDS,
    add_keywords,
    add_responsive_search_ad,
    create_search_campaign,
    enable_campaign,
)
from .models import Campaign, CampaignStatus, Platform, SocialPost, PostStatus
from .storage import save_campaign, save_post


def launch_campaign(
    name: str,
    product: str,
    target_audience: str,
    platforms: list[Platform],
    budget_aud: float,
    duration_days: int = 30,
    campaign_context: Optional[str] = None,
    google_ads_daily_budget: float = 50.0,
    start_offset_hours: int = 1,
) -> Campaign:
    """
    Full campaign launch:
    1. Save campaign record
    2. Generate & schedule social posts
    3. Create Google Ads search campaign (if Platform.GOOGLE_ADS in platforms)
    """
    start = datetime.utcnow()
    end = start + timedelta(days=duration_days)

    campaign = Campaign(
        name=name,
        description=campaign_context or f"{product} marketing campaign",
        product=product,
        target_audience=target_audience,
        platforms=platforms,
        budget_aud=budget_aud,
        start_date=start,
        end_date=end,
        status=CampaignStatus.ACTIVE,
    )
    campaign = save_campaign(campaign)

    social_platforms = [p for p in platforms if p != Platform.GOOGLE_ADS]

    if social_platforms:
        print(f"[campaigns] Generating content for {[p.value for p in social_platforms]}...")
        content_map = generate_campaign_posts(
            product=product,
            platforms=social_platforms,
            campaign_context=campaign_context or f"Campaign: {name}. Audience: {target_audience}",
        )

        schedule_base = datetime.utcnow() + timedelta(hours=start_offset_hours)
        for i, (platform, content) in enumerate(content_map.items()):
            post = SocialPost(
                platform=platform,
                content=content.post_text,
                hashtags=content.hashtags,
                image_url=None,
                scheduled_at=schedule_base + timedelta(hours=i * 2),
                status=PostStatus.SCHEDULED,
                campaign_id=campaign.id,
            )
            save_post(post)
            print(f"[campaigns] Scheduled {platform.value} post at {post.scheduled_at}")

    if Platform.GOOGLE_ADS in platforms:
        print("[campaigns] Creating Google Ads search campaign...")
        try:
            campaign_resource = create_search_campaign(
                name=name,
                daily_budget_aud=google_ads_daily_budget,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )

            # Generate ad copy for Google Ads if available
            from .content import generate_post
            from .models import ContentRequest, PostTone

            ads_content = generate_post(ContentRequest(
                product=product,
                tone=PostTone.PROMOTIONAL,
                platform=Platform.GOOGLE_ADS,
                include_cta=True,
                campaign_context=campaign_context,
            ))

            headlines = [ads_content.ad_headline or f"Buy {product} — Vantyx", "Global Fertiliser Trader", "Australian Importer/Exporter"]
            descriptions = [
                ads_content.ad_description or "Premium fertiliser. Competitive pricing. Global supply.",
                "Submit an LOI to secure your stock allocation today.",
            ]

            ag_resource = add_responsive_search_ad(
                campaign_resource=campaign_resource,
                ad_group_name=f"{name} — Search",
                headlines=headlines,
                descriptions=descriptions,
            )
            add_keywords(campaign_resource, ag_resource, FERTILISER_KEYWORDS)
            enable_campaign(campaign_resource)
            print(f"[campaigns] Google Ads campaign created and enabled: {campaign_resource}")
        except Exception as exc:
            print(f"[campaigns] Google Ads setup failed (check credentials): {exc}")

    return campaign
