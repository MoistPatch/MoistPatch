"""
SQLite storage for the Dicker Data agent.
Database file: agents/dicker_data/dicker_data.db  (WAL mode)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Order, OrderLine, Product, StockAlert

_DB_PATH = Path(__file__).parent / "dicker_data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't already exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            sku          TEXT PRIMARY KEY,
            part_number  TEXT,
            description  TEXT,
            brand        TEXT,
            category     TEXT,
            unit_price_aud REAL,
            cost_price_aud REAL,
            stock_qty    INTEGER,
            stock_status TEXT,
            weight_kg    REAL,
            image_url    TEXT,
            updated_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            reference      TEXT,
            status         TEXT,
            total_aud      REAL,
            lines_json     TEXT,
            created_at     TEXT,
            tracking_number TEXT
        );

        CREATE TABLE IF NOT EXISTS stock_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sku          TEXT,
            description  TEXT,
            threshold    INTEGER,
            current_qty  INTEGER,
            triggered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tracked_skus (
            sku      TEXT PRIMARY KEY,
            label    TEXT,
            added_at TEXT
        );
    """)
    conn.commit()
    conn.close()


# ── Product helpers ────────────────────────────────────────────────────────

def _row_to_product(row: sqlite3.Row) -> Product:
    updated_at = None
    if row["updated_at"]:
        try:
            updated_at = datetime.fromisoformat(row["updated_at"])
        except ValueError:
            pass
    return Product(
        sku=row["sku"],
        part_number=row["part_number"],
        description=row["description"],
        brand=row["brand"],
        category=row["category"],
        unit_price_aud=row["unit_price_aud"],
        cost_price_aud=row["cost_price_aud"],
        stock_qty=row["stock_qty"],
        stock_status=row["stock_status"],
        weight_kg=row["weight_kg"],
        image_url=row["image_url"],
        updated_at=updated_at,
    )


def upsert_product(p: Product) -> None:
    conn = _connect()
    conn.execute(
        """INSERT INTO products
               (sku, part_number, description, brand, category,
                unit_price_aud, cost_price_aud, stock_qty, stock_status,
                weight_kg, image_url, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(sku) DO UPDATE SET
               part_number    = excluded.part_number,
               description    = excluded.description,
               brand          = excluded.brand,
               category       = excluded.category,
               unit_price_aud = excluded.unit_price_aud,
               cost_price_aud = excluded.cost_price_aud,
               stock_qty      = excluded.stock_qty,
               stock_status   = excluded.stock_status,
               weight_kg      = excluded.weight_kg,
               image_url      = excluded.image_url,
               updated_at     = excluded.updated_at
        """,
        (
            p.sku, p.part_number, p.description, p.brand, p.category,
            p.unit_price_aud, p.cost_price_aud, p.stock_qty, p.stock_status,
            p.weight_kg, p.image_url,
            p.updated_at.isoformat() if p.updated_at else datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_product(sku: str) -> Optional[Product]:
    conn = _connect()
    row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    conn.close()
    return _row_to_product(row) if row else None


def get_all_products(limit: int = 100) -> List[Product]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM products ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_product(r) for r in rows]


# ── Order helpers ──────────────────────────────────────────────────────────

def _row_to_order(row: sqlite3.Row) -> Order:
    lines_raw = json.loads(row["lines_json"] or "[]")
    lines = [
        OrderLine(
            sku=ln.get("sku", ""),
            quantity=ln.get("quantity", 1),
            unit_price_aud=ln.get("unit_price_aud"),
        )
        for ln in lines_raw
    ]
    created_at = None
    if row["created_at"]:
        try:
            created_at = datetime.fromisoformat(row["created_at"])
        except ValueError:
            pass
    return Order(
        id=row["id"],
        reference=row["reference"],
        lines=lines,
        status=row["status"],
        total_aud=row["total_aud"],
        created_at=created_at,
        tracking_number=row["tracking_number"],
    )


def save_order(o: Order) -> Order:
    lines_json = json.dumps(
        [{"sku": ln.sku, "quantity": ln.quantity, "unit_price_aud": ln.unit_price_aud} for ln in o.lines]
    )
    conn = _connect()
    if o.id:
        conn.execute(
            """UPDATE orders SET reference=?, status=?, total_aud=?,
                  lines_json=?, created_at=?, tracking_number=?
               WHERE id=?""",
            (
                o.reference, o.status, o.total_aud, lines_json,
                o.created_at.isoformat() if o.created_at else datetime.utcnow().isoformat(),
                o.tracking_number, o.id,
            ),
        )
        conn.commit()
        conn.close()
        return o
    cursor = conn.execute(
        """INSERT INTO orders (reference, status, total_aud, lines_json, created_at, tracking_number)
           VALUES (?,?,?,?,?,?)""",
        (
            o.reference, o.status, o.total_aud, lines_json,
            o.created_at.isoformat() if o.created_at else datetime.utcnow().isoformat(),
            o.tracking_number,
        ),
    )
    conn.commit()
    o.id = cursor.lastrowid
    conn.close()
    return o


def get_orders(limit: int = 20) -> List[Order]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


# ── Tracked SKUs ───────────────────────────────────────────────────────────

def add_tracked_sku(sku: str, label: str = "") -> None:
    conn = _connect()
    conn.execute(
        """INSERT INTO tracked_skus (sku, label, added_at)
           VALUES (?,?,?)
           ON CONFLICT(sku) DO UPDATE SET label = excluded.label""",
        (sku, label, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_tracked_sku(sku: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM tracked_skus WHERE sku = ?", (sku,))
    conn.commit()
    conn.close()


def get_tracked_skus() -> List[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM tracked_skus ORDER BY added_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stock alerts ───────────────────────────────────────────────────────────

def _row_to_alert(row: sqlite3.Row) -> StockAlert:
    triggered_at = None
    if row["triggered_at"]:
        try:
            triggered_at = datetime.fromisoformat(row["triggered_at"])
        except ValueError:
            pass
    return StockAlert(
        sku=row["sku"],
        description=row["description"],
        threshold=row["threshold"],
        current_qty=row["current_qty"],
        triggered_at=triggered_at,
    )


def save_stock_alert(a: StockAlert) -> None:
    conn = _connect()
    conn.execute(
        """INSERT INTO stock_alerts (sku, description, threshold, current_qty, triggered_at)
           VALUES (?,?,?,?,?)""",
        (
            a.sku, a.description, a.threshold, a.current_qty,
            a.triggered_at.isoformat() if a.triggered_at else datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_stock_alerts(limit: int = 20) -> List[StockAlert]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM stock_alerts ORDER BY triggered_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_alert(r) for r in rows]
