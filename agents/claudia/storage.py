"""SQLite storage for CLAUDIA conversation history."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Union

DB_PATH = Path(__file__).parent / "claudia.db"


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT
            )
        """)


def save_message(role: str, content: Union[str, list, dict]) -> None:
    """Save a message. Content can be a string OR a structured list/dict (will be JSON-encoded)."""
    if isinstance(content, str):
        payload = json.dumps({"_str": content})
    else:
        payload = json.dumps(content, default=str)
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?,?,?)",
            (role, payload, datetime.utcnow().isoformat()),
        )


def load_messages(limit: int = 40) -> list[dict]:
    """Load the last N messages in chronological order, deserialised for the Anthropic SDK."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    rows = list(reversed(rows))
    result = []
    for r in rows:
        try:
            decoded = json.loads(r["content"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(decoded, dict) and "_str" in decoded:
            result.append({"role": r["role"], "content": decoded["_str"]})
        else:
            result.append({"role": r["role"], "content": decoded})
    return result


def load_history_for_ui(limit: int = 60) -> list[dict]:
    """Return messages in a UI-friendly format (user text and assistant text only)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    rows = list(reversed(rows))

    ui_events = []
    for r in rows:
        try:
            decoded = json.loads(r["content"])
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(decoded, dict) and "_str" in decoded:
            ui_events.append({
                "type": "user" if r["role"] == "user" else "assistant",
                "text": decoded["_str"],
                "ts": r["created_at"],
            })
        elif isinstance(decoded, list) and r["role"] == "assistant":
            # Assistant content with text + tool_use blocks
            for block in decoded:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text" and block.get("text", "").strip():
                        ui_events.append({"type": "assistant", "text": block["text"], "ts": r["created_at"]})
                    elif btype == "tool_use":
                        ui_events.append({
                            "type": "tool_call",
                            "name": block.get("name", ""),
                            "args": block.get("input", {}),
                            "ts": r["created_at"],
                        })
        elif isinstance(decoded, list) and r["role"] == "user":
            # Tool results in a user message
            for block in decoded:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, list):
                        # Newer SDK returns content as list of blocks
                        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                    ui_events.append({
                        "type": "tool_result",
                        "preview": str(content)[:400],
                        "ts": r["created_at"],
                    })

    return ui_events


def clear_messages() -> None:
    with _db() as conn:
        conn.execute("DELETE FROM messages")
