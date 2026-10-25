"""Safe file output for the 'file' destination (e.g. a Paperless consume folder)."""

from __future__ import annotations

import os
from pathlib import Path
import shutil

MIN_FREE_BYTES = 256 * 1024 * 1024


class FileOutputError(Exception):
    """File could not be written."""


def write_atomic(target: Path, data: bytes, min_free: int = MIN_FREE_BYTES) -> None:
    """Write via a hidden temp file and rename, so folder watchers never see a partial PDF."""
    target.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(target.parent).free
    if free < len(data) + min_free:
        raise FileOutputError(
            f"Zu wenig freier Speicher in {target.parent} ({free // 2**20} MiB frei)"
        )
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except OSError as err:
        tmp.unlink(missing_ok=True)
        raise FileOutputError(f"Schreiben fehlgeschlagen: {err}") from err
