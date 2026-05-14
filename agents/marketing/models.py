"""Pydantic models for the Vantyx marketing agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    GOOGLE_ADS = "google_ads"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class PostTone(str, Enum):
    PROFESSIONAL = "professional"
    INFORMATIVE = "informative"
    PROMOTIONAL = "promotional"
    ENGAGING = "engaging"


class SocialPost(BaseModel):
    id: Optional[int] = None
    platform: Platform
    content: str
    hashtags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    image_path: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    status: PostStatus = PostStatus.DRAFT
    platform_post_id: Optional[str] = None
    campaign_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Campaign(BaseModel):
    id: Optional[int] = None
    name: str
    description: str
    product: str
    target_audience: str
    platforms: list[Platform]
    budget_aud: Optional[float] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    status: CampaignStatus = CampaignStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Lead(BaseModel):
    id: Optional[int] = None
    source: str  # platform or "direct"
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    product_interest: Optional[str] = None
    quantity_mt: Optional[float] = None
    message: Optional[str] = None
    forwarded: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ContentRequest(BaseModel):
    product: str
    tone: PostTone = PostTone.PROFESSIONAL
    platform: Platform
    include_cta: bool = True
    campaign_context: Optional[str] = None
    max_chars: Optional[int] = None


class GeneratedContent(BaseModel):
    post_text: str
    hashtags: list[str]
    image_prompt: Optional[str] = None
    ad_headline: Optional[str] = None
    ad_description: Optional[str] = None
