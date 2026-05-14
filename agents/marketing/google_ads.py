"""Google Ads campaign management for Vantyx."""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

# Google Ads API v16
_ADS_BASE = "https://googleads.googleapis.com/v16"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GOOGLE_ADS_ACCESS_TOKEN']}",
        "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "login-customer-id": os.environ["GOOGLE_ADS_MANAGER_ACCOUNT_ID"],
    }


def _customer_id() -> str:
    return os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")


def create_search_campaign(
    name: str,
    daily_budget_aud: float,
    start_date: str,
    end_date: Optional[str] = None,
) -> str:
    """Create a Search campaign. Returns the campaign resource name."""
    customer = _customer_id()

    # 1. Create shared budget
    budget_ops = [{
        "campaignBudgetOperation": {
            "create": {
                "name": f"{name} Budget",
                "amountMicros": int(daily_budget_aud * 1_000_000),
                "deliveryMethod": "STANDARD",
            }
        }
    }]
    r = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": budget_ops},
        timeout=30,
    )
    r.raise_for_status()
    budget_name = r.json()["mutateOperationResponses"][0]["campaignBudgetResult"]["resourceName"]

    # 2. Create campaign
    campaign_body: dict[str, Any] = {
        "name": name,
        "advertisingChannelType": "SEARCH",
        "status": "PAUSED",  # start paused; activate when ready
        "campaignBudget": budget_name,
        "startDate": start_date,
        "manualCpc": {},
    }
    if end_date:
        campaign_body["endDate"] = end_date

    ops = [{"campaignOperation": {"create": campaign_body}}]
    r2 = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": ops},
        timeout=30,
    )
    r2.raise_for_status()
    return r2.json()["mutateOperationResponses"][0]["campaignResult"]["resourceName"]


def add_responsive_search_ad(
    campaign_resource: str,
    ad_group_name: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str = "https://vantyx.com.au",
) -> str:
    """Add a responsive search ad to a new ad group under campaign_resource."""
    customer = _customer_id()

    # Create ad group
    ag_ops = [{
        "adGroupOperation": {
            "create": {
                "name": ad_group_name,
                "campaign": campaign_resource,
                "status": "ENABLED",
                "type": "SEARCH_STANDARD",
            }
        }
    }]
    r = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": ag_ops},
        timeout=30,
    )
    r.raise_for_status()
    ag_name = r.json()["mutateOperationResponses"][0]["adGroupResult"]["resourceName"]

    # Create RSA
    rsa_ops = [{
        "adGroupAdOperation": {
            "create": {
                "adGroup": ag_name,
                "status": "ENABLED",
                "ad": {
                    "responsiveSearchAd": {
                        "headlines": [{"text": h[:30]} for h in headlines[:15]],
                        "descriptions": [{"text": d[:90]} for d in descriptions[:4]],
                    },
                    "finalUrls": [final_url],
                },
            }
        }
    }]
    r2 = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": rsa_ops},
        timeout=30,
    )
    r2.raise_for_status()
    return r2.json()["mutateOperationResponses"][0]["adGroupAdResult"]["resourceName"]


def add_keywords(campaign_resource: str, ad_group_resource: str, keywords: list[str]) -> None:
    """Add broad-match keywords to an ad group."""
    customer = _customer_id()
    ops = [
        {
            "adGroupCriterionOperation": {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "ENABLED",
                    "keyword": {"text": kw, "matchType": "BROAD"},
                }
            }
        }
        for kw in keywords
    ]
    r = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": ops},
        timeout=30,
    )
    r.raise_for_status()


def enable_campaign(campaign_resource: str) -> None:
    """Set a campaign to ENABLED."""
    customer = _customer_id()
    ops = [{
        "campaignOperation": {
            "update": {"resourceName": campaign_resource, "status": "ENABLED"},
            "updateMask": "status",
        }
    }]
    r = httpx.post(
        f"{_ADS_BASE}/customers/{customer}/googleAds:mutate",
        headers=_headers(),
        json={"mutateOperations": ops},
        timeout=30,
    )
    r.raise_for_status()


FERTILISER_KEYWORDS = [
    "buy urea fertiliser",
    "DAP fertiliser supplier",
    "MAP fertiliser bulk",
    "MOP potash supplier Australia",
    "agricultural fertiliser importer",
    "fertiliser commodity trader",
    "bulk fertiliser Australia",
    "NPK fertiliser wholesale",
    "fertiliser stock allocation",
    "vantyx fertiliser",
]
