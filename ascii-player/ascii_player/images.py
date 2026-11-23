"""Still-image, GIF frame and clipboard support for ASCII Player.

Renders photos and screenshots through the same preset pipeline used for video
playback, and adds reveal animations (decode / type / rain) for the terminal.

This module is deliberately UI-agnostic: the CLI image player and the TUI both
build on the functions here.
"""

from __future__ import annotations

import io
import html
import os
import random
import re
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import numpy as np
from PIL import Image

from .config import ASCII_PRESETS

IMAGE_EXT = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".tif", ".tiff", ".ico",
)

ANIMATIONS = ("none", "decode", "type", "rain")

GLITCH_POOL = "0123456789ABCDEF#@%&$*+=/\\|<>[]{}~^"
GLITCH_COLOR = (255, 70, 70)
DIM_COLOR = (90, 55, 55)
TEXT_COLOR = (235, 235, 235)
RESET = "\x1b[0m"

BAYER = np.array(
    [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
    dtype=np.float32,
) / 16.0 - 0.5

try:  # Pillow >= 9.1
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover
    RESAMPLE = Image.LANCZOS

_CHAR_CACHE = {}


# ------------------------------------------------------------------ input --

def is_image_file(path: str) -> bool:
    """True if the path has a supported still-image extension."""
    return str(path).lower().endswith(IMAGE_EXT)


def is_image_url(text: str) -> bool:
    """True for http(s) URLs whose path ends in an image extension."""
    text = str(text).strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    return urlparse(text).path.lower().endswith(IMAGE_EXT)


def _open_image(source) -> Image.Image:
    """Open a path, URL or PIL image without forcing a single frame."""
    if isinstance(source, Image.Image):
        return source

    text = str(source)
    if text.lower().startswith(("http://", "https://")):
        request = urllib.request.Request(
            text, headers={"User-Agent": "ascii-player/1.0"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
        return Image.open(io.BytesIO(raw))
    return Image.open(text)


def load_image(source) -> Image.Image:
    """Load an image from a path, URL or PIL image. Returns RGB."""
    image = _open_image(source)
    try:  # animated GIFs: use the first frame
        image.seek(0)
    except (EOFError, AttributeError):
        pass
    return image.convert("RGB")


def frame_count(source) -> int:
    """Number of frames in a GIF/WebP, or 1 for a still image."""
    image = _open_image(source)
    return int(getattr(image, "n_frames", 1) or 1)


def load_frames(source) -> List[Tuple[Image.Image, float]]:
    """Load every frame of an animated image as (RGB frame, seconds).

    Still images return a single frame with a zero duration. Durations are
    clamped to a sane minimum so broken GIF metadata cannot stall playback.
    """
    image = _open_image(source)
    total = int(getattr(image, "n_frames", 1) or 1)
    frames: List[Tuple[Image.Image, float]] = []
    for index in range(total):
        try:
            image.seek(index)
        except EOFError:
            break
        duration = image.info.get("duration", 100) or 100
        try:
            seconds = float(duration) / 1000.0
        except (TypeError, ValueError):
            seconds = 0.1
        frames.append((image.convert("RGB").copy(), max(0.02, seconds)))
    if not frames:
        image.seek(0)
        frames.append((image.convert("RGB"), 0.0))
    return frames


# --------------------------------------------------------------- rendering --

@dataclass
class AsciiGrid:
    """Glyph + color cells for one rendered image."""

    glyphs: np.ndarray      # (height, width) '<U1'
    rgb: np.ndarray         # (height, width, 3) uint8
    width: int
    height: int


def _char_array(preset: str) -> np.ndarray:
    chars = ASCII_PRESETS.get(preset, ASCII_PRESETS["classic"])
    if chars not in _CHAR_CACHE:
        _CHAR_CACHE[chars] = np.array(list(chars), dtype="<U1")
    return _CHAR_CACHE[chars]


def _ordered_dither(gray: np.ndarray, levels: int) -> np.ndarray:
    if levels <= 1:
        return gray
    height, width = gray.shape
    tile = np.tile(BAYER, (height // 4 + 1, width // 4 + 1))[:height, :width]
    return np.clip(gray + tile * (1.0 / levels), 0.0, 1.0)


def image_to_grid(
    image: Image.Image,
    width: int = 80,
    preset: str = "classic",
    aspect: float = 0.55,
    invert: bool = False,
    dither: bool = False,
    max_rows: Optional[int] = None,
    crop: bool = False,
) -> AsciiGrid:
    """Convert an image into a glyph/color grid sized for a character cell."""
    image = image.convert("RGB")
    if crop and aspect and aspect > 0:
        source_w, source_h = image.size
        target_ratio = 1.0 / aspect
        source_ratio = source_w / source_h if source_h else target_ratio
        if source_ratio > target_ratio:
            new_w = max(1, int(source_h * target_ratio))
            left = (source_w - new_w) // 2
            image = image.crop((left, 0, left + new_w, source_h))
        elif source_ratio < target_ratio:
            new_h = max(1, int(source_w / target_ratio))
            top = (source_h - new_h) // 2
            image = image.crop((0, top, source_w, top + new_h))
    source_w, source_h = image.size
    if source_w <= 0 or source_h <= 0:
        raise ValueError("image has no pixels")
    if width <= 0:
        width = 80

    rows = max(1, int(round(source_h / source_w * width * aspect)))
    if max_rows and rows > max_rows:
        width = max(4, int(round(width * max_rows / rows)))
        rows = max_rows

    small = image.resize((width, rows), RESAMPLE)
    gray = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    if invert:
        gray = 1.0 - gray

    chars = _char_array(preset)
    levels = len(chars)
    if dither:
        gray = _ordered_dither(gray, levels)

    index = np.clip((gray * (levels - 1)).astype(np.int32), 0, levels - 1)
    return AsciiGrid(chars[index], np.asarray(small, dtype=np.uint8), width, rows)


def _row_ansi(chars, rgb_row, color: bool, fallback=TEXT_COLOR) -> str:
    if not color or rgb_row is None:
        return "".join(chars)

    parts = []
    previous = None
    for char, rgb in zip(chars, rgb_row):
        cell = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if cell != previous:
            parts.append(f"\x1b[38;2;{cell[0]};{cell[1]};{cell[2]}m")
            previous = cell
        parts.append(char)
    parts.append(RESET)
    return "".join(parts)


def grid_lines(grid: AsciiGrid, color: bool = False) -> List[str]:
    """Render the final, clean frame."""
    glyph_rows = grid.glyphs.tolist()
    if not color:
        return ["".join(row) for row in glyph_rows]
    return [
        _row_ansi(row, grid.rgb[r].tolist(), True)
        for r, row in enumerate(glyph_rows)
    ]


def still_lines(
    source,
    width: int = 80,
    preset: str = "classic",
    color: bool = False,
    invert: bool = False,
    dither: bool = False,
    max_rows: Optional[int] = None,
    crop: bool = False,
) -> List[str]:
    """Convenience: load + render an image to ASCII rows."""
    grid = image_to_grid(
        load_image(source), width, preset,
        invert=invert, dither=dither, max_rows=max_rows, crop=crop,
    )
    return grid_lines(grid, color)


# -------------------------------------------------------------- animations --

def _noise_row(width: int, density: float) -> List[str]:
    return [
        random.choice(GLITCH_POOL) if random.random() < density else " "
        for _ in range(width)
    ]


def decode_lines(grid: AsciiGrid, progress: float, color: bool = False) -> List[str]:
    """Top-down reveal with corruption that settles as progress approaches 1."""
    progress = min(1.0, max(0.0, progress))
    eased = 1.0 - (1.0 - progress) ** 2
    revealed = int(eased * grid.height)
    glitch = 0.18 * (1.0 - progress) ** 1.6

    glyph_rows = grid.glyphs.tolist()
    rgb_rows = grid.rgb.tolist() if color else None
    lines = []

    for r in range(grid.height):
        if r < revealed:
            chars = glyph_rows[r]
            if glitch > 0:
                chars = [
                    random.choice(GLITCH_POOL)
                    if ch != " " and random.random() < glitch else ch
                    for ch in chars
                ]
            lines.append(_row_ansi(chars, rgb_rows[r] if color else None, color))
        elif r == revealed:
            lines.append(_row_ansi(_noise_row(grid.width, 0.32), None, color))
        else:
            lines.append(_row_ansi(_noise_row(grid.width, 0.03), None, color))
    return lines


def type_lines(grid: AsciiGrid, progress: float, color: bool = False) -> List[str]:
    """Typewriter reveal, row-major."""
    progress = min(1.0, max(0.0, progress))
    eased = 1.0 - (1.0 - progress) ** 2
    written = int(eased * grid.height * grid.width)

    glyph_rows = grid.glyphs.tolist()
    rgb_rows = grid.rgb.tolist() if color else None
    lines = []

    for r in range(grid.height):
        base = r * grid.width
        if written >= base + grid.width:
            chars = glyph_rows[r]
        elif written <= base:
            chars = [" "] * grid.width
        else:
            cut = written - base
            chars = glyph_rows[r][:cut] + [" "] * (grid.width - cut)
        lines.append(_row_ansi(chars, rgb_rows[r] if color else None, color))
    return lines


class RainAnimator:
    """Matrix-style rain that condenses into the image."""

    def __init__(self, grid: AsciiGrid):
        self.grid = grid
        self.drops = [random.uniform(-grid.height, 0) for _ in range(grid.width)]
        self.speeds = [random.uniform(0.5, 1.6) for _ in range(grid.width)]

    def lines(self, progress: float, dt: float, color: bool = False) -> List[str]:
        grid = self.grid
        glyph_rows = grid.glyphs.tolist()
        rgb_rows = grid.rgb.tolist() if color else None

        for c in range(grid.width):
            self.drops[c] += self.speeds[c] * max(0.0, dt) * grid.height * 1.6
            if self.drops[c] > grid.height + random.uniform(0, 14):
                self.drops[c] = random.uniform(-grid.height, 0)
                self.speeds[c] = random.uniform(0.5, 1.6)

        revealed = int(min(1.0, max(0.0, progress)) ** 1.5 * grid.height)
        trail_color = GLITCH_COLOR if color else None
        lines = []

        for r in range(grid.height):
            if r < revealed:
                chars = glyph_rows[r]
                if revealed - r < 4:
                    chars = [
                        random.choice(GLITCH_POOL)
                        if ch != " " and random.random() < 0.2 else ch
                        for ch in chars
                    ]
                lines.append(_row_ansi(chars, rgb_rows[r] if color else None, color))
            else:
                chars = []
                for c in range(grid.width):
                    distance = self.drops[c] - r
                    if 0 <= distance < 1:
                        chars.append(random.choice("01"))
                    elif 1 <= distance < 12:
                        chars.append(
                            random.choice(GLITCH_POOL)
                            if random.random() < 1 - distance / 12 else " "
                        )
                    else:
                        chars.append(" ")
                lines.append(_row_ansi(chars, None, False, trail_color))
        return lines


# --------------------------------------------------------------- clipboard --

def _grab_image_windows_mac() -> Optional[Image.Image]:
    try:
        from PIL import ImageGrab
    except ImportError:  # pragma: no cover
        return None
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(data, Image.Image):
        return data.convert("RGB")
    if isinstance(data, list):  # files copied in Explorer/Finder
        for path in data:
            if is_image_file(str(path)) and os.path.isfile(str(path)):
                try:
                    return load_image(str(path))
                except Exception:
                    continue
    return None


def _grab_image_linux() -> Optional[Image.Image]:
    import subprocess

    commands = (
        ["wl-paste", "--type", "image/png"],
        ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, timeout=3)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout:
            try:
                return Image.open(io.BytesIO(result.stdout)).convert("RGB")
            except Exception:
                continue
    return None


def clipboard_image() -> Optional[Image.Image]:
    """Return an image from the clipboard, or None if there is none."""
    if sys.platform == "darwin" or os.name == "nt":
        return _grab_image_windows_mac()
    if sys.platform.startswith("linux"):
        return _grab_image_linux()
    return None


def clipboard_text() -> Optional[str]:
    """Return clipboard text, or None. Best-effort across platforms."""
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        finally:
            root.destroy()
        if text:
            return text
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        import subprocess

        for command in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"]):
            try:
                result = subprocess.run(command, capture_output=True, timeout=3)
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and result.stdout:
                return result.stdout.decode("utf-8", "replace")
    return None


def save_clipboard_image(image: Image.Image, directory: Optional[str] = None) -> str:
    """Persist a clipboard image to a temp PNG and return its path."""
    directory = directory or os.path.join(
        tempfile.gettempdir(), "ascii_player_clipboard"
    )
    os.makedirs(directory, exist_ok=True)
    filename = f"clipboard_{int(time.time() * 1000)}.png"
    path = os.path.join(directory, filename)
    image.convert("RGB").save(path)
    return path


# ----------------------------------------------------------------- preview --

def render_preview_lines(
    source,
    width: int = 80,
    preset: str = "classic",
    color: bool = False,
    max_rows: int = 16,
    crop: bool = False,
) -> List[str]:
    """Still preview rows, small enough for the TUI preview panel."""
    try:
        grid = image_to_grid(load_image(source), width, preset, max_rows=max_rows, crop=crop)
        return grid_lines(grid, color)
    except Exception:
        return []


# ------------------------------------------------------------------ export --

_ANSI_COLOR = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m")
_ANSI_ANY = re.compile(r"\x1b\[[0-9;]*m")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ASCII art</title>
<style>
  html, body {{ background: #0f1117; margin: 0; }}
  pre.ascii {{
    color: #ebebeb;
    font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 14px;
    line-height: 1.05;
    padding: 24px;
    white-space: pre;
  }}
</style>
</head>
<body>
<pre class="ascii">
{art}
</pre>
</body>
</html>
"""


def _html_line(line: str) -> str:
    """Convert one truecolor ANSI row into escaped HTML."""
    parts = []
    position = 0
    span_open = False
    for match in _ANSI_COLOR.finditer(line):
        text = html.escape(line[position:match.start()], quote=False)
        if text:
            parts.append(text)
        if span_open:
            parts.append("</span>")
        red, green, blue = (int(value) for value in match.groups())
        parts.append(
            f'<span style="color:#{red:02x}{green:02x}{blue:02x}">'
        )
        span_open = True
        position = match.end()
    tail = _ANSI_ANY.sub("", line[position:])
    if tail:
        parts.append(html.escape(tail, quote=False))
    if span_open:
        parts.append("</span>")
    return "".join(parts)


def grid_to_html(grid: AsciiGrid) -> str:
    """Return a standalone HTML document for a rendered grid."""
    rows = "\n".join(_html_line(line) for line in grid_lines(grid, color=True))
    return HTML_TEMPLATE.format(art=rows)


def save_grid(grid: AsciiGrid, path: str) -> str:
    """Write a rendered grid as .txt, .ans or .html and return the path."""
    extension = os.path.splitext(path)[1].lower()
    if extension == ".html":
        document = grid_to_html(grid)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(document)
    elif extension == ".ans":
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(grid_lines(grid, color=True)))
            handle.write("\n")
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(grid_lines(grid, color=False)))
            handle.write("\n")
    return path
