"""Find the sheet inside a feeder scan (pure Pillow, no numpy).

An Epson feeder scans wider than A4 and puts the sheet to one side, differently for the
front and the back of a duplex page. Next to the paper a strip of empty scanner background is
left, and between the two runs a faint, thin, perfectly straight dark line: the shadow of the
paper edge, over the whole height of the page. Text and pictures do not make such a line, so
only a line that most parts of the page agree on counts. Anything less clear leaves the
page as it is.
"""

from __future__ import annotations

from io import BytesIO
from statistics import median

from PIL import Image, ImageOps

BLOCKS = 40               # the page height is cut into this many bands, each votes on its own
ZONE_PX = 150             # how far from the border the line is looked for (at 300 dpi)
SKIP_PX = 10              # the very border of the image is no paper edge (half-size px)
MIN_DIP = 3.0             # how much darker than its surroundings the line is (brightness levels)
MIN_VOTES = 0.4           # share of bands that must see a line at all
MIN_AGREE = 0.7           # share of those that must agree on where (+-3 px)
TOLERANCE = (0.97, 1.04)  # the cut page must be about as wide as the paper


def _line_in_zone(img: Image.Image, scale: float, dpi: int) -> int | None:
    """Position of the edge line, counted from the left border of `img` (half-size px), or None."""
    zone_w = int(ZONE_PX * dpi / 300 / scale)
    cols = min(img.width, zone_w + 8)
    if cols < SKIP_PX + 12:
        return None
    zone = img.crop((0, 0, cols, img.height)).resize((cols, BLOCKS), Image.BOX)
    data = zone.tobytes()
    votes: list[int] = []
    for row in range(BLOCKS):
        p = data[row * cols:(row + 1) * cols]
        best: tuple[float, int] | None = None
        for x in range(SKIP_PX, min(zone_w, cols - 8)):
            around = (sum(p[x - 7:x - 3]) + sum(p[x + 4:x + 8])) / 8
            dip = around - (p[x - 1] + p[x] + p[x + 1]) / 3
            if dip >= MIN_DIP and (best is None or dip > best[0]):
                best = (dip, x)
        if best:
            votes.append(best[1])
    if len(votes) < MIN_VOTES * BLOCKS:
        return None
    centre = median(votes)
    if sum(abs(v - centre) <= 3 for v in votes) < MIN_AGREE * len(votes):
        return None
    return int(centre)


def find_paper(jpeg: bytes, dpi: int, paper_width_px: int) -> tuple[int, int] | None:
    """(x0, x1) of the sheet within the image, or None if the page is to stay as scanned.

    `paper_width_px` is the width of the paper size at this resolution; pages that are not
    clearly wider than the paper are left alone (nothing to cut).
    """
    try:
        with Image.open(BytesIO(jpeg)) as img:
            width = img.width
            if not paper_width_px or width < paper_width_px * 1.015:
                return None
            img.draft("L", (width // 2, img.height // 2))
            gray = img.convert("L")
    except (OSError, ValueError):
        return None
    scale = width / gray.width
    gray = gray.crop((0, int(gray.height * 0.03), gray.width, int(gray.height * 0.97)))
    left = _line_in_zone(gray, scale, dpi)
    right = _line_in_zone(ImageOps.mirror(gray), scale, dpi)
    if left is None and right is None:
        return None
    x0 = int((left + 2) * scale) if left is not None else 0
    x1 = width - int((right + 2) * scale) if right is not None else width
    if not paper_width_px * TOLERANCE[0] <= x1 - x0 <= paper_width_px * TOLERANCE[1]:
        return None
    return x0, x1
