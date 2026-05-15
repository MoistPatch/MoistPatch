"""Fetches live exchange rates from open.er-api.com (free, no API key)."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime

_ER_URL = "https://open.er-api.com/v6/latest/USD"


def fetch_live_rates() -> dict:
    """Return live USD-based rates for 160+ currencies.

    Response shape:
        {
            "base": "USD",
            "fetched_at": "<iso>",
            "rates": {"EUR": 0.92, "JPY": 149.5, ...}
        }
    """
    req = urllib.request.Request(
        _ER_URL,
        headers={"User-Agent": "VantyxDashboard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    if data.get("result") != "success":
        raise RuntimeError(f"open.er-api.com returned: {data.get('result')}")

    return {
        "base": data.get("base_code", "USD"),
        "fetched_at": datetime.utcnow().isoformat(),
        "next_update_utc": data.get("time_next_update_utc", ""),
        "rates": data["rates"],
    }
