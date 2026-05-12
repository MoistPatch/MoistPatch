from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


GENESIS = "0" * 64


class AuditLog:
    """Append-only JSONL log with a SHA-256 hash chain.

    Each line: {prev_hash, entry_hash, ts, actor_type, agent, action, params, result}
    entry_hash = sha256(prev_hash + canonical_json(entry_without_hash))

    Tamper-evidence: if any line is modified, every subsequent entry_hash
    will fail to verify.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def _last_hash(self) -> str:
        if self.path.stat().st_size == 0:
            return GENESIS
        with self.path.open("rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except OSError:
                f.seek(0)
            tail = f.read().splitlines()
        if not tail:
            return GENESIS
        last = json.loads(tail[-1].decode("utf-8"))
        return last["entry_hash"]

    def append(
        self,
        *,
        agent: str,
        action: str,
        params: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        actor_type: str = "agent",
        authorization: str | None = None,
    ) -> str:
        """Append an entry. Returns the entry_hash."""
        with self._lock:
            prev = self._last_hash()
            body = {
                "prev_hash": prev,
                "ts": datetime.now(timezone.utc).isoformat(),
                "actor_type": actor_type,
                "agent": agent,
                "action": action,
                "params": params or {},
                "result": result or {},
                "authorization": authorization,
            }
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
            entry_hash = hashlib.sha256(
                (prev + canonical).encode("utf-8")
            ).hexdigest()
            body["entry_hash"] = entry_hash
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(body, sort_keys=True) + "\n")
            return entry_hash

    def verify(self) -> tuple[bool, int, str | None]:
        """Verify the hash chain. Returns (ok, lines_checked, first_bad_line_or_None)."""
        prev = GENESIS
        checked = 0
        with self.path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                stored = entry.pop("entry_hash")
                if entry.get("prev_hash") != prev:
                    return False, checked, f"line {i}: prev_hash mismatch"
                canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
                recomputed = hashlib.sha256(
                    (prev + canonical).encode("utf-8")
                ).hexdigest()
                if recomputed != stored:
                    return False, checked, f"line {i}: entry_hash invalid"
                prev = stored
                checked += 1
        return True, checked, None

    def iter_entries(self) -> Iterator[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
