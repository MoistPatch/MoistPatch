"""Fetch engagement metrics from each platform's API and store them."""
from __future__ import annotations

import os
from datetime import datetime

import httpx

from .models import Platform, PostMetrics, SocialPost
from .storage import (
    get_published_posts_without_metrics,
    get_stale_metrics_posts,
    save_metrics,
)


def fetch_facebook_metrics(post: SocialPost) -> PostMetrics:
    token = os.environ["META_PAGE_ACCESS_TOKEN"]
    pid = post.platform_post_id

    # Fetch insights
    r = httpx.get(
        f"https://graph.facebook.com/v19.0/{pid}/insights",
        params={
            "metric": "post_impressions,post_impressions_unique,post_clicks,post_shares",
            "access_token": token,
        },
        timeout=20,
    )
    r.raise_for_status()
    insights = {item["name"]: item["values"][0]["value"] for item in r.json().get("data", [])}

    # Fetch reactions count
    r2 = httpx.get(
        f"https://graph.facebook.com/v19.0/{pid}",
        params={"fields": "reactions.summary(true),comments.summary(true)", "access_token": token},
        timeout=20,
    )
    r2.raise_for_status()
    data2 = r2.json()
    likes = data2.get("reactions", {}).get("summary", {}).get("total_count", 0)
    comments = data2.get("comments", {}).get("summary", {}).get("total_count", 0)

    return PostMetrics(
        post_id=post.id,
        likes=likes,
        comments=comments,
        shares=insights.get("post_shares", 0),
        reach=insights.get("post_impressions_unique", 0),
        impressions=insights.get("post_impressions", 0),
        clicks=insights.get("post_clicks", 0),
    )


def fetch_instagram_metrics(post: SocialPost) -> PostMetrics:
    token = os.environ["META_PAGE_ACCESS_TOKEN"]
    pid = post.platform_post_id

    r = httpx.get(
        f"https://graph.facebook.com/v19.0/{pid}/insights",
        params={
            "metric": "impressions,reach,likes,comments,shares,saved",
            "access_token": token,
        },
        timeout=20,
    )
    r.raise_for_status()
    m = {item["name"]: item["values"][0]["value"] for item in r.json().get("data", [])}

    return PostMetrics(
        post_id=post.id,
        likes=m.get("likes", 0),
        comments=m.get("comments", 0),
        shares=m.get("shares", 0) + m.get("saved", 0),
        reach=m.get("reach", 0),
        impressions=m.get("impressions", 0),
        clicks=0,
    )


def fetch_twitter_metrics(post: SocialPost) -> PostMetrics:
    bearer = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not bearer:
        # Fall back to user context token if bearer not set
        bearer = os.environ.get("TWITTER_ACCESS_TOKEN", "")

    tid = post.platform_post_id
    r = httpx.get(
        f"https://api.twitter.com/2/tweets/{tid}",
        params={"tweet.fields": "public_metrics,non_public_metrics,organic_metrics"},
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=20,
    )
    r.raise_for_status()
    pm = r.json().get("data", {}).get("public_metrics", {})
    nm = r.json().get("data", {}).get("non_public_metrics", {})

    return PostMetrics(
        post_id=post.id,
        likes=pm.get("like_count", 0),
        comments=pm.get("reply_count", 0),
        shares=pm.get("retweet_count", 0) + pm.get("quote_count", 0),
        reach=pm.get("impression_count", 0),
        impressions=pm.get("impression_count", 0),
        clicks=nm.get("url_link_clicks", 0),
    )


def fetch_linkedin_metrics(post: SocialPost) -> PostMetrics:
    token = os.environ["LINKEDIN_ACCESS_TOKEN"]
    org_id = os.environ["LINKEDIN_ORG_ID"]
    share_urn = post.platform_post_id  # e.g. "urn:li:share:..."

    r = httpx.get(
        "https://api.linkedin.com/v2/organizationalEntityShareStatistics",
        params={
            "q": "organizationalEntity",
            "organizationalEntity": f"urn:li:organization:{org_id}",
            "shares[0]": share_urn,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        timeout=20,
    )
    r.raise_for_status()
    elements = r.json().get("elements", [])
    stats = elements[0].get("totalShareStatistics", {}) if elements else {}

    return PostMetrics(
        post_id=post.id,
        likes=stats.get("likeCount", 0),
        comments=stats.get("commentCount", 0),
        shares=stats.get("shareCount", 0),
        reach=stats.get("uniqueImpressionsCount", 0),
        impressions=stats.get("impressionCount", 0),
        clicks=stats.get("clickCount", 0),
    )


_FETCHERS = {
    Platform.FACEBOOK: fetch_facebook_metrics,
    Platform.INSTAGRAM: fetch_instagram_metrics,
    Platform.TWITTER: fetch_twitter_metrics,
    Platform.LINKEDIN: fetch_linkedin_metrics,
}


def fetch_metrics_for_post(post: SocialPost) -> PostMetrics | None:
    fetcher = _FETCHERS.get(post.platform)
    if fetcher is None:
        return None  # Google Ads metrics come from the Ads API separately
    try:
        metrics = fetcher(post)
        metrics.fetched_at = datetime.utcnow()
        return save_metrics(metrics)
    except Exception as exc:
        print(f"[analytics] Failed to fetch metrics for post {post.id} ({post.platform.value}): {exc}")
        return None


def refresh_all_metrics(min_age_hours: int = 6) -> int:
    """
    Fetch metrics for:
    - published posts that have never had metrics recorded
    - published posts whose metrics are older than min_age_hours

    Returns the number of posts successfully updated.
    """
    targets: list[SocialPost] = []
    targets.extend(get_published_posts_without_metrics())
    targets.extend(get_stale_metrics_posts(min_age_hours))

    # Deduplicate by post ID
    seen: set[int] = set()
    unique = []
    for p in targets:
        if p.id not in seen:
            seen.add(p.id)
            unique.append(p)

    count = 0
    for post in unique:
        if fetch_metrics_for_post(post):
            count += 1

    if count:
        print(f"[analytics] Refreshed metrics for {count} post(s)")
    return count
