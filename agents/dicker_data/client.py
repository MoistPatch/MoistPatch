"""
Dicker Data Reseller API HTTP client.

Credentials via environment variables:
  DICKER_DATA_API_KEY  — API key from the Dicker Data reseller portal
  DICKER_DATA_USERNAME — reseller account username (fallback / future auth)
  DICKER_DATA_PASSWORD — reseller account password (fallback / future auth)

Base URL : https://api.dickerdata.com.au/v1
Auth     : Bearer token in the Authorization header
Responses: JSON
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class DickerDataAPIError(Exception):
    """Raised when the Dicker Data API returns an HTTP error (status >= 400)."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Dicker Data API error {status}: {message}")


class DickerDataClient:
    """
    Dicker Data Reseller API client.

    Credentials set via env vars:
      DICKER_DATA_API_KEY  — API key from reseller portal
      DICKER_DATA_USERNAME — reseller account username (fallback auth)
      DICKER_DATA_PASSWORD — reseller account password (fallback auth)

    Base URL: https://api.dickerdata.com.au/v1
    Auth: Bearer token in Authorization header.
    All responses are JSON.
    """

    BASE_URL = "https://api.dickerdata.com.au/v1"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("DICKER_DATA_API_KEY", "")
        # Stored for any future username/password-based auth flows.
        self._username = os.environ.get("DICKER_DATA_USERNAME", "")
        self._password = os.environ.get("DICKER_DATA_PASSWORD", "")

    # ── Internal request helper ────────────────────────────────────────────

    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Any:
        """
        Make an authenticated request to the Dicker Data API.

        Raises:
            DickerDataAPIError if the API responds with HTTP >= 400.
            RuntimeError if DICKER_DATA_API_KEY is not configured.
        """
        if not self._api_key:
            raise RuntimeError(
                "DICKER_DATA_API_KEY not set — get your API key from the "
                "Dicker Data reseller portal (https://www.dickerdata.com.au/reseller)"
            )

        url = f"{self.BASE_URL}{path}"
        body: Optional[bytes] = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "TensorWorks-DickerDataAgent/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            raise DickerDataAPIError(exc.code, detail) from exc

    # ── Public API methods ─────────────────────────────────────────────────

    def search_products(self, query: str, page: int = 1, limit: int = 20) -> List[dict]:
        """Search the Dicker Data product catalogue.

        GET /products/search?q=...&page=...&limit=...
        Returns a list of product dicts.
        """
        qs = urllib.parse.urlencode({"q": query, "page": page, "limit": limit})
        result = self._request("GET", f"/products/search?{qs}")
        # API may return {"products": [...]} or a bare list.
        if isinstance(result, list):
            return result
        return result.get("products", result.get("data", []))

    def get_product(self, sku: str) -> dict:
        """Fetch a single product by SKU.

        GET /products/{sku}
        """
        return self._request("GET", f"/products/{urllib.parse.quote(sku, safe='')}")

    def get_stock(self, sku: str) -> dict:
        """Fetch real-time stock level for a SKU.

        GET /products/{sku}/stock
        """
        return self._request("GET", f"/products/{urllib.parse.quote(sku, safe='')}/stock")

    def get_pricing(self, sku: str) -> dict:
        """Fetch reseller pricing for a SKU.

        GET /products/{sku}/pricing
        """
        return self._request("GET", f"/products/{urllib.parse.quote(sku, safe='')}/pricing")

    def get_bulk_stock(self, skus: List[str]) -> List[dict]:
        """Fetch stock levels for multiple SKUs in one call.

        POST /products/stock/bulk  {"skus": [...]}
        Returns a list of stock dicts.
        """
        result = self._request("POST", "/products/stock/bulk", data={"skus": skus})
        if isinstance(result, list):
            return result
        return result.get("stock", result.get("data", []))

    def place_order(
        self,
        reference: str,
        lines: List[dict],
        delivery_address: dict,
    ) -> dict:
        """Submit a purchase order to Dicker Data.

        POST /orders
        Body: {"reference": ..., "lines": [...], "delivery_address": {...}}
        """
        return self._request(
            "POST",
            "/orders",
            data={
                "reference": reference,
                "lines": lines,
                "delivery_address": delivery_address,
            },
        )

    def get_order(self, order_id: str) -> dict:
        """Fetch an existing order by ID.

        GET /orders/{order_id}
        """
        return self._request("GET", f"/orders/{urllib.parse.quote(str(order_id), safe='')}")

    def get_categories(self) -> List[dict]:
        """Fetch the full product category tree.

        GET /categories
        """
        result = self._request("GET", "/categories")
        if isinstance(result, list):
            return result
        return result.get("categories", result.get("data", []))
