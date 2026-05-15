"""
Dicker Data agent — high-level orchestration layer.

Wraps DickerDataClient with local SQLite caching, SKU tracking,
and graceful error handling so the dashboard never crashes on API errors.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .client import DickerDataAPIError, DickerDataClient
from .models import Order, OrderLine, Product, StockAlert
from .storage import (
    add_tracked_sku,
    get_all_products,
    get_orders,
    get_product,
    get_stock_alerts,
    get_tracked_skus,
    init_db,
    remove_tracked_sku,
    save_order,
    save_stock_alert,
    upsert_product,
)

log = logging.getLogger("vantyx.dicker_data")


def _product_to_dict(p: Product) -> dict:
    return {
        "sku": p.sku,
        "part_number": p.part_number,
        "description": p.description,
        "brand": p.brand,
        "category": p.category,
        "unit_price_aud": p.unit_price_aud,
        "cost_price_aud": p.cost_price_aud,
        "stock_qty": p.stock_qty,
        "stock_status": p.stock_status,
        "weight_kg": p.weight_kg,
        "image_url": p.image_url,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "reference": o.reference,
        "status": o.status,
        "total_aud": o.total_aud,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "tracking_number": o.tracking_number,
        "lines": [
            {
                "sku": ln.sku,
                "quantity": ln.quantity,
                "unit_price_aud": ln.unit_price_aud,
            }
            for ln in o.lines
        ],
    }


def _parse_product_from_api(data: dict) -> Product:
    """Map a Dicker Data API product dict to our Product model."""
    updated_raw = data.get("updated_at") or data.get("updatedAt")
    updated_at: Optional[datetime] = None
    if updated_raw:
        try:
            updated_at = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
        except ValueError:
            updated_at = datetime.utcnow()
    else:
        updated_at = datetime.utcnow()

    return Product(
        sku=str(data.get("sku") or data.get("id", "")),
        part_number=data.get("part_number") or data.get("partNumber"),
        description=data.get("description") or data.get("name"),
        brand=data.get("brand") or data.get("manufacturer"),
        category=data.get("category"),
        unit_price_aud=_to_float(data.get("unit_price_aud") or data.get("rrp") or data.get("price")),
        cost_price_aud=_to_float(data.get("cost_price_aud") or data.get("cost") or data.get("reseller_price")),
        stock_qty=_to_int(data.get("stock_qty") or data.get("stock") or data.get("quantity")),
        stock_status=data.get("stock_status") or data.get("availability"),
        weight_kg=_to_float(data.get("weight_kg") or data.get("weight")),
        image_url=data.get("image_url") or data.get("image"),
        updated_at=updated_at,
    )


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class DickerDataAgent:
    """High-level Dicker Data integration agent."""

    def __init__(self) -> None:
        init_db()
        self._client: Optional[DickerDataClient] = None  # lazy

    def _c(self) -> DickerDataClient:
        if not self._client:
            self._client = DickerDataClient(os.environ.get("DICKER_DATA_API_KEY", ""))
        return self._client

    # ── Catalogue search ───────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> List[dict]:
        """Search Dicker Data catalogue, cache results locally."""
        if not query:
            return []
        try:
            raw_products = self._c().search_products(query, limit=limit)
        except DickerDataAPIError as exc:
            log.warning("Dicker Data search failed: %s", exc)
            return [{"error": str(exc)}]
        except RuntimeError as exc:
            log.warning("Dicker Data client not configured: %s", exc)
            return [{"error": str(exc)}]

        results: List[dict] = []
        for raw in raw_products:
            try:
                product = _parse_product_from_api(raw)
                upsert_product(product)
                results.append(_product_to_dict(product))
            except Exception as exc:
                log.warning("Failed to parse/cache product: %s — %s", raw, exc)
                results.append(raw)  # return raw dict as fallback

        return results

    # ── SKU tracking ───────────────────────────────────────────────────────

    def track_sku(self, sku: str, label: str = "") -> dict:
        """Add a SKU to the tracking list and fetch initial stock/pricing data."""
        if not sku:
            return {"error": "sku is required"}
        add_tracked_sku(sku, label)
        # Fetch initial data right away; don't fail if API is not yet configured.
        try:
            raw = self._c().get_product(sku)
            product = _parse_product_from_api(raw)
            upsert_product(product)
            return {"ok": True, "sku": sku, "label": label, "product": _product_to_dict(product)}
        except DickerDataAPIError as exc:
            log.warning("Initial fetch for %s failed: %s", sku, exc)
            return {"ok": True, "sku": sku, "label": label, "warning": str(exc)}
        except RuntimeError as exc:
            log.warning("Dicker Data client not configured: %s", exc)
            return {"ok": True, "sku": sku, "label": label, "warning": str(exc)}

    def untrack_sku(self, sku: str) -> dict:
        """Remove a SKU from the tracking list."""
        if not sku:
            return {"error": "sku is required"}
        remove_tracked_sku(sku)
        return {"ok": True, "sku": sku}

    def get_tracked(self) -> List[dict]:
        """Return tracked SKUs with latest stock/price from local DB."""
        tracked = get_tracked_skus()
        results: List[dict] = []
        for t in tracked:
            entry: dict = {"sku": t["sku"], "label": t.get("label", ""), "added_at": t.get("added_at")}
            product = get_product(t["sku"])
            if product:
                entry.update(_product_to_dict(product))
            results.append(entry)
        return results

    # ── Bulk refresh ───────────────────────────────────────────────────────

    def refresh_tracked(self) -> dict:
        """Refresh stock + pricing for all tracked SKUs. Returns a summary."""
        tracked = get_tracked_skus()
        if not tracked:
            return {"ok": True, "refreshed": 0, "errors": 0, "message": "No SKUs are being tracked"}

        skus = [t["sku"] for t in tracked]
        refreshed = 0
        errors = 0
        low_stock: List[str] = []

        # Try bulk stock first; fall back to individual calls if API fails.
        try:
            bulk_stock = self._c().get_bulk_stock(skus)
            stock_map: Dict[str, dict] = {}
            for entry in bulk_stock:
                s = entry.get("sku") or entry.get("id", "")
                if s:
                    stock_map[str(s)] = entry
        except DickerDataAPIError as exc:
            log.warning("Bulk stock fetch failed, will use per-SKU fallback: %s", exc)
            stock_map = {}
        except RuntimeError as exc:
            log.warning("Dicker Data client not configured: %s", exc)
            return {"ok": False, "error": str(exc)}

        for sku in skus:
            try:
                # Merge bulk stock result with full product details.
                raw_product = self._c().get_product(sku)
                if sku in stock_map:
                    raw_product.update(stock_map[sku])
                product = _parse_product_from_api(raw_product)

                # Also pull pricing separately if cost_price not in product data.
                if product.cost_price_aud is None:
                    try:
                        pricing = self._c().get_pricing(sku)
                        product.cost_price_aud = _to_float(
                            pricing.get("cost_price_aud") or pricing.get("reseller_price") or pricing.get("cost")
                        )
                        product.unit_price_aud = product.unit_price_aud or _to_float(
                            pricing.get("rrp") or pricing.get("price")
                        )
                    except DickerDataAPIError:
                        pass  # pricing endpoint optional

                upsert_product(product)
                refreshed += 1

                # Record stock alert if qty is very low (threshold = 5).
                THRESHOLD = 5
                if product.stock_qty is not None and product.stock_qty <= THRESHOLD:
                    alert = StockAlert(
                        sku=sku,
                        description=product.description,
                        threshold=THRESHOLD,
                        current_qty=product.stock_qty,
                        triggered_at=datetime.utcnow(),
                    )
                    save_stock_alert(alert)
                    low_stock.append(sku)

            except DickerDataAPIError as exc:
                log.warning("Refresh failed for %s: %s", sku, exc)
                errors += 1
            except Exception as exc:
                log.warning("Unexpected error refreshing %s: %s", sku, exc)
                errors += 1

        return {
            "ok": True,
            "refreshed": refreshed,
            "errors": errors,
            "low_stock_skus": low_stock,
        }

    # ── Orders ─────────────────────────────────────────────────────────────

    def place_order(
        self,
        reference: str,
        lines: List[dict],
        delivery_address: dict,
    ) -> dict:
        """Place an order via the Dicker Data API and save it locally.

        Unlike other methods this RAISES on API error — the caller must know
        if an order submission fails.
        """
        if not reference:
            raise ValueError("reference is required")
        if not lines:
            raise ValueError("lines must not be empty")

        raw_order = self._c().place_order(reference, lines, delivery_address)

        order_lines = [
            OrderLine(
                sku=ln.get("sku", ""),
                quantity=int(ln.get("quantity", 1)),
                unit_price_aud=_to_float(ln.get("unit_price_aud") or ln.get("price")),
            )
            for ln in lines
        ]
        order = Order(
            reference=reference,
            lines=order_lines,
            status=raw_order.get("status", "submitted"),
            total_aud=_to_float(raw_order.get("total_aud") or raw_order.get("total")),
            created_at=datetime.utcnow(),
            tracking_number=raw_order.get("tracking_number"),
        )
        order = save_order(order)
        return _order_to_dict(order)

    def get_orders(self, limit: int = 20) -> List[dict]:
        """Return orders from local DB (most recent first)."""
        return [_order_to_dict(o) for o in get_orders(limit=limit)]

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return agent status: api_key configured, tracked SKU count, order count."""
        api_key = os.environ.get("DICKER_DATA_API_KEY", "")
        tracked = get_tracked_skus()
        orders = get_orders(limit=1000)
        return {
            "agent": "dicker_data",
            "api_key_configured": bool(api_key),
            "tracked_sku_count": len(tracked),
            "order_count": len(orders),
            "stock_alert_count": len(get_stock_alerts(limit=1000)),
        }
