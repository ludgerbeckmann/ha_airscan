"""Summary of the last finished scan, shown as attributes."""

from __future__ import annotations

from datetime import datetime

SOURCES = {"platen": "platen", "adf": "adf", "adf_duplex": "adf_duplex"}


def summarize(result: dict, finished_at: datetime) -> dict:
    """Pick the user-facing facts out of a scan result."""
    return {
        "source": SOURCES.get(result.get("source", ""), result.get("source")),
        "destination": result.get("destination"),
        "document_id": result.get("document_id"),
        "blank_removed": result.get("blank_removed", 0),
        "finished_at": finished_at.isoformat(),
    }
