"""Claude-powered performance analysis and adaptive strategy generation."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import anthropic

from .models import Platform, PostTone, StrategyInsight
from .storage import (
    get_all_metrics_with_posts,
    get_all_insights,
    get_latest_insight,
    lead_counts_by_source,
    save_insight,
)

_MIN_POSTS_FOR_ANALYSIS = 5  # don't bother analysing fewer than this


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _build_performance_table(data: list) -> str:
    """Convert (post, metrics) pairs into a markdown table for Claude."""
    rows = ["| # | Platform | Tone hint | Published | Hashtags | Likes | Comments | Shares | Reach | Impressions | Clicks | Eng% | Content excerpt |"]
    rows.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    for post, m in data:
        hour = post.published_at.hour if post.published_at else "?"
        hashtags = " ".join(post.hashtags[:4])
        excerpt = post.content[:80].replace("|", "/").replace("\n", " ")
        rows.append(
            f"| {post.id} | {post.platform.value} | — | {hour}h UTC | {hashtags} "
            f"| {m.likes} | {m.comments} | {m.shares} | {m.reach} "
            f"| {m.impressions} | {m.clicks} | {m.engagement_rate}% | {excerpt}... |"
        )
    return "\n".join(rows)


def analyse_performance(force: bool = False) -> StrategyInsight | None:
    """
    Analyse all post metrics with Claude and store a StrategyInsight.

    Returns None if there isn't enough data yet (< _MIN_POSTS_FOR_ANALYSIS
    posts with metrics) and force=False.
    """
    data = get_all_metrics_with_posts()
    if len(data) < _MIN_POSTS_FOR_ANALYSIS and not force:
        print(f"[insights] Only {len(data)} posts with metrics — need {_MIN_POSTS_FOR_ANALYSIS} to analyse. Run with force=True to override.")
        return None

    table = _build_performance_table(data) if data else "(no post data yet)"
    lead_attribution = lead_counts_by_source()
    lead_str = json.dumps(lead_attribution, indent=2) if lead_attribution else "{}"

    # Include history of previous insights so Claude can track improvement over time
    prev_insights = get_all_insights(limit=5)
    history_str = ""
    if prev_insights:
        history_str = "\n\nPrevious strategy recommendations (oldest first):\n"
        for ins in reversed(prev_insights):
            history_str += f"\n[{ins.generated_at.strftime('%Y-%m-%d')}] {ins.summary[:200]}...\n"
            for r in ins.recommendations[:3]:
                history_str += f"  • {r}\n"

    prompt = f"""You are the marketing strategist for Vantyx Pty Ltd — an International Commodity Trader
and Importer/Exporter specialising in agricultural fertilisers. You are reviewing social media
performance data to identify what is working, what isn't, and how to improve.

## Post Performance Data ({len(data)} posts with metrics)

{table}

## Lead Attribution by Source Platform

```json
{lead_str}
```
{history_str}

## Your Task

Analyse this data deeply. Consider:
- Which platforms drive the most engagement and leads?
- Which content tones (professional/informative/promotional/engaging) work best per platform?
- Which posting hours (UTC) correlate with higher reach/engagement?
- Which hashtags appear in high-performing posts? Which appear in low-performing ones?
- What content patterns (questions, statistics, product specifics, CTAs) get the most traction?
- Are there any trends improving or declining over time?
- What should we do MORE of? LESS of? STOP entirely?

If data is sparse, acknowledge that and give directional recommendations based on industry
best practices for B2B agricultural commodity marketing.

Respond in this EXACT JSON format — no prose outside the JSON:

{{
  "summary": "2-3 paragraph analysis of overall performance and key trends",
  "recommendations": [
    "Specific, actionable rule #1 (e.g. 'Post on LinkedIn between 07:00-09:00 UTC for 2x reach')",
    "Specific, actionable rule #2",
    "Specific, actionable rule #3",
    "Specific, actionable rule #4",
    "Specific, actionable rule #5"
  ],
  "best_platform": "facebook|instagram|twitter|linkedin|google_ads or null",
  "best_tone": "professional|informative|promotional|engaging or null",
  "best_posting_hour": 8,
  "top_hashtags": ["#Fertiliser", "#AgTech"],
  "avoid_hashtags": ["#lowperformance"]
}}"""

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned non-JSON: {raw[:300]}")

    result = json.loads(match.group())
    insight = StrategyInsight(
        posts_analysed=len(data),
        summary=result["summary"],
        recommendations=result.get("recommendations", []),
        best_platform=result.get("best_platform"),
        best_tone=result.get("best_tone"),
        best_posting_hour=result.get("best_posting_hour"),
        top_hashtags=result.get("top_hashtags", []),
        avoid_hashtags=result.get("avoid_hashtags", []),
    )
    insight = save_insight(insight)
    print(f"[insights] Analysis complete (insight #{insight.id}, {len(data)} posts analysed)")
    return insight


def get_strategy_context() -> str:
    """
    Return a compact strategy block to inject into content generation prompts.
    Empty string if no insights exist yet.
    """
    insight = get_latest_insight()
    if not insight:
        return ""

    lines = ["## Learned Marketing Strategy (from performance analysis)\n"]
    if insight.best_platform:
        lines.append(f"Best-performing platform: {insight.best_platform}")
    if insight.best_tone:
        lines.append(f"Best content tone overall: {insight.best_tone}")
    if insight.best_posting_hour is not None:
        lines.append(f"Optimal posting time: ~{insight.best_posting_hour:02d}:00 UTC")
    if insight.top_hashtags:
        lines.append(f"High-performing hashtags: {', '.join(insight.top_hashtags[:6])}")
    if insight.avoid_hashtags:
        lines.append(f"Avoid these hashtags: {', '.join(insight.avoid_hashtags[:4])}")
    if insight.recommendations:
        lines.append("\nKey rules to follow:")
        for rec in insight.recommendations:
            lines.append(f"  • {rec}")
    lines.append(f"\n(Analysis based on {insight.posts_analysed} posts, generated {insight.generated_at.strftime('%Y-%m-%d')})")

    # Mark insight as applied
    if not insight.applied:
        insight.applied = True
        save_insight(insight)

    return "\n".join(lines)


def should_reanalyse(new_posts_threshold: int = 10) -> bool:
    """
    True if we should run a fresh analysis — either no insight exists,
    or enough new posts with metrics have been published since the last one.
    """
    insight = get_latest_insight()
    if not insight:
        data = get_all_metrics_with_posts()
        return len(data) >= _MIN_POSTS_FOR_ANALYSIS

    data = get_all_metrics_with_posts()
    # Count posts published after the last insight
    new_count = sum(
        1 for post, _ in data
        if post.published_at and post.published_at > insight.generated_at
    )
    return new_count >= new_posts_threshold
