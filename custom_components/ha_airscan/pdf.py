"""Lossless JPEG to PDF conversion (embeds the JPEG data as-is)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

_COLORSPACES = {"L": "DeviceGray", "RGB": "DeviceRGB", "CMYK": "DeviceCMYK"}


def jpegs_to_pdf(pages: list[bytes], dpi: int) -> bytes:
    """Build a multi-page PDF from JPEG images without re-encoding them."""
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []

    def add(body: bytes) -> None:
        offsets.append(len(out))
        out.extend(f"{len(offsets)} 0 obj\n".encode() + body + b"\nendobj\n")

    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(len(pages)))
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())

    for i, jpeg in enumerate(pages):
        with Image.open(BytesIO(jpeg)) as img:
            width, height = img.size
            colorspace = _COLORSPACES[img.mode]
        w_pt, h_pt = width * 72 / dpi, height * 72 / dpi
        page_no = 3 + 3 * i
        add(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.2f} {h_pt:.2f}] "
            f"/Resources << /XObject << /Im0 {page_no + 2} 0 R >> >> "
            f"/Contents {page_no + 1} 0 R >>".encode()
        )
        content = f"q {w_pt:.2f} 0 0 {h_pt:.2f} 0 0 cm /Im0 Do Q".encode()
        add(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
        add(
            (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /{colorspace} /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(jpeg)} >>\nstream\n"
            ).encode()
            + jpeg
            + b"\nendstream"
        )

    xref = len(out)
    out.extend(f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)
