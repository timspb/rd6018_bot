"""Dark image card renderer for the operator panel.

Presentation-only: it accepts rendered text and produces a PNG. It has no
access to Telegram, HA, controllers, or hardware.
"""

from __future__ import annotations

import html
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_TAG_RE = re.compile(r"<[^>]+>")
_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
    Path("C:/Windows/Fonts/consola.ttf"),
)


def _plain_lines(text: str) -> list[str]:
    plain = html.unescape(_TAG_RE.sub("", str(text or "")))
    return [line.rstrip() for line in plain.splitlines() if line.strip()]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def render_dark_panel(text: str) -> bytes:
    """Render a compact dark PNG card from already-rendered panel text."""
    lines = _plain_lines(text) or ["RD6018"]
    font = _font(18)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    boxes = [probe.textbbox((0, 0), line, font=font) for line in lines]
    line_height = max((box[3] - box[1] for box in boxes), default=20) + 8
    width = max((box[2] - box[0] for box in boxes), default=120) + 36
    height = line_height * len(lines) + 24
    image = Image.new("RGB", (width, height), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=18, fill=(35, 35, 35), outline=(62, 62, 62), width=2)
    for index, line in enumerate(lines):
        draw.text((18, 12 + index * line_height), line, fill=(242, 242, 242), font=font)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_dark_dashboard(chart: bytes | None, text: str) -> bytes:
    """Compose the existing chart above the dark operator state card."""
    panel = Image.open(io.BytesIO(render_dark_panel(text))).convert("RGB")
    if not chart:
        return _png_bytes(panel)
    graph = Image.open(io.BytesIO(chart)).convert("RGB")
    width = max(graph.width, panel.width)
    result = Image.new("RGB", (width, graph.height + panel.height), (20, 20, 20))
    result.paste(graph, ((width - graph.width) // 2, 0))
    result.paste(panel, ((width - panel.width) // 2, graph.height))
    return _png_bytes(result)


def _png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
