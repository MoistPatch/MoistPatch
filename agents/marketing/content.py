"""Claude-powered content generation for Vantyx marketing."""
from __future__ import annotations

import os

import anthropic

from .models import ContentRequest, GeneratedContent, Platform

_CLIENT: anthropic.Anthropic | None = None

PLATFORM_LIMITS = {
    Platform.TWITTER: 280,
    Platform.FACEBOOK: 2000,
    Platform.INSTAGRAM: 2200,
    Platform.LINKEDIN: 3000,
    Platform.GOOGLE_ADS: 90,
}

VANTYX_CONTEXT = """
Vantyx Pty Ltd (ABN 84 544 119 830) is an Australian-based International Commodity Trader
and Importer/Exporter specialising in agricultural fertiliser products of all types.
Based in Melbourne, Victoria. Contact: sam@vantyx.com.au | 0431 367 255
Website: https://vantyx.com.au

Product range includes: Urea (46% N), DAP (18-46-0), MAP (12-61-0), MOP (60% K₂O),
Sulphate of Potash, Granular Superphosphate, Triple Superphosphate, Calcium Ammonium Nitrate,
Ammonium Sulphate, Sulphur Bentonite, Zinc Sulphate, Magnesium Sulphate, and blended NPK.

Key value propositions:
- Global sourcing from 6 major agricultural supply regions
- Competitive pricing with direct manufacturer relationships
- Australian market expertise + international logistics
- LOI-based stock allocation process
- Supply the World
"""


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


def generate_post(req: ContentRequest) -> GeneratedContent:
    """Generate a social media post using Claude, informed by learned strategy."""
    from .insights import get_strategy_context

    char_limit = req.max_chars or PLATFORM_LIMITS.get(req.platform, 2000)
    cta = "Submit an LOI at vantyx.com.au to secure allocation." if req.include_cta else ""
    strategy_block = get_strategy_context()

    prompt = f"""You are a professional agricultural commodities marketing specialist for Vantyx Pty Ltd.

Company context:
{VANTYX_CONTEXT}
{strategy_block}

Write a {req.tone.value} {req.platform.value} post about: {req.product}
{"Campaign context: " + req.campaign_context if req.campaign_context else ""}

Requirements:
- Maximum {char_limit} characters for the post text (STRICT limit)
- Tone: {req.tone.value}
- {"Include this CTA: " + cta if req.include_cta else "No CTA needed"}
- Include 3-6 relevant hashtags (prioritise high-performing ones from strategy above; avoid listed underperformers)
- Suggest an image prompt for DALL-E or Stable Diffusion
- For Google Ads: also write a 30-char headline and 90-char description

Respond in this exact JSON format:
{{
  "post_text": "...",
  "hashtags": ["#tag1", "#tag2"],
  "image_prompt": "...",
  "ad_headline": "..." or null,
  "ad_description": "..." or null
}}"""

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    import re

    raw = next(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned non-JSON: {raw[:200]}")

    data = json.loads(match.group())
    return GeneratedContent(**data)


def generate_campaign_posts(
    product: str,
    platforms: list[Platform],
    campaign_context: str,
    tone_variation: bool = True,
) -> dict[Platform, GeneratedContent]:
    """Generate platform-specific posts for a campaign."""
    from .models import PostTone

    tones = [PostTone.PROFESSIONAL, PostTone.INFORMATIVE, PostTone.PROMOTIONAL, PostTone.ENGAGING]
    results = {}

    for i, platform in enumerate(platforms):
        tone = tones[i % len(tones)] if tone_variation else PostTone.PROFESSIONAL
        req = ContentRequest(
            product=product,
            tone=tone,
            platform=platform,
            include_cta=True,
            campaign_context=campaign_context,
        )
        results[platform] = generate_post(req)

    return results


def generate_lead_response(lead_name: str, product: str, company: str) -> str:
    """Generate a personalised follow-up email body for a lead."""
    prompt = f"""Write a brief, professional follow-up email body from Vantyx Pty Ltd
to {lead_name} at {company} who enquired about {product}.

Company context:
{VANTYX_CONTEXT}

Keep it under 150 words. Warm but professional. Mention the LOI process.
Do not include subject line or salutation — just the body paragraphs."""

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    return next(b.text for b in response.content if b.type == "text")
