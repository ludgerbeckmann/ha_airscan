"""Blank page detection for scanned JPEG pages."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops, ImageFilter

DEFAULT_INK_PERCENT = 0.1
# Ignore the page border: scanner shadows, edge noise and punch holes.
MARGIN = 0.04
# A pixel counts as "ink" if it differs this much from its surroundings (dark text on light
# paper, but also light text on a dark page).
CONTRAST = 48
# Size of the surroundings in pixels of the reduced image (1/4 of the scan): about 8 mm at 300 dpi.
# Slow changes (a lid shadow, a gradient, uneven lighting) fall out, strokes and edges stay.
BACKGROUND_RADIUS = 25


def ink_percent(jpeg: bytes) -> tuple[float, int]:
    """Return (percentage of "ink" pixels, average brightness 0-255).

    "Ink" is everything that stands out from its local surroundings. A uniform area is no ink,
    whether it is white paper, a grey lid with a shadow, or the black of an open scanner.
    """
    with Image.open(BytesIO(jpeg)) as img:
        # JPEG draft mode decodes at 1/2, 1/4 or 1/8 size: much faster, plenty for this.
        img.draft("L", (max(img.width // 4, 1), max(img.height // 4, 1)))
        gray = img.convert("L")
    # Cut the border first: scanner shadows there must not leak into the surroundings of the page.
    w, h = gray.size
    mx, my = int(w * MARGIN), int(h * MARGIN)
    if w - 2 * mx > 8 and h - 2 * my > 8:
        gray = gray.crop((mx, my, w - mx, h - my))
    diff = ImageChops.difference(gray, gray.filter(ImageFilter.BoxBlur(BACKGROUND_RADIUS)))
    hist = diff.histogram()
    total = sum(hist)
    ink = sum(hist[CONTRAST + 1:])
    mean = int(sum(i * c for i, c in enumerate(gray.histogram())) / total)
    return ink * 100 / total, mean


def is_blank(jpeg: bytes, threshold: float = DEFAULT_INK_PERCENT) -> bool:
    """True if the page has (almost) no content."""
    ink, _ = ink_percent(jpeg)
    return ink < threshold


def filter_blank(
    pages: list[bytes], threshold: float = DEFAULT_INK_PERCENT
) -> tuple[list[bytes], int]:
    """Drop blank pages, keep the order. Returns (kept pages, number removed)."""
    kept = [p for p in pages if not is_blank(p, threshold)]
    return kept, len(pages) - len(kept)
