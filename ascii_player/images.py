"""Still-image, GIF frame and clipboard support for ASCII Player.

Renders photos and screenshots through the same preset pipeline used for video
playback, and adds reveal animations (decode / type / rain) for the terminal.

This module is deliberately UI-agnostic: the CLI image player and the TUI both
build on the functions here.
"""

from __future__ import annotations

import html
import io
import os
import random
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .config import ASCII_PRESETS, POST_FX_MODES
from .core import _char_array as _core_char_array
from .core import row_to_ansi
from .url_loader import fetch_url_bytes

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
    if text.lower().startswith(("http://", "https://", "file://")):
        # Only URL-like inputs go through the shared SSRF/size-limited fetcher;
        # ordinary local paths keep working as before. file:// is rejected by
        # the helper with a clear ValueError.
        raw = fetch_url_bytes(text)
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
    bg_rgb: Optional[np.ndarray] = None  # optional (height, width, 3) uint8


def _char_array(preset: str) -> np.ndarray:
    chars = ASCII_PRESETS.get(preset, ASCII_PRESETS["classic"])
    return _core_char_array(chars)


def _ordered_dither(gray: np.ndarray, levels: int) -> np.ndarray:
    if levels <= 1:
        return gray
    height, width = gray.shape
    tile = np.tile(BAYER, (height // 4 + 1, width // 4 + 1))[:height, :width]
    return np.clip(gray + tile * (1.0 / levels), 0.0, 1.0)


def preprocess_image(
    image: Image.Image,
    contrast: float = 1.0,
    brightness: float = 1.0,
    filter_mode: str = "none",
    colorcycle_hue: float = 0.0,
) -> Image.Image:
    """Apply non-destructive contrast, brightness, and artistic filters to an RGB image."""
    img = image.convert("RGB")
    if abs(contrast - 1.0) > 1e-3:
        clamped_contrast = max(0.2, min(3.5, float(contrast)))
        img = ImageEnhance.Contrast(img).enhance(clamped_contrast)
    if abs(brightness - 1.0) > 1e-3:
        clamped_brightness = max(0.2, min(3.0, float(brightness)))
        img = ImageEnhance.Brightness(img).enhance(clamped_brightness)

    mode = (filter_mode or "none").lower()
    if mode == "mirror":
        return ImageOps.mirror(img)
    if mode == "invert":
        return ImageOps.invert(img)
    if mode == "emboss":
        return img.filter(ImageFilter.EMBOSS)
    if mode == "sharpen":
        return img.filter(ImageFilter.SHARPEN)
    if mode == "contour":
        return img.filter(ImageFilter.CONTOUR)
    if mode == "posterize":
        return ImageOps.posterize(img, 3)
    if mode == "colorcycle":
        hsv = np.asarray(img.convert("HSV"), dtype=np.uint8).copy()
        shift = int(colorcycle_hue) % 256
        hsv[:, :, 0] = ((hsv[:, :, 0].astype(np.uint16) + shift) % 256).astype(np.uint8)
        return Image.fromarray(hsv, mode="HSV").convert("RGB")
    if mode == "edge":
        try:
            import cv2

            rgb_arr = np.asarray(img, dtype=np.uint8)
            gray_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray_arr, 80, 180)
            edge_mask = edges > 0
            boosted = np.clip(rgb_arr.astype(np.float32) * 1.35 + 40.0, 0, 255).astype(np.uint8)
            out = np.zeros_like(rgb_arr)
            out[edge_mask] = boosted[edge_mask]
            return Image.fromarray(out, mode="RGB")
        except Exception:
            return img.filter(ImageFilter.FIND_EDGES)
    return img


def apply_post_fx(image: Image.Image, effects: Sequence[str]) -> Image.Image:
    """Apply stackable post-FX (scanlines, chromatic, vignette, bloom, halftone, glitch)."""
    active = {str(fx).strip().lower() for fx in (effects or ()) if fx}
    active &= set(POST_FX_MODES)
    if not active:
        return image.convert("RGB")

    img = image.convert("RGB")
    arr = np.asarray(img, dtype=np.float32).copy()
    h, w = arr.shape[:2]
    if h == 0 or w == 0:
        return img

    if "chromatic" in active and w > 2:
        shift = max(1, w // 90)
        arr[:, :, 0] = np.roll(arr[:, :, 0], shift, axis=1)
        arr[:, :, 2] = np.roll(arr[:, :, 2], -shift, axis=1)

    if "bloom" in active:
        hi = np.clip((arr - 180.0) * 2.5, 0.0, 255.0).astype(np.uint8)
        radius = max(2, min(8, w // 60))
        glow = np.asarray(
            Image.fromarray(hi, mode="RGB").filter(ImageFilter.GaussianBlur(radius=radius)),
            dtype=np.float32,
        )
        arr = np.clip(arr + glow * 0.65, 0.0, 255.0)

    if "halftone" in active:
        yy = np.arange(h, dtype=np.float32)[:, None]
        xx = np.arange(w, dtype=np.float32)[None, :]
        pattern = 0.82 + 0.18 * (np.sin(xx * np.pi / 2.0) * np.sin(yy * np.pi / 2.0))
        arr *= pattern[:, :, None]

    if "vignette" in active:
        dy = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        dx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        dist = np.hypot(dx, dy) / 1.4142135
        mask = 1.0 - 0.68 * np.clip(dist ** 1.8, 0.0, 1.0)
        arr *= mask[:, :, None]

    if "scanlines" in active and h > 1:
        band = max(1, h // 120)
        scan_mask = ((np.arange(h) // band) % 2) == 1
        arr[scan_mask] *= 0.58

    if "glitch" in active and h >= 8 and w >= 8:
        rng = np.random.default_rng(42)
        band_h = max(1, h // 32)
        max_shift = max(2, w // 18)
        for _ in range(6):
            y0 = int(rng.integers(0, max(1, h - band_h)))
            y1 = min(h, y0 + band_h)
            dx = int(rng.integers(-max_shift, max_shift + 1))
            if dx == 0:
                dx = 2
            arr[y0:y1] = np.roll(arr[y0:y1], dx, axis=1)
            arr[y0:y1, :, 0] = np.roll(arr[y0:y1, :, 0], 1, axis=1)
            arr[y0:y1, :, 2] = np.roll(arr[y0:y1, :, 2], -1, axis=1)

    return Image.fromarray(np.clip(arr, 0.0, 255.0).astype(np.uint8), mode="RGB")


def _apply_grid_scanlines(grid: AsciiGrid) -> AsciiGrid:
    """Darken alternating ASCII rows so CRT scanlines stay crisp at low heights."""
    if grid.height <= 1:
        return grid
    rgb = grid.rgb.astype(np.float32).copy()
    rgb[1::2] *= 0.62
    bg_rgb = None
    if grid.bg_rgb is not None:
        bg_rgb = grid.bg_rgb.astype(np.float32).copy()
        bg_rgb[1::2] *= 0.62
        bg_rgb = np.clip(bg_rgb, 0.0, 255.0).astype(np.uint8)
    return AsciiGrid(
        grid.glyphs,
        np.clip(rgb, 0.0, 255.0).astype(np.uint8),
        grid.width,
        grid.height,
        bg_rgb=bg_rgb,
    )


def _render_halfblock_grid(
    image: Image.Image,
    width: int,
    rows: int,
    invert: bool = False,
) -> AsciiGrid:
    """Render using Unicode upper half-blocks for 2x vertical TrueColor resolution."""
    small = image.resize((width, max(2, rows * 2)), RESAMPLE)
    arr = np.asarray(small, dtype=np.uint8)
    if invert:
        arr = 255 - arr
    top_rgb = arr[0::2, :, :].copy()
    bot_rgb = arr[1::2, :, :].copy()
    glyphs = np.full((rows, width), "▀", dtype="<U1")
    return AsciiGrid(glyphs, top_rgb, width, rows, bg_rgb=bot_rgb)


def _render_braille_hd_grid(
    image: Image.Image,
    width: int,
    rows: int,
    invert: bool = False,
    dither: bool = False,
) -> AsciiGrid:
    """Render 2x4 sub-pixel clusters onto Unicode Braille patterns (U+2800..U+28FF)."""
    small = image.resize((width * 2, rows * 4), RESAMPLE)
    small_arr = np.asarray(small, dtype=np.uint8)
    gray = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    if invert:
        gray = 1.0 - gray
    if dither:
        gray = _ordered_dither(gray, 2)

    dots = (gray >= 0.5).reshape(rows, 4, width, 2).astype(np.int32)
    bits = (
        dots[:, 0, :, 0] * 0x01
        + dots[:, 1, :, 0] * 0x02
        + dots[:, 2, :, 0] * 0x04
        + dots[:, 3, :, 0] * 0x40
        + dots[:, 0, :, 1] * 0x08
        + dots[:, 1, :, 1] * 0x10
        + dots[:, 2, :, 1] * 0x20
        + dots[:, 3, :, 1] * 0x80
    )
    glyphs = np.array(
        [[chr(0x2800 + int(b)) for b in row] for row in bits.tolist()],
        dtype="<U1",
    )
    rgb = small_arr.reshape(rows, 4, width, 2, 3).mean(axis=(1, 3)).astype(np.uint8)
    return AsciiGrid(glyphs, rgb, width, rows)


def _render_edge_art_grid(
    image: Image.Image,
    width: int,
    rows: int,
    invert: bool = False,
    dither: bool = False,
) -> AsciiGrid:
    """Render directional Sobel edge strokes (|, -, /, \\) combined with shading."""
    small = image.resize((width, rows), RESAMPLE)
    gray = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    if invert:
        gray = 1.0 - gray

    p = np.pad(gray, 1, mode="edge")
    gx = (p[:-2, 2:] + 2.0 * p[1:-1, 2:] + p[2:, 2:]) - (
        p[:-2, :-2] + 2.0 * p[1:-1, :-2] + p[2:, :-2]
    )
    gy = (p[2:, :-2] + 2.0 * p[2:, 1:-1] + p[2:, 2:]) - (
        p[:-2, :-2] + 2.0 * p[:-2, 1:-1] + p[:-2, 2:]
    )
    mag = np.hypot(gx, gy)
    angle = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0

    shade_chars = _core_char_array(" .,:;+*#@")
    shade_gray = _ordered_dither(gray, len(shade_chars)) if dither else gray
    index = np.clip((shade_gray * (len(shade_chars) - 1)).astype(np.int32), 0, len(shade_chars) - 1)
    glyphs = shade_chars[index].copy()

    strong = mag > 0.45
    vert = strong & ((angle < 22.5) | (angle >= 157.5))
    horiz = strong & (angle >= 67.5) & (angle < 112.5)
    diag_slash = strong & (angle >= 22.5) & (angle < 67.5)
    diag_back = strong & (angle >= 112.5) & (angle < 157.5)
    glyphs[vert] = "|"
    glyphs[horiz] = "-"
    glyphs[diag_slash] = "/"
    glyphs[diag_back] = "\\"
    return AsciiGrid(glyphs, np.asarray(small, dtype=np.uint8), width, rows)


def _halfblock_mono_rows(grid: AsciiGrid) -> List[str]:
    """Convert a halfblock AsciiGrid with bg_rgb to monochrome half/full block chars."""
    if grid.bg_rgb is None:
        return ["".join(row) for row in grid.glyphs.tolist()]
    top = grid.rgb.astype(np.float32)
    bot = grid.bg_rgb.astype(np.float32)
    top_lum = top[:, :, 0] * 0.299 + top[:, :, 1] * 0.587 + top[:, :, 2] * 0.114
    bot_lum = bot[:, :, 0] * 0.299 + bot[:, :, 1] * 0.587 + bot[:, :, 2] * 0.114
    top_on = top_lum >= 128.0
    bot_on = bot_lum >= 128.0
    rows_out: List[str] = []
    for y in range(grid.height):
        chars = []
        for x in range(grid.width):
            t_bit = bool(top_on[y, x])
            b_bit = bool(bot_on[y, x])
            if t_bit and b_bit:
                chars.append("█")
            elif t_bit:
                chars.append("▀")
            elif b_bit:
                chars.append("▄")
            else:
                chars.append(" ")
        rows_out.append("".join(chars))
    return rows_out


def image_to_grid(
    image: Image.Image,
    width: int = 80,
    preset: str = "classic",
    aspect: float = 0.55,
    invert: bool = False,
    dither: bool = False,
    max_rows: Optional[int] = None,
    crop: bool = False,
    charset: Optional[str] = None,
    contrast: float = 1.0,
    brightness: float = 1.0,
    filter_mode: str = "none",
    colorcycle_hue: float = 0.0,
    post_fx: Sequence[str] = (),
) -> AsciiGrid:
    """Convert an image into a glyph/color grid sized for a character cell."""
    image = image.convert("RGB")
    if (
        abs(contrast - 1.0) > 1e-3
        or abs(brightness - 1.0) > 1e-3
        or (filter_mode and filter_mode != "none")
    ):
        image = preprocess_image(
            image,
            contrast=contrast,
            brightness=brightness,
            filter_mode=filter_mode,
            colorcycle_hue=colorcycle_hue,
        )
    if post_fx:
        image = apply_post_fx(image, post_fx)
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

    if not (charset and len(charset) >= 2):
        if preset == "halfblock":
            grid = _render_halfblock_grid(image, width, rows, invert=invert)
            return _apply_grid_scanlines(grid) if "scanlines" in set(post_fx or ()) else grid
        if preset == "braille_hd":
            grid = _render_braille_hd_grid(image, width, rows, invert=invert, dither=dither)
            return _apply_grid_scanlines(grid) if "scanlines" in set(post_fx or ()) else grid
        if preset == "edge_art":
            grid = _render_edge_art_grid(image, width, rows, invert=invert, dither=dither)
            return _apply_grid_scanlines(grid) if "scanlines" in set(post_fx or ()) else grid

    small = image.resize((width, rows), RESAMPLE)
    gray = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    if invert:
        gray = 1.0 - gray

    if charset and len(charset) >= 2:
        chars = _core_char_array(charset)
    else:
        chars = _char_array(preset)
    levels = len(chars)
    if dither:
        gray = _ordered_dither(gray, levels)

    index = np.clip((gray * (levels - 1)).astype(np.int32), 0, levels - 1)
    grid = AsciiGrid(chars[index], np.asarray(small, dtype=np.uint8), width, rows)
    return _apply_grid_scanlines(grid) if "scanlines" in set(post_fx or ()) else grid


def text_to_grid(
    lines: List[str],
    gradient: Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = None,
) -> AsciiGrid:
    """Convert raw ASCII text lines into an AsciiGrid with optional RGB gradient."""
    cleaned = [str(line).rstrip("\r") for line in lines]
    if not cleaned:
        cleaned = [" "]
    width = max((len(line) for line in cleaned), default=1) or 1
    height = len(cleaned)
    glyphs = np.full((height, width), " ", dtype="<U1")
    for r, line in enumerate(cleaned):
        for c, ch in enumerate(line[:width]):
            glyphs[r, c] = ch

    c0, c1 = gradient or ((88, 166, 255), (192, 132, 252))
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    denom = max(1, (height - 1) + (width - 1))
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]
    t = (ys + xs) / denom
    for ch_idx in range(3):
        rgb[:, :, ch_idx] = np.clip(c0[ch_idx] + (c1[ch_idx] - c0[ch_idx]) * t, 0, 255).astype(
            np.uint8
        )
    return AsciiGrid(glyphs, rgb, width, height)


def _halfblock_ansi_row(fg_row, bg_row) -> str:
    """Emit truecolor foreground+background ANSI for a halfblock row."""
    parts: List[str] = []
    width = len(fg_row)
    if width == 0:
        return ""
    run = 0
    prev = (
        fg_row[0][0],
        fg_row[0][1],
        fg_row[0][2],
        bg_row[0][0],
        bg_row[0][1],
        bg_row[0][2],
    )
    for idx in range(1, width):
        cur = (
            fg_row[idx][0],
            fg_row[idx][1],
            fg_row[idx][2],
            bg_row[idx][0],
            bg_row[idx][1],
            bg_row[idx][2],
        )
        if cur != prev:
            fr, fg, fb, br, bg, bb = prev
            parts.append(
                f"\x1b[38;2;{fr};{fg};{fb};48;2;{br};{bg};{bb}m"
                + ("▀" * (idx - run))
            )
            run = idx
            prev = cur
    fr, fg, fb, br, bg, bb = prev
    parts.append(
        f"\x1b[38;2;{fr};{fg};{fb};48;2;{br};{bg};{bb}m"
        + ("▀" * (width - run))
        + RESET
    )
    return "".join(parts)


def grid_to_rich_text(grid: AsciiGrid, color: bool = True):
    """Render an AsciiGrid as a Rich Text object with native 24-bit TrueColor spans."""
    from rich.text import Text

    if not color:
        if grid.bg_rgb is not None:
            return Text("\n".join(_halfblock_mono_rows(grid)), no_wrap=True)
        glyph_rows = grid.glyphs.tolist()
        return Text("\n".join("".join(row) for row in glyph_rows), no_wrap=True)

    glyph_rows = grid.glyphs.tolist()
    rich_text = Text(no_wrap=True)
    rgb_rows = grid.rgb.tolist()
    bg_rows = grid.bg_rgb.tolist() if grid.bg_rgb is not None else None
    num_rows = len(glyph_rows)
    for r, (chars, rgb_row) in enumerate(zip(glyph_rows, rgb_rows)):
        if chars:
            if bg_rows is not None:
                bg_row = bg_rows[r]
                run_start = 0
                prev_key = (
                    rgb_row[0][0],
                    rgb_row[0][1],
                    rgb_row[0][2],
                    bg_row[0][0],
                    bg_row[0][1],
                    bg_row[0][2],
                )
                for idx in range(1, len(chars)):
                    cur_key = (
                        rgb_row[idx][0],
                        rgb_row[idx][1],
                        rgb_row[idx][2],
                        bg_row[idx][0],
                        bg_row[idx][1],
                        bg_row[idx][2],
                    )
                    if cur_key != prev_key:
                        segment = "".join(chars[run_start:idx])
                        fr, fg, fb, br, bg, bb = prev_key
                        rich_text.append(
                            segment,
                            style=f"rgb({fr},{fg},{fb}) on rgb({br},{bg},{bb})",
                        )
                        run_start = idx
                        prev_key = cur_key
                segment = "".join(chars[run_start:])
                fr, fg, fb, br, bg, bb = prev_key
                rich_text.append(
                    segment,
                    style=f"rgb({fr},{fg},{fb}) on rgb({br},{bg},{bb})",
                )
            else:
                run_start = 0
                prev_rgb = tuple(rgb_row[0])
                for idx in range(1, len(chars)):
                    cur_rgb = tuple(rgb_row[idx])
                    if cur_rgb != prev_rgb:
                        segment = "".join(chars[run_start:idx])
                        rich_text.append(
                            segment,
                            style=f"rgb({prev_rgb[0]},{prev_rgb[1]},{prev_rgb[2]})",
                        )
                        run_start = idx
                        prev_rgb = cur_rgb
                segment = "".join(chars[run_start:])
                rich_text.append(
                    segment,
                    style=f"rgb({prev_rgb[0]},{prev_rgb[1]},{prev_rgb[2]})",
                )
        if r < num_rows - 1:
            rich_text.append("\n")
    return rich_text


# Process-wide cache of parsed Textual styles, keyed by (r, g, b) or (fr, fg, fb, br, bg, bb).
#
# Textual's Static.update() converts a Rich Text through Content.from_rich_text(),
# which re-parses every style string on *every* frame. A 160x66 truecolor frame
# carries ~10.5k spans, so that conversion cost ~235 ms/frame -- far beyond the
# 80 ms webcam cadence. Building Content directly with pre-parsed Style objects
# skips the conversion entirely (~26 ms/frame).
_STYLE_CACHE: dict = {}
_STYLE_CACHE_MAX = 100_000


def grid_to_content(grid: AsciiGrid, color: bool = True):
    """Render a *grid* as native Textual ``Content`` (the fast paint path).

    Returns a Rich ``Text`` when Textual is unavailable, so callers can treat
    the result as an opaque renderable either way.
    """
    try:
        from textual.color import Color
        from textual.content import Content, Span
        from textual.style import Style
    except ImportError:  # pragma: no cover - textual only ships with the TUI
        return grid_to_rich_text(grid, color=color)

    if grid is None:
        return Content("")

    if not color:
        if grid.bg_rgb is not None:
            return Content("\n".join(_halfblock_mono_rows(grid)))
        glyph_rows = grid.glyphs.tolist()
        return Content("\n".join("".join(row) for row in glyph_rows))

    glyph_rows = grid.glyphs.tolist()
    text = "\n".join("".join(row) for row in glyph_rows)

    height, width = grid.glyphs.shape
    if height == 0 or width == 0:
        return Content(text)

    cache = _STYLE_CACHE
    if len(cache) > _STYLE_CACHE_MAX:
        cache.clear()

    spans = []
    append = spans.append
    offset = 0
    if grid.bg_rgb is not None:
        fg_rows = grid.rgb.tolist()
        bg_rows = grid.bg_rgb.tolist()
        for r_idx in range(height):
            fg_row = fg_rows[r_idx]
            bg_row = bg_rows[r_idx]
            run = 0
            prev = (
                fg_row[0][0],
                fg_row[0][1],
                fg_row[0][2],
                bg_row[0][0],
                bg_row[0][1],
                bg_row[0][2],
            )
            for i in range(1, width):
                cur = (
                    fg_row[i][0],
                    fg_row[i][1],
                    fg_row[i][2],
                    bg_row[i][0],
                    bg_row[i][1],
                    bg_row[i][2],
                )
                if cur != prev:
                    style = cache.get(prev)
                    if style is None:
                        style = cache[prev] = Style(
                            foreground=Color(prev[0], prev[1], prev[2]),
                            background=Color(prev[3], prev[4], prev[5]),
                        )
                    append(Span(offset + run, offset + i, style))
                    run = i
                    prev = cur
            style = cache.get(prev)
            if style is None:
                style = cache[prev] = Style(
                    foreground=Color(prev[0], prev[1], prev[2]),
                    background=Color(prev[3], prev[4], prev[5]),
                )
            append(Span(offset + run, offset + width, style))
            offset += width + 1
    else:
        for row in grid.rgb.tolist():
            run = 0
            prev = (row[0][0], row[0][1], row[0][2])
            for i in range(1, width):
                cur = (row[i][0], row[i][1], row[i][2])
                if cur != prev:
                    style = cache.get(prev)
                    if style is None:
                        style = cache[prev] = Style(foreground=Color(*prev))
                    append(Span(offset + run, offset + i, style))
                    run = i
                    prev = cur
            style = cache.get(prev)
            if style is None:
                style = cache[prev] = Style(foreground=Color(*prev))
            append(Span(offset + run, offset + width, style))
            offset += width + 1

    return Content(text, spans)


_ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_to_content(text: str):
    """Convert truecolor ANSI text to native Textual ``Content``.

    ``row_to_ansi`` emits ``38;2;r;g;b`` and halfblock rows emit
    ``38;2;r;g;b;48;2;br;bg;bb``. Parsing directly with cached Style objects
    avoids Rich -> Textual style conversion overhead.
    """
    try:
        from textual.color import Color
        from textual.content import Content, Span
        from textual.style import Style
    except ImportError:  # pragma: no cover - textual only ships with the TUI
        from rich.text import Text

        return Text.from_ansi(text, no_wrap=True)

    if "\x1b[" not in text:
        return Content(text)

    cache = _STYLE_CACHE
    if len(cache) > _STYLE_CACHE_MAX:
        cache.clear()

    out = []
    spans = []
    append = spans.append
    plain_len = 0
    span_start = 0
    current = None
    pos = 0

    for match in _ANSI_SGR_RE.finditer(text):
        segment = text[pos : match.start()]
        out.append(segment)
        plain_len += len(segment)
        if current is not None and plain_len > span_start:
            append(Span(span_start, plain_len, current))

        code = match.group(1)
        if code.startswith("38;2;"):
            parts = code.split(";")
            if len(parts) == 10 and parts[5] == "48" and parts[6] == "2":
                try:
                    key = (
                        int(parts[2]),
                        int(parts[3]),
                        int(parts[4]),
                        int(parts[7]),
                        int(parts[8]),
                        int(parts[9]),
                    )
                except ValueError:
                    key = None
                if key is not None:
                    current = cache.get(key)
                    if current is None:
                        current = cache[key] = Style(
                            foreground=Color(key[0], key[1], key[2]),
                            background=Color(key[3], key[4], key[5]),
                        )
                else:
                    current = None
            elif len(parts) == 5:
                try:
                    key = (int(parts[2]), int(parts[3]), int(parts[4]))
                except ValueError:
                    key = None
                if key is not None:
                    current = cache.get(key)
                    if current is None:
                        current = cache[key] = Style(foreground=Color(*key))
                else:
                    current = None
            else:
                current = None
        else:
            # Reset (and any unsupported SGR) drops the current colour.
            current = None
        span_start = plain_len
        pos = match.end()

    tail = text[pos:]
    out.append(tail)
    plain_len += len(tail)
    if current is not None and plain_len > span_start:
        append(Span(span_start, plain_len, current))

    return Content("".join(out), spans)


def _row_ansi(chars, rgb_row, color: bool, fallback=TEXT_COLOR) -> str:
    return row_to_ansi(chars, rgb_row, color=color)


def grid_lines(grid: AsciiGrid, color: bool = False) -> List[str]:
    """Render the final, clean frame."""
    if not color:
        if grid.bg_rgb is not None:
            return _halfblock_mono_rows(grid)
        return ["".join(row) for row in grid.glyphs.tolist()]
    if grid.bg_rgb is not None:
        fg_rows = grid.rgb.tolist()
        bg_rows = grid.bg_rgb.tolist()
        return [_halfblock_ansi_row(fg_rows[r], bg_rows[r]) for r in range(grid.height)]
    glyph_rows = grid.glyphs.tolist()
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


def copy_text_to_clipboard(text: str) -> bool:
    """Copy plain text to the system clipboard. Best-effort across platforms."""
    if not text:
        return False
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            return True
        finally:
            root.destroy()
    except Exception:
        pass

    import subprocess

    commands = []
    if os.name == "nt":
        commands.append(["clip"])
    elif sys.platform == "darwin":
        commands.append(["pbcopy"])
    else:
        commands.extend([["wl-copy"], ["xclip", "-selection", "clipboard"]])

    for command in commands:
        try:
            result = subprocess.run(
                command,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=3,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return False


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


def _halfblock_html_line(chars, fg_row, bg_row) -> str:
    """Convert one halfblock row with fg/bg RGB into escaped HTML spans."""
    parts: List[str] = []
    width = len(chars)
    if width == 0:
        return ""
    run = 0
    prev = (
        fg_row[0][0],
        fg_row[0][1],
        fg_row[0][2],
        bg_row[0][0],
        bg_row[0][1],
        bg_row[0][2],
    )
    for idx in range(1, width):
        cur = (
            fg_row[idx][0],
            fg_row[idx][1],
            fg_row[idx][2],
            bg_row[idx][0],
            bg_row[idx][1],
            bg_row[idx][2],
        )
        if cur != prev:
            fr, fg, fb, br, bg, bb = prev
            seg = html.escape("".join(chars[run:idx]), quote=False)
            parts.append(
                f'<span style="color:#{fr:02x}{fg:02x}{fb:02x};'
                f'background-color:#{br:02x}{bg:02x}{bb:02x}">{seg}</span>'
            )
            run = idx
            prev = cur
    fr, fg, fb, br, bg, bb = prev
    seg = html.escape("".join(chars[run:]), quote=False)
    parts.append(
        f'<span style="color:#{fr:02x}{fg:02x}{fb:02x};'
        f'background-color:#{br:02x}{bg:02x}{bb:02x}">{seg}</span>'
    )
    return "".join(parts)


def grid_to_html(grid: AsciiGrid) -> str:
    """Return a standalone HTML document for a rendered grid."""
    if grid.bg_rgb is not None:
        glyph_rows = grid.glyphs.tolist()
        fg_rows = grid.rgb.tolist()
        bg_rows = grid.bg_rgb.tolist()
        rows = "\n".join(
            _halfblock_html_line(glyph_rows[r], fg_rows[r], bg_rows[r])
            for r in range(grid.height)
        )
        return HTML_TEMPLATE.format(art=rows)
    rows = "\n".join(_html_line(line) for line in grid_lines(grid, color=True))
    return HTML_TEMPLATE.format(art=rows)


def _load_mono_font():
    """Load a crisp monospace font for PNG ASCII rendering."""
    for name in (
        "consola.ttf",
        "CascadiaMono.ttf",
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "cour.ttf",
    ):
        try:
            return ImageFont.truetype(name, 13)
        except OSError:
            continue
    return ImageFont.load_default()


def save_grid_png(
    grid: AsciiGrid,
    path: str,
    color: bool = True,
    bg_color: Tuple[int, int, int] = (13, 17, 23),
) -> str:
    """Render an AsciiGrid into a crisp monospace PNG image."""
    char_w, char_h = 8, 14
    pad = 12
    img_w = max(1, grid.width * char_w + pad * 2)
    img_h = max(1, grid.height * char_h + pad * 2)
    canvas = Image.new("RGB", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    if color and grid.bg_rgb is not None:
        fg_rows = grid.rgb.tolist()
        bg_rows = grid.bg_rgb.tolist()
        half_h = char_h // 2
        for y in range(grid.height):
            py = pad + y * char_h
            for x in range(grid.width):
                px = pad + x * char_w
                fg = (int(fg_rows[y][x][0]), int(fg_rows[y][x][1]), int(fg_rows[y][x][2]))
                bg = (int(bg_rows[y][x][0]), int(bg_rows[y][x][1]), int(bg_rows[y][x][2]))
                draw.rectangle((px, py, px + char_w - 1, py + half_h - 1), fill=fg)
                draw.rectangle((px, py + half_h, px + char_w - 1, py + char_h - 1), fill=bg)
        canvas.save(path, format="PNG")
        return path

    font = _load_mono_font()
    if not color and grid.bg_rgb is not None:
        glyph_rows = [list(line) for line in _halfblock_mono_rows(grid)]
    else:
        glyph_rows = grid.glyphs.tolist()
    rgb_rows = grid.rgb.tolist()
    for y, row in enumerate(glyph_rows):
        py = pad + y * char_h
        for x, ch in enumerate(row):
            if ch == " ":
                continue
            fill = tuple(int(v) for v in rgb_rows[y][x]) if color else TEXT_COLOR
            draw.text((pad + x * char_w, py), ch, fill=fill, font=font)

    canvas.save(path, format="PNG")
    return path


def save_grid(grid: AsciiGrid, path: str, color: bool = False) -> str:
    """Write a rendered grid as .txt, .ans, .html, or .png and return the path.

    Only .ans and .png use colour; .txt is always plain text.
    """
    extension = os.path.splitext(path)[1].lower()
    if extension == ".png":
        return save_grid_png(grid, path, color=color)
    if extension == ".html":
        document = grid_to_html(grid)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(document)
    elif extension == ".ans":
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(grid_lines(grid, color=color)))
            handle.write("\n")
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(grid_lines(grid, color=False)))
            handle.write("\n")
    return path
