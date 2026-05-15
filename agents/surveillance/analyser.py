"""Claude-powered news analysis and market intelligence reporting."""
from __future__ import annotations

import json
import os
import re

import anthropic

from .models import MarketAlert, NewsItem, Relevance, Sentiment, SurveillanceReport
from .storage import (
    get_recent_news,
    get_unanalysed_items,
    save_alert,
    save_report,
    update_news_analysis,
)

_BATCH_SIZE = 20  # analyse this many items per Claude call


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _vantyx_context() -> str:
    return """Vantyx Pty Ltd (ABN 84 544 119 830) — Australian International Commodity Trader
and Importer/Exporter of agricultural fertilisers. Based Melbourne, Victoria.
Products: Urea 46%, DAP 18-46-0, MAP 12-61-0, MOP, SOP, SSP, TSP, CAN, Ammonia, Zinc Sulphate, NPK blends.
Global sourcing from Middle East, North Africa, China, Eastern Europe, Americas, Southeast Asia.
Target customers: Australian and international agricultural buyers, distributors, co-operatives.
Contact: sam@vantyx.com.au"""


def classify_news_batch(items: list[NewsItem]) -> None:
    """Classify relevance and sentiment for a batch of unanalysed news items."""
    if not items:
        return

    items_text = "\n".join(
        f"{i}. [{item.source}] {item.title}\n   {(item.summary or '')[:200]}"
        for i, item in enumerate(items, 1)
    )

    prompt = f"""You are a market intelligence analyst for Vantyx Pty Ltd.

{_vantyx_context()}

Classify each news item below for relevance to Vantyx's business and sentiment (opportunity/threat/neutral).

IMPORTANT: Base your analysis ONLY on the title and summary text provided for each item. Do NOT invent, assume, or add information not present in the item text. Summaries must be derived solely from the provided text.

News items to classify:
{items_text}

For each item, respond with a JSON array (one object per item, in order):
[
  {{
    "index": 1,
    "relevance": "high|medium|low|irrelevant",
    "sentiment": "opportunity|threat|neutral",
    "summary": "One sentence drawn only from the provided title/text explaining relevance to Vantyx (or 'Not relevant' if irrelevant)",
    "tags": ["urea", "price_rise", "supply_disruption"]
  }},
  ...
]

Relevance guide:
- high: directly affects Vantyx's products, pricing, supply, or customers
- medium: related to agricultural inputs, commodity markets, Australia agriculture
- low: loosely related (general agriculture, broader commodities)
- irrelevant: not related to Vantyx's business

Only output the JSON array."""

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in response.content if b.type == "text")
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        print(f"[surveillance] Claude returned non-JSON: {raw[:200]}")
        return

    results = json.loads(match.group())
    for result in results:
        idx = result.get("index", 0) - 1
        if 0 <= idx < len(items):
            item = items[idx]
            if item.id:
                update_news_analysis(
                    item.id,
                    Relevance(result.get("relevance", "medium")),
                    Sentiment(result.get("sentiment", "neutral")),
                    result.get("summary", ""),
                    result.get("tags", []),
                )


def analyse_unanalysed() -> int:
    """Classify all unanalysed news items in batches. Returns count processed."""
    items = get_unanalysed_items(limit=60)
    if not items:
        return 0

    count = 0
    for i in range(0, len(items), _BATCH_SIZE):
        batch = items[i:i + _BATCH_SIZE]
        classify_news_batch(batch)
        count += len(batch)

    print(f"[surveillance] Classified {count} news items")
    return count


def generate_report(min_items: int = 5) -> SurveillanceReport | None:
    """Generate a market intelligence briefing from recent relevant news."""
    recent = get_recent_news(limit=30, min_relevance=Relevance.MEDIUM)
    if len(recent) < min_items:
        print(f"[surveillance] Only {len(recent)} relevant items — need {min_items} for a report")
        return None

    news_text = "\n".join(
        f"- [{item.sentiment.value.upper()}] {item.title}\n  Summary: {item.summary or '(no summary)'}\n  Source: {item.source} | {item.published_at.strftime('%d %b %Y') if item.published_at else 'n/d'}"
        for item in recent[:25]
    )

    prompt = f"""You are a market intelligence analyst for Vantyx Pty Ltd.

{_vantyx_context()}

Produce a market intelligence briefing based ONLY on the following verified news items fetched from real RSS feeds.

## Verified News Items

{news_text}

## Briefing Requirements

Write a briefing covering:
1. Executive summary (2-3 paragraphs on the key market developments)
2. Opportunities Vantyx should act on
3. Threats or risks to be aware of
4. Key market trends to monitor
5. Specific action items for Sam

CRITICAL RULES:
- Every claim, statistic, and named event in your briefing MUST be traceable to one of the news items listed above.
- Do NOT invent price figures, company names, country events, or market data not present in the provided items.
- Do NOT add sources, URLs, or references not present in the items above.
- If the news items don't support a strong conclusion, say so rather than speculating.

Respond in this EXACT JSON format — no text outside the JSON:

{{
  "executive_summary": "2-3 paragraph briefing on the market...",
  "opportunities": [
    "Specific opportunity #1 with detail on why and how to act",
    "Opportunity #2"
  ],
  "threats": [
    "Specific threat #1 with context",
    "Threat #2"
  ],
  "key_trends": [
    "Trend #1 to monitor",
    "Trend #2"
  ],
  "action_items": [
    "Sam should: [specific action] by [timeframe]",
    "Action #2"
  ]
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
        raise ValueError(f"Non-JSON from Claude: {raw[:200]}")

    data = json.loads(match.group())
    report = save_report(SurveillanceReport(
        items_analysed=len(recent),
        executive_summary=data["executive_summary"],
        opportunities=data.get("opportunities", []),
        threats=data.get("threats", []),
        key_trends=data.get("key_trends", []),
        action_items=data.get("action_items", []),
    ))

    # Auto-generate high-priority alerts from threats
    for threat in data.get("threats", [])[:3]:
        save_alert(MarketAlert(
            alert_type="market_threat",
            headline=threat[:120],
            detail=threat,
            sentiment=Sentiment.THREAT,
        ))

    print(f"[surveillance] Report generated (#{report.id}, {len(recent)} items)")
    return report


def run_full_scan() -> dict:
    """Full pipeline: fetch feeds → classify → generate report."""
    from .fetcher import fetch_all_feeds
    new_items = fetch_all_feeds()
    classified = analyse_unanalysed()
    report = generate_report()
    return {
        "new_items_fetched": len(new_items),
        "items_classified": classified,
        "report_generated": report is not None,
        "report_id": report.id if report else None,
    }
