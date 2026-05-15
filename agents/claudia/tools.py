"""Tool definitions and dispatchers for CLAUDIA.

Each tool routes to one of the three specialised agents. All handlers return a
STRING (success message or error). They never raise — errors are caught and
returned so Claude can recover gracefully.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

# ── Tool schema definitions for the Anthropic SDK ─────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_status",
        "description": "Get a snapshot of all Vantyx agents — marketing post counts, leads, pricing alerts, surveillance state. Use when Sam asks 'how are things?' or for a summary.",
        "input_schema": {"type": "object", "properties": {}},
    },

    # ── Marketing ─────────────────────────────────────────────────────
    {
        "name": "draft_post",
        "description": "Generate a social media post using Claude. Optionally schedule it. Returns the drafted content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product or topic, e.g. 'Urea 46% N' or 'DAP 18-46-0'"},
                "platform": {"type": "string", "enum": ["facebook", "instagram", "twitter", "linkedin"]},
                "tone": {"type": "string", "enum": ["professional", "informative", "promotional", "engaging"], "description": "Default: professional"},
                "schedule_hours": {"type": "integer", "description": "Hours from now to schedule. 0 = draft only. Default 0."},
            },
            "required": ["product", "platform"],
        },
    },
    {
        "name": "list_posts",
        "description": "List recent marketing posts with status and content preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {"type": "string", "enum": ["all", "draft", "scheduled", "published", "failed"]},
                "limit": {"type": "integer", "description": "Default 10"},
            },
        },
    },
    {
        "name": "launch_campaign",
        "description": "Launch a multi-channel marketing campaign with budget allocation. Generates and schedules posts across the specified platforms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "product": {"type": "string"},
                "audience": {"type": "string", "description": "Target audience description"},
                "platforms": {"type": "array", "items": {"type": "string", "enum": ["facebook", "instagram", "twitter", "linkedin", "google_ads"]}},
                "budget_aud": {"type": "number"},
                "duration_days": {"type": "integer", "description": "Default 30"},
            },
            "required": ["name", "product", "platforms", "budget_aud"],
        },
    },
    {
        "name": "list_leads",
        "description": "List recent leads captured.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Default 10"}},
        },
    },
    {
        "name": "record_lead",
        "description": "Record a new lead and immediately forward to sam@vantyx.com.au with auto-generated personalised reply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "company": {"type": "string"},
                "product_interest": {"type": "string"},
                "quantity_mt": {"type": "number"},
                "message": {"type": "string"},
                "source": {"type": "string", "description": "How they found us. Default 'claudia'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "flush_leads",
        "description": "Forward all pending un-forwarded leads to sam@vantyx.com.au.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_marketing_strategy",
        "description": "Get the current learned marketing strategy — best platform, tone, hashtags — derived from performance data.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyse_marketing",
        "description": "Run Claude analysis on marketing post performance to update the learned strategy. Slow (~30s).",
        "input_schema": {
            "type": "object",
            "properties": {"force": {"type": "boolean", "description": "Analyse even with few posts. Default false."}},
        },
    },

    # ── Pricing ───────────────────────────────────────────────────────
    {
        "name": "get_prices",
        "description": "Get current fertiliser commodity prices for all tracked products (Urea, DAP, MAP, MOP, etc.).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "refresh_prices",
        "description": "Fetch fresh prices from IndexMundi and FRED. Slow (~10s).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_manual_price",
        "description": "Manually record a price (e.g. from a supplier quote you received).",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "enum": ["urea", "dap", "map", "mop", "phosphate_rock", "ammonia", "ammonium_sulphate", "tsp"]},
                "price_usd_mt": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["product", "price_usd_mt"],
        },
    },
    {
        "name": "run_price_analysis",
        "description": "Run Claude market analysis on pricing data — identifies buying opportunities, risks, recommendations. Slow (~20s).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_price_alerts",
        "description": "Get current pricing alerts (significant moves: spikes, drops, opportunities).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_pricing_analysis",
        "description": "Get the most recent pricing analysis (without running a new one).",
        "input_schema": {"type": "object", "properties": {}},
    },

    # ── Surveillance ──────────────────────────────────────────────────
    {
        "name": "run_market_scan",
        "description": "Run full market intelligence pipeline: fetch RSS news → classify with Claude → generate briefing. Slow (~60s).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_news",
        "description": "Get recent market news items relevant to Vantyx (already classified).",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Default 10"}},
        },
    },
    {
        "name": "get_surveillance_alerts",
        "description": "Get current market surveillance alerts (threats and opportunities flagged from news).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_intelligence_report",
        "description": "Get the latest market intelligence briefing — executive summary, opportunities, threats, action items.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Tool dispatchers ──────────────────────────────────────────────────────

def _marketing():
    from agents.marketing import MarketingAgent
    return MarketingAgent()


def _pricing():
    from agents.pricing import PricingAgent
    return PricingAgent()


def _surveillance():
    from agents.surveillance import SurveillanceAgent
    return SurveillanceAgent()


def _t_get_status(args: dict) -> str:
    m = _marketing().status()
    p = _pricing().status()
    s = _surveillance().status()
    return (
        "## Vantyx agent status\n\n"
        f"**Marketing** — {m.get('posts_scheduled', 0)} scheduled / {m.get('posts_published', 0)} published. "
        f"Leads: {m.get('leads_total', 0)} ({m.get('leads_unforwarded', 0)} pending). "
        f"Insights: {m.get('insights_generated', 0)}.\n\n"
        f"**Pricing** — {p.get('products_tracked', 0)} products tracked. "
        f"{p.get('unacknowledged_alerts', 0)} active alerts. "
        f"Outlook: {p.get('market_outlook', 'unknown')}.\n\n"
        f"**Surveillance** — {s.get('unacknowledged_alerts', 0)} alerts. "
        f"Last scan: {s.get('last_scan', 'never')}."
    )


def _t_draft_post(args: dict) -> str:
    from agents.marketing.models import Platform, PostTone
    product = args.get("product", "")
    platform = Platform(args.get("platform", "linkedin"))
    tone = PostTone(args.get("tone", "professional"))
    hours = int(args.get("schedule_hours", 0))
    schedule_at = datetime.utcnow() + timedelta(hours=hours) if hours else None
    post = _marketing().draft_post(product=product, platform=platform, tone=tone, schedule_at=schedule_at)
    scheduled = f" Scheduled for {post.scheduled_at.strftime('%d %b %H:%M UTC')}." if post.scheduled_at else " Saved as draft."
    return f"Post #{post.id} ({platform.value}) created.{scheduled}\n\n{post.content}\n\n{' '.join(post.hashtags)}"


def _t_list_posts(args: dict) -> str:
    from agents.marketing.storage import get_posts
    from agents.marketing.models import PostStatus
    filt = args.get("status_filter", "all")
    limit = int(args.get("limit", 10))
    status = PostStatus(filt) if filt != "all" else None
    posts = get_posts(status=status, limit=limit)
    if not posts:
        return "No posts found."
    lines = ["| # | Platform | Status | Scheduled | Preview |", "|---|---|---|---|---|"]
    for p in posts:
        ts = p.scheduled_at or p.published_at or p.created_at
        lines.append(f"| {p.id} | {p.platform.value} | {p.status.value} | {ts.strftime('%d %b %H:%M')} | {p.content[:50]}… |")
    return "\n".join(lines)


def _t_launch_campaign(args: dict) -> str:
    from agents.marketing.models import Platform
    platforms = [Platform(p) for p in args.get("platforms", [])]
    campaign = _marketing().run_campaign(
        name=args["name"],
        product=args["product"],
        target_audience=args.get("audience", "agricultural buyers globally"),
        platforms=platforms,
        budget_aud=float(args["budget_aud"]),
        duration_days=int(args.get("duration_days", 30)),
    )
    return f"Campaign #{campaign.id} '{campaign.name}' launched. Status: {campaign.status.value}. Budget AUD ${campaign.budget_aud:,.0f} over {(campaign.end_date - campaign.start_date).days if campaign.end_date else '?'} days."


def _t_list_leads(args: dict) -> str:
    from agents.marketing.storage import get_leads
    limit = int(args.get("limit", 10))
    leads = get_leads(limit=limit)
    if not leads:
        return "No leads yet."
    lines = ["| Name | Company | Product | Vol (MT) | Source | Forwarded |", "|---|---|---|---|---|---|"]
    for l in leads:
        lines.append(f"| {l.name or '—'} | {l.company or '—'} | {l.product_interest or '—'} | {l.quantity_mt or '—'} | {l.source} | {'✓' if l.forwarded else '✗'} |")
    return "\n".join(lines)


def _t_record_lead(args: dict) -> str:
    lead = _marketing().record_lead(
        source=args.get("source", "claudia"),
        name=args.get("name"),
        email=args.get("email"),
        company=args.get("company"),
        product_interest=args.get("product_interest"),
        quantity_mt=args.get("quantity_mt"),
        message=args.get("message"),
    )
    return f"Lead #{lead.id} captured. Forwarded to sam@vantyx.com.au: {'yes' if lead.forwarded else 'pending'}."


def _t_flush_leads(args: dict) -> str:
    n = _marketing().flush_leads()
    return f"Forwarded {n} pending lead(s)."


def _t_get_marketing_strategy(args: dict) -> str:
    return _marketing().strategy()


def _t_analyse_marketing(args: dict) -> str:
    insight = _marketing().analyse(force=bool(args.get("force", False)))
    if not insight:
        return "Not enough data — try again after more posts are published, or pass force=true."
    rec_text = "\n".join(f"- {r}" for r in insight.recommendations[:5])
    return f"Strategy insight #{insight.id} generated ({insight.posts_analysed} posts).\n\n**Top recommendations:**\n{rec_text}"


# ── Pricing ───────────────────────────────────────────────────────────────

def _t_get_prices(args: dict) -> str:
    prices = _pricing().prices()
    if not prices:
        return "No price data yet. Call refresh_prices first."
    lines = ["| Product | USD/MT | Source | Date |", "|---|---|---|---|"]
    for k, p in sorted(prices.items()):
        lines.append(f"| {p['label']} | ${p['price_usd_mt']:,.0f} | {p['source']} | {p['date']} |")
    return "\n".join(lines)


def _t_refresh_prices(args: dict) -> str:
    r = _pricing().refresh()
    return f"Refreshed prices: {r['prices_fetched']} updates, {r['alerts_generated']} new alerts generated."


def _t_add_manual_price(args: dict) -> str:
    _pricing().add_price(args["product"], float(args["price_usd_mt"]), args.get("notes", ""))
    return f"Recorded {args['product']} at ${args['price_usd_mt']:.0f}/MT."


def _t_run_price_analysis(args: dict) -> str:
    a = _pricing().analyse(force=True)
    if not a:
        return "No pricing data to analyse. Run refresh_prices first."
    opp = "\n".join(f"- {o}" for o in a.buying_opportunities[:3])
    risks = "\n".join(f"- {r}" for r in a.risk_warnings[:3])
    return (
        f"## Pricing analysis — outlook: **{a.outlook}**\n\n"
        f"{a.market_summary}\n\n"
        f"**Buying opportunities:**\n{opp or '(none flagged)'}\n\n"
        f"**Risk warnings:**\n{risks or '(none)'}"
    )


def _t_get_price_alerts(args: dict) -> str:
    alerts = _pricing().alerts(unacknowledged_only=False)[:10]
    if not alerts:
        return "No pricing alerts."
    lines = ["| Severity | Product | Change | Message |", "|---|---|---|---|"]
    for a in alerts:
        change = f"{a.change_pct:+.1f}%" if a.change_pct else "—"
        lines.append(f"| {a.severity.value} | {a.product} | {change} | {a.message[:70]} |")
    return "\n".join(lines)


def _t_get_pricing_analysis(args: dict) -> str:
    a = _pricing().analysis()
    if not a:
        return "No analysis yet. Call run_price_analysis."
    return (
        f"Latest analysis — outlook: **{a.outlook}** (generated {a.generated_at.strftime('%d %b %H:%M UTC')})\n\n"
        f"{a.market_summary}"
    )


# ── Surveillance ──────────────────────────────────────────────────────────

def _t_run_market_scan(args: dict) -> str:
    r = _surveillance().scan()
    return f"Market scan complete. New items: {r['new_items_fetched']}. Classified: {r['items_classified']}. Report {'generated' if r['report_generated'] else 'not generated (insufficient data)'}."


def _t_get_news(args: dict) -> str:
    items = _surveillance().news(limit=int(args.get("limit", 10)))
    if not items:
        return "No relevant news yet. Run a market scan."
    lines = []
    for i in items:
        date = i.published_at.strftime('%d %b') if i.published_at else 'n/d'
        lines.append(f"- [{i.sentiment.value.upper()}] **{i.title}** ({date}, {i.source})\n  {(i.summary or '')[:140]}")
    return "\n".join(lines)


def _t_get_surveillance_alerts(args: dict) -> str:
    alerts = _surveillance().alerts(unacknowledged_only=False)[:10]
    if not alerts:
        return "No surveillance alerts."
    lines = [f"- [{a.sentiment.value.upper()}] {a.headline}" for a in alerts]
    return "\n".join(lines)


def _t_get_intelligence_report(args: dict) -> str:
    r = _surveillance().report()
    if not r:
        return "No intelligence report yet. Run a market scan."
    opp = "\n".join(f"- {o}" for o in r.opportunities[:4])
    threats = "\n".join(f"- {t}" for t in r.threats[:4])
    actions = "\n".join(f"- {a}" for a in r.action_items[:4])
    return (
        f"## Intelligence briefing #{r.id} ({r.generated_at.strftime('%d %b %H:%M UTC')}, {r.items_analysed} items)\n\n"
        f"{r.executive_summary}\n\n"
        f"**Opportunities:**\n{opp or '(none)'}\n\n"
        f"**Threats:**\n{threats or '(none)'}\n\n"
        f"**Action items:**\n{actions or '(none)'}"
    )


_HANDLERS = {
    "get_status": _t_get_status,
    "draft_post": _t_draft_post,
    "list_posts": _t_list_posts,
    "launch_campaign": _t_launch_campaign,
    "list_leads": _t_list_leads,
    "record_lead": _t_record_lead,
    "flush_leads": _t_flush_leads,
    "get_marketing_strategy": _t_get_marketing_strategy,
    "analyse_marketing": _t_analyse_marketing,
    "get_prices": _t_get_prices,
    "refresh_prices": _t_refresh_prices,
    "add_manual_price": _t_add_manual_price,
    "run_price_analysis": _t_run_price_analysis,
    "get_price_alerts": _t_get_price_alerts,
    "get_pricing_analysis": _t_get_pricing_analysis,
    "run_market_scan": _t_run_market_scan,
    "get_news": _t_get_news,
    "get_surveillance_alerts": _t_get_surveillance_alerts,
    "get_intelligence_report": _t_get_intelligence_report,
}


def execute_tool(name: str, args: dict) -> str:
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool '{name}'."
    try:
        return handler(args or {})
    except Exception as exc:
        return f"Error executing {name}: {type(exc).__name__}: {exc}"
