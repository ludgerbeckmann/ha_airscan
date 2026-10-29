"""On-disk queue for scans that could not be delivered yet (pure file logic)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .files import write_atomic

# Backoff between delivery attempts while Paperless stays unreachable (seconds).
RETRY_DELAYS = (60, 120, 300, 600, 900)
MIN_FREE_BYTES = 64 * 1024 * 1024


def next_delay(failures: int) -> int:
    """Delay before the next attempt after `failures` failed runs in a row (1-based)."""
    return RETRY_DELAYS[min(max(failures, 1), len(RETRY_DELAYS)) - 1]


class OutboxStore:
    """One PDF + one small JSON file per waiting scan. Blocking: call from an executor."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _json(self, item_id: str) -> Path:
        return self.path / f"{item_id}.json"

    def _pdf(self, item_id: str) -> Path:
        return self.path / f"{item_id}.pdf"

    def load(self) -> list[dict]:
        """All waiting items, oldest first. Unreadable entries are skipped."""
        items: list[dict] = []
        if not self.path.is_dir():
            return items
        for meta_file in self.path.glob("*.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict) and self._pdf(meta.get("id", "")).is_file():
                items.append(meta)
        return sorted(items, key=lambda m: m.get("created", ""))

    def add(self, pdf: bytes, meta: dict) -> dict:
        """Store a PDF with its upload metadata; returns the stored item."""
        item_id = uuid.uuid4().hex[:12]
        item = {
            "id": item_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "attempts": 0,
            "last_error": None,
            "rejected": False,
            **meta,
        }
        write_atomic(self._pdf(item_id), pdf, MIN_FREE_BYTES)   # PDF first: a JSON without PDF is ignored
        write_atomic(self._json(item_id), json.dumps(item, ensure_ascii=False).encode(), 0)
        return item

    def read_pdf(self, item_id: str) -> bytes:
        """Content of a waiting PDF."""
        return self._pdf(item_id).read_bytes()

    def update(self, item: dict, **changes) -> dict:
        """Persist changed fields (attempts, last_error, rejected)."""
        item.update(changes)
        write_atomic(self._json(item["id"]), json.dumps(item, ensure_ascii=False).encode(), 0)
        return item

    def remove(self, item_id: str) -> None:
        """Delete a delivered item."""
        self._json(item_id).unlink(missing_ok=True)   # JSON first: never a JSON without PDF
        self._pdf(item_id).unlink(missing_ok=True)
