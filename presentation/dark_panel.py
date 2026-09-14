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


_ICON_COLORS = {
    "🔋": (120, 210, 120),
    "⚡": (255, 210, 70),
    "🎯": (255, 100, 100),
    "🌡": (255, 150, 80),
    "⏱": (150, 190, 255),
    "✅": (100, 225, 130),
    "🛡": (120, 180, 255),
    "➡️": (150, 200, 255),
}

_ICON_FALLBACKS = {
    "🔋": "▣",
    "⚡": "ϟ",
    "🎯": "◎",
    "🌡": "♨",
    "⏱": "◷",
    "✅": "✓",
    "🛡": "◇",
    "➡️": "→",
}


def _draw_line(draw: ImageDraw.ImageDraw, line: str, xy: tuple[int, int], font) -> None:
    """Draw text with a colored leading icon and white informational text."""
    x, y = xy
    token, separator, rest = line.partition(" ")
    color = _ICON_COLORS.get(token)
    if color is None:
        draw.text((x, y), line, fill=(242, 242, 242), font=font)
        return
    glyph = _ICON_FALLBACKS.get(token, token)
    draw.text((x, y), glyph, fill=color, font=font)
    token_width = draw.textbbox((0, 0), glyph, font=font)[2]
    draw.text((x + token_width + (6 if separator else 0), y), rest, fill=(242, 242, 242), font=font)


def render_dark_panel(text: str, *, width: int | None = None) -> bytes:
    """Render a dark PNG card; optional width aligns it with the chart."""
    lines = _plain_lines(text) or ["RD6018"]
    font = _font(31)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    boxes = [probe.textbbox((0, 0), line, font=font) for line in lines]
    line_height = max((box[3] - box[1] for box in boxes), default=20) + 8
    natural_width = max((box[2] - box[0] for box in boxes), default=120) + 36
    width = max(int(width or 0), natural_width)
    height = line_height * len(lines) + 24
    image = Image.new("RGB", (width, height), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=18, fill=(35, 35, 35), outline=(62, 62, 62), width=2)
    for index, line in enumerate(lines):
        _draw_line(draw, line, (18, 12 + index * line_height), font)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_dark_dashboard(chart: bytes | None, text: str) -> bytes:
    """Compose the existing chart above the dark operator state card."""
    graph = Image.open(io.BytesIO(chart)).convert("RGB") if chart else None
    panel_width = graph.width if graph else None
    panel = Image.open(io.BytesIO(render_dark_panel(text, width=panel_width))).convert("RGB")
    if not chart:
        return _png_bytes(panel)
    assert graph is not None
    width = max(graph.width, panel.width)
    result = Image.new("RGB", (width, graph.height + panel.height), (20, 20, 20))
    result.paste(graph, ((width - graph.width) // 2, 0))
    result.paste(panel, ((width - panel.width) // 2, graph.height))
    return _png_bytes(result)


def _png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
