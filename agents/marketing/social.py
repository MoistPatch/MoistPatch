"""Social media posting — Meta, Twitter/X, LinkedIn."""
from __future__ import annotations

import os
from typing import Optional

import httpx

from .models import Platform, SocialPost


def post_to_facebook(post: SocialPost) -> str:
    """Post to a Facebook Page. Returns the platform post ID."""
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    text = post.content
    if post.hashtags:
        text += "\n\n" + " ".join(post.hashtags)

    if post.image_url:
        r = httpx.post(
            f"https://graph.facebook.com/v19.0/{page_id}/photos",
            params={"access_token": token},
            json={"url": post.image_url, "caption": text},
            timeout=30,
        )
    else:
        r = httpx.post(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            params={"access_token": token},
            json={"message": text},
            timeout=30,
        )

    r.raise_for_status()
    data = r.json()
    return data.get("id") or data.get("post_id", "")


def post_to_instagram(post: SocialPost) -> str:
    """Post to an Instagram Business account. Requires an image."""
    account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    if not post.image_url:
        raise ValueError("Instagram posts require an image_url")

    caption = post.content
    if post.hashtags:
        caption += "\n\n" + " ".join(post.hashtags)

    # Step 1: create media container
    r = httpx.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media",
        params={"access_token": token},
        json={"image_url": post.image_url, "caption": caption},
        timeout=30,
    )
    r.raise_for_status()
    creation_id = r.json()["id"]

    # Step 2: publish
    r2 = httpx.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media_publish",
        params={"access_token": token},
        json={"creation_id": creation_id},
        timeout=30,
    )
    r2.raise_for_status()
    return r2.json()["id"]


def post_to_twitter(post: SocialPost) -> str:
    """Post a tweet using Twitter/X API v2 with OAuth 2.0 Bearer + user auth."""
    import base64
    import hashlib
    import hmac
    import time
    import urllib.parse

    consumer_key = os.environ["TWITTER_API_KEY"]
    consumer_secret = os.environ["TWITTER_API_SECRET"]
    access_token = os.environ["TWITTER_ACCESS_TOKEN"]
    access_secret = os.environ["TWITTER_ACCESS_TOKEN_SECRET"]

    text = post.content
    if post.hashtags and len(text) + len(" ".join(post.hashtags)) + 2 <= 280:
        text += "\n" + " ".join(post.hashtags)
    text = text[:280]

    url = "https://api.twitter.com/2/tweets"

    # OAuth 1.0a signature
    timestamp = str(int(time.time()))
    nonce = base64.b64encode(os.urandom(32)).decode().strip("=")

    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    base_string = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(
            "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}"
                     for k, v in sorted(params.items())),
            safe="",
        ),
    ])

    signing_key = f"{urllib.parse.quote(consumer_secret)}&{urllib.parse.quote(access_secret)}"
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    params["oauth_signature"] = sig

    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k)}="{urllib.parse.quote(v)}"'
        for k, v in sorted(params.items())
    )

    r = httpx.post(
        url,
        headers={"Authorization": auth_header, "Content-Type": "application/json"},
        json={"text": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def post_to_linkedin(post: SocialPost) -> str:
    """Post to a LinkedIn Company Page."""
    org_id = os.environ["LINKEDIN_ORG_ID"]
    token = os.environ["LINKEDIN_ACCESS_TOKEN"]

    text = post.content
    if post.hashtags:
        text += "\n\n" + " ".join(post.hashtags)

    body: dict = {
        "author": f"urn:li:organization:{org_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    if post.image_url:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "IMAGE"
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
            {
                "status": "READY",
                "originalUrl": post.image_url,
                "description": {"text": "Vantyx fertiliser product"},
                "title": {"text": "Vantyx"},
            }
        ]

    r = httpx.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.headers.get("X-RestLi-Id", "")


def publish_post(post: SocialPost) -> str:
    """Dispatch a post to the correct platform and return the platform post ID."""
    handlers = {
        Platform.FACEBOOK: post_to_facebook,
        Platform.INSTAGRAM: post_to_instagram,
        Platform.TWITTER: post_to_twitter,
        Platform.LINKEDIN: post_to_linkedin,
    }
    handler = handlers.get(post.platform)
    if handler is None:
        raise ValueError(f"No social handler for platform: {post.platform}")
    return handler(post)
