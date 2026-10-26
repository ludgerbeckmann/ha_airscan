"""Blank page detection for scanned JPEG pages."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

DEFAULT_INK_PERCENT = 0.1
# Ignore the page border: scanner shadows, edge noise and punch holes.
MARGIN = 0.04
# A pixel counts as "ink" if it is this much darker than the paper level.
CONTRAST = 48
# Paper must be reasonably bright; an overall dark page (photo, black sheet) is content.
MIN_PAPER_LEVEL = 128


def ink_percent(jpeg: bytes) -> tuple[float, int]:
    """Return (percentage of ink pixels, paper brightness level 0-255)."""
    with Image.open(BytesIO(jpeg)) as img:
        # JPEG draft mode decodes at 1/2, 1/4 or 1/8 size: much faster, plenty for this.
        img.draft("L", (max(img.width // 4, 1), max(img.height // 4, 1)))
        gray = img.convert("L")
    w, h = gray.size
    mx, my = int(w * MARGIN), int(h * MARGIN)
    if w - 2 * mx > 8 and h - 2 * my > 8:
        gray = gray.crop((mx, my, w - mx, h - my))
    hist = gray.histogram()
    total = sum(hist)
    # Paper level = 90th percentile of brightness.
    acc, paper = 0, 255
    for level, count in enumerate(hist):
        acc += count
        if acc >= total * 0.9:
            paper = level
            break
    limit = max(paper - CONTRAST, 0)
    ink = sum(hist[:limit])
    return ink * 100 / total, paper


def is_blank(jpeg: bytes, threshold: float = DEFAULT_INK_PERCENT) -> bool:
    """True if the page has (almost) no content."""
    ink, paper = ink_percent(jpeg)
    return paper >= MIN_PAPER_LEVEL and ink < threshold


def filter_blank(
    pages: list[bytes], threshold: float = DEFAULT_INK_PERCENT
) -> tuple[list[bytes], int]:
    """Drop blank pages, keep the order. Returns (kept pages, number removed)."""
    kept = [p for p in pages if not is_blank(p, threshold)]
    return kept, len(pages) - len(kept)
