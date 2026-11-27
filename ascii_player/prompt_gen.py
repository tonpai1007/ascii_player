"""Multi-engine prompt-to-ASCII generator (AI, Web, Ollama, FIGlet, Procedural)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import random
import re
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

from PIL import Image, ImageDraw, ImageFont

from .images import AsciiGrid, text_to_grid
from .url_loader import fetch_url_bytes

CURATED_FONTS = (
    "slant",
    "big",
    "doom",
    "block",
    "banner3-D",
    "cyberlarge",
    "isometric1",
    "larry3d",
    "standard",
    "small",
    "mini",
    "graffiti",
    "starwars",
)

STARTER_PROMPTS = [
    "cyberpunk samurai cat",
    "mount fuji at sunset",
    "ringed planet in deep space",
    "neon retro skull",
    "fractal forest silhouette",
    "ASCII STUDIO",
]


@dataclass
class PromptResult:
    """Generated output from a text prompt."""

    prompt: str
    engine: str
    image: Optional[Image.Image] = None
    grid: Optional[AsciiGrid] = None
    saved_path: Optional[str] = None
    note: str = ""


def available_banner_fonts() -> List[str]:
    """Return available curated FIGlet font names."""
    try:
        import pyfiglet

        installed = set(pyfiglet.FigletFont.getFonts())
        curated = [font for font in CURATED_FONTS if font in installed]
        return curated or sorted(installed)[:20] or ["standard"]
    except Exception:
        return ["standard"]


def _save_generated_image(
    image: Image.Image, prompt: str, cache_dir: Optional[str] = None
) -> str:
    directory = cache_dir or os.path.join(tempfile.gettempdir(), "ascii_player_generated")
    os.makedirs(directory, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", prompt.strip())[:24].strip("_") or "art"
    filename = f"{slug}_{int(time.time() * 1000)}.png"
    path = os.path.join(directory, filename)
    image.convert("RGB").save(path, format="PNG")
    return path


RGBTuple = Tuple[int, int, int]


def _detect_palette(
    prompt: str, rng: random.Random
) -> Tuple[RGBTuple, RGBTuple, RGBTuple]:
    """Choose (bg_top, bg_bottom, accent) palette from prompt keywords or seed."""
    lower = prompt.lower()
    if any(k in lower for k in ("matrix", "hack", "code", "terminal", "cyber")):
        return (5, 16, 10), (10, 42, 24), (80, 255, 140)
    if any(k in lower for k in ("neon", "synth", "retro", "vapor", "cyberpunk")):
        return (14, 8, 36), (62, 14, 78), (0, 240, 255)
    if any(k in lower for k in ("fire", "lava", "volcano", "dragon", "phoenix", "flame")):
        return (26, 6, 8), (92, 18, 8), (255, 165, 40)
    if any(k in lower for k in ("sunset", "dawn", "dusk", "fuji", "warm")):
        return (24, 16, 54), (210, 84, 62), (255, 212, 110)
    if any(k in lower for k in ("ocean", "sea", "wave", "ice", "arctic", "water")):
        return (6, 20, 44), (16, 88, 128), (140, 240, 255)
    if any(k in lower for k in ("gold", "royal", "egypt", "crown", "sun")):
        return (18, 12, 24), (54, 34, 16), (255, 215, 70)
    if any(k in lower for k in ("space", "planet", "saturn", "galaxy", "cosmos", "moon")):
        return (4, 6, 18), (20, 14, 48), (190, 210, 255)

    palettes = [
        ((10, 18, 38), (28, 70, 110), (120, 220, 255)),
        ((20, 10, 34), (88, 28, 88), (255, 130, 200)),
        ((10, 26, 20), (30, 82, 54), (160, 255, 150)),
        ((28, 16, 12), (96, 44, 24), (255, 195, 95)),
    ]
    return rng.choice(palettes)


def _draw_gradient_sky(
    img: Image.Image, c0: Tuple[int, int, int], c1: Tuple[int, int, int]
) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)


def _draw_stars(
    draw: ImageDraw.ImageDraw, w: int, h: int, rng: random.Random, count: int = 90
) -> None:
    for _ in range(count):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, int(h * 0.72))
        brightness = rng.randint(150, 255)
        r = 2 if rng.random() > 0.88 else 1
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(brightness, brightness, 255))


def _draw_retro_grid(
    draw: ImageDraw.ImageDraw, w: int, h: int, horizon_y: int, accent: Tuple[int, int, int]
) -> None:
    for row in range(1, 9):
        t = (row / 8.0) ** 1.7
        y = int(horizon_y + t * (h - horizon_y))
        draw.line([(0, y), (w, y)], fill=accent, width=1)
    cx = w // 2
    for offset in range(-8, 9):
        x_bot = cx + offset * (w // 7)
        x_top = cx + offset * 14
        draw.line([(x_top, horizon_y), (x_bot, h)], fill=accent, width=1)


def _draw_motif_mountain(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
) -> None:
    _draw_stars(draw, w, h, rng, count=70)
    sun_r = int(min(w, h) * 0.22)
    cx, cy = w // 2, int(h * 0.44)
    draw.ellipse((cx - sun_r, cy - sun_r, cx + sun_r, cy + sun_r), fill=accent)
    for stripe_y in range(cy, cy + sun_r, 9):
        draw.rectangle((cx - sun_r, stripe_y, cx + sun_r, stripe_y + 3), fill=(25, 15, 35))

    # Distant ridge
    pts_far = [(0, h), (0, int(h * 0.68))]
    for x in range(0, w + 16, 24):
        pts_far.append((x, int(h * 0.56 + rng.randint(-18, 22))))
    pts_far.append((w, h))
    draw.polygon(pts_far, fill=(36, 28, 56))

    # Main peak + snow cap
    peak_x = w // 2 + rng.randint(-30, 30)
    peak_y = int(h * 0.25)
    base_l = (int(w * 0.12), h)
    base_r = (int(w * 0.88), h)
    draw.polygon([base_l, (peak_x, peak_y), base_r], fill=(18, 16, 28))
    cap_l = (int(peak_x - (peak_x - base_l[0]) * 0.28), int(peak_y + (h - peak_y) * 0.28))
    cap_r = (int(peak_x + (base_r[0] - peak_x) * 0.28), int(peak_y + (h - peak_y) * 0.28))
    draw.polygon([(peak_x, peak_y), cap_r, (peak_x, cap_r[1] + 10), cap_l], fill=(242, 245, 255))


def _draw_motif_city(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
) -> None:
    _draw_stars(draw, w, h, rng, count=65)
    moon_r = int(min(w, h) * 0.16)
    draw.ellipse((w - moon_r * 3, 24, w - moon_r, 24 + moon_r * 2), fill=accent)
    horizon = int(h * 0.78)
    _draw_retro_grid(draw, w, h, horizon, accent)

    x = 8
    while x < w - 20:
        bw = rng.randint(26, 54)
        bh = rng.randint(int(h * 0.24), int(h * 0.62))
        top = horizon - bh
        draw.rectangle((x, top, x + bw, horizon), fill=(12, 14, 24), outline=accent)
        for wy in range(top + 8, horizon - 10, 12):
            for wx in range(x + 6, x + bw - 8, 10):
                if rng.random() > 0.35:
                    win_col = accent if rng.random() > 0.3 else (255, 240, 170)
                    draw.rectangle((wx, wy, wx + 5, wy + 7), fill=win_col)
        x += bw + rng.randint(4, 10)


def _draw_motif_planet(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
) -> None:
    _draw_stars(draw, w, h, rng, count=140)
    cx, cy = w // 2, h // 2
    r = int(min(w, h) * 0.28)
    # Back ring half
    draw.arc((cx - r * 2, cy - r // 2, cx + r * 2, cy + r // 2), 180, 360, fill=accent, width=6)
    # Planet body + highlight
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(215, 225, 250))
    draw.ellipse((cx - r + 18, cy - r + 10, cx + r + 24, cy + r + 18), fill=(18, 22, 48))
    draw.ellipse((cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4), outline=accent, width=3)
    # Front ring half
    draw.arc(
        (cx - r * 2, cy - r // 2, cx + r * 2, cy + r // 2),
        0,
        180,
        fill=(255, 240, 190),
        width=7,
    )


def _draw_motif_cat(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
) -> None:
    _draw_stars(draw, w, h, rng, count=50)
    cx, cy = w // 2, int(h * 0.54)
    r = int(min(w, h) * 0.25)
    # Ears
    ear_fill = (235, 240, 250)
    draw.polygon(
        [
            (cx - r, cy - r // 3),
            (cx - int(r * 1.05), cy - int(r * 1.45)),
            (cx - r // 4, cy - int(r * 0.85)),
        ],
        fill=ear_fill,
    )
    draw.polygon(
        [
            (cx + r, cy - r // 3),
            (cx + int(r * 1.05), cy - int(r * 1.45)),
            (cx + r // 4, cy - int(r * 0.85)),
        ],
        fill=ear_fill,
    )
    draw.polygon(
        [
            (cx - int(r * 0.85), cy - int(r * 0.5)),
            (cx - int(r * 0.92), cy - int(r * 1.2)),
            (cx - r // 3, cy - int(r * 0.82)),
        ],
        fill=accent,
    )
    draw.polygon(
        [
            (cx + int(r * 0.85), cy - int(r * 0.5)),
            (cx + int(r * 0.92), cy - int(r * 1.2)),
            (cx + r // 3, cy - int(r * 0.82)),
        ],
        fill=accent,
    )
    # Head
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + int(r * 0.88)),
        fill=ear_fill,
        outline=accent,
        width=3,
    )
    # Eyes
    ew, eh = max(2, int(r * 0.22)), max(3, int(r * 0.26))
    pw, ph = max(1, min(4, ew - 1)), max(1, eh - 3)
    for side in (-1, 1):
        ex = cx + side * int(r * 0.42)
        ey = cy - int(r * 0.12)
        draw.ellipse((ex - ew, ey - eh, ex + ew, ey + eh), fill=accent)
        draw.ellipse((ex - pw, ey - ph, ex + pw, ey + ph), fill=(10, 12, 18))
    # Nose & whiskers
    draw.polygon([(cx - 10, cy + 12), (cx + 10, cy + 12), (cx, cy + 24)], fill=(255, 110, 150))
    for wy in (cy + 8, cy + 20, cy + 32):
        draw.line([(cx - r - 35, wy - 4), (cx - r // 2, wy)], fill=accent, width=3)
        draw.line([(cx + r // 2, wy), (cx + r + 35, wy - 4)], fill=accent, width=3)


def _draw_motif_skull(
    draw: ImageDraw.ImageDraw, w: int, h: int, accent: Tuple[int, int, int]
) -> None:
    cx, cy = w // 2, int(h * 0.45)
    r = int(min(w, h) * 0.28)
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + int(r * 0.78)),
        fill=(238, 242, 248),
        outline=accent,
        width=4,
    )
    jaw_w = int(r * 0.56)
    draw.rectangle(
        (cx - jaw_w, cy + int(r * 0.45), cx + jaw_w, cy + int(r * 1.05)),
        fill=(238, 242, 248),
        outline=accent,
        width=4,
    )
    er = max(2, int(r * 0.24))
    pr = max(1, er // 3)
    for side in (-1, 1):
        ex = cx + side * int(r * 0.4)
        ey = cy - int(r * 0.06)
        draw.ellipse((ex - er, ey - er, ex + er, ey + er), fill=(12, 14, 22))
        draw.ellipse((ex - pr, ey - pr, ex + pr, ey + pr), fill=accent)
    draw.polygon([(cx, cy + 12), (cx - 12, cy + 38), (cx + 12, cy + 38)], fill=(12, 14, 22))
    for tx in range(cx - jaw_w + 12, cx + jaw_w - 8, 16):
        draw.line([(tx, cy + int(r * 0.72)), (tx, cy + int(r * 1.05))], fill=(12, 14, 22), width=3)


def _draw_motif_heart(
    draw: ImageDraw.ImageDraw, w: int, h: int, accent: Tuple[int, int, int]
) -> None:
    cx, cy = w // 2, int(h * 0.48)
    scale = min(w, h) * 0.015
    pts = []
    for deg in range(0, 360, 4):
        t = math.radians(deg)
        x = 16 * (math.sin(t) ** 3)
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * scale, cy + y * scale))
    draw.polygon(pts, fill=accent, outline=(255, 240, 245))
    inner = [(cx + (px - cx) * 0.65, cy + (py - cy) * 0.65) for px, py in pts]
    draw.polygon(inner, fill=(255, 225, 235))


def _draw_motif_tree(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
) -> None:
    _draw_stars(draw, w, h, rng, count=60)
    moon_r = int(min(w, h) * 0.18)
    draw.ellipse((w // 2 - moon_r, 28, w // 2 + moon_r, 28 + moon_r * 2), fill=accent)

    def branch(x1: float, y1: float, angle: float, length: float, depth: int) -> None:
        if depth <= 0 or length < 4:
            return
        x2 = x1 + math.cos(angle) * length
        y2 = y1 + math.sin(angle) * length
        col = (240, 248, 255) if depth > 2 else accent
        draw.line([(x1, y1), (x2, y2)], fill=col, width=max(1, depth))
        branch(x2, y2, angle - 0.42, length * 0.72, depth - 1)
        branch(x2, y2, angle + 0.42, length * 0.72, depth - 1)

    branch(w // 2, h - 10, -math.pi / 2, h * 0.28, 7)


def _draw_motif_wave(
    draw: ImageDraw.ImageDraw, w: int, h: int, accent: Tuple[int, int, int]
) -> None:
    cx, cy = w // 2, int(h * 0.28)
    r = int(min(w, h) * 0.16)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 230, 150))
    for layer in range(6):
        base_y = int(h * (0.42 + layer * 0.09))
        amp = 14 + layer * 4
        pts = [(0, h)]
        for x in range(0, w + 8, 8):
            y = int(base_y + math.sin(x * 0.028 + layer * 0.9) * amp)
            pts.append((x, y))
        pts.append((w, h))
        shade = tuple(max(12, min(255, int(accent[i] * (0.35 + layer * 0.11)))) for i in range(3))
        draw.polygon(pts, fill=shade, outline=(235, 250, 255))


def _draw_motif_robot(
    draw: ImageDraw.ImageDraw, w: int, h: int, accent: Tuple[int, int, int]
) -> None:
    cx, cy = w // 2, int(h * 0.52)
    rw, rh = max(24, int(w * 0.22)), max(18, int(h * 0.30))
    ant_h = max(12, int(h * 0.11))
    # Antenna
    draw.line([(cx, cy - rh), (cx, cy - rh - ant_h)], fill=accent, width=4)
    draw.ellipse((cx - 6, cy - rh - ant_h - 6, cx + 6, cy - rh - ant_h + 6), fill=accent)
    # Head
    draw.rounded_rectangle(
        (cx - rw, cy - rh, cx + rw, cy + rh),
        radius=min(18, rh // 2),
        fill=(225, 235, 245),
        outline=accent,
        width=4,
    )
    # Visor
    vx0, vy0 = cx - rw + max(6, rw // 5), cy - rh // 2
    vx1, vy1 = cx + rw - max(6, rw // 5), max(cy - rh // 2 + 6, cy - 4)
    draw.rounded_rectangle(
        (vx0, vy0, vx1, vy1),
        radius=6,
        fill=(14, 18, 28),
        outline=accent,
        width=2,
    )
    er = max(3, min(10, (vy1 - vy0) // 3))
    eye_y = (vy0 + vy1) // 2
    draw.ellipse((cx - rw // 2 - er, eye_y - er, cx - rw // 2 + er, eye_y + er), fill=accent)
    draw.ellipse((cx + rw // 2 - er, eye_y - er, cx + rw // 2 + er, eye_y + er), fill=accent)
    # Mouth grill
    my0, my1 = cy + max(6, rh // 4), cy + max(14, int(rh * 0.65))
    draw.rectangle(
        (cx - rw // 2, my0, cx + rw // 2, my1),
        fill=(18, 22, 32),
        outline=accent,
        width=2,
    )
    for gx in range(cx - rw // 2 + 8, cx + rw // 2 - 4, 10):
        draw.line([(gx, my0), (gx, my1)], fill=accent, width=2)


def _draw_motif_spiral(
    draw: ImageDraw.ImageDraw, w: int, h: int, accent: Tuple[int, int, int]
) -> None:
    cx, cy = w // 2, h // 2
    max_r = min(w, h) * 0.44
    pts = []
    steps = 260
    for i in range(steps):
        t = i / steps
        ang = t * math.pi * 10
        rad = t * max_r
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    for i in range(len(pts) - 1):
        col = accent if i % 2 == 0 else (245, 248, 255)
        draw.line([pts[i], pts[i + 1]], fill=col, width=4)


def _draw_motif_abstract(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    accent: Tuple[int, int, int],
    rng: random.Random,
    prompt: str,
) -> None:
    _draw_stars(draw, w, h, rng, count=80)
    horizon = int(h * 0.72)
    _draw_retro_grid(draw, w, h, horizon, accent)
    cx, cy = w // 2, int(h * 0.44)
    base_r = int(min(w, h) * 0.28)
    for idx, mult in enumerate((1.0, 0.76, 0.52)):
        rad = int(base_r * mult)
        sides = rng.choice((5, 6, 8))
        rot = idx * 0.4 + rng.random()
        poly = [
            (cx + math.cos(rot + 2 * math.pi * k / sides) * rad,
             cy + math.sin(rot + 2 * math.pi * k / sides) * rad)
            for k in range(sides)
        ]
        fill = (240, 245, 255) if idx == 2 else None
        draw.polygon(poly, fill=fill, outline=accent)
    draw.ellipse(
        (cx - base_r - 12, cy - base_r - 12, cx + base_r + 12, cy + base_r + 12),
        outline=(245, 248, 255),
        width=2,
    )
    # Crisp centered caption for prompt identity
    label = prompt.strip().upper()[:26]
    if label:
        font = ImageFont.load_default()
        draw.rectangle(
            (cx - 110, h - 42, cx + 110, h - 14),
            fill=(10, 14, 22),
            outline=accent,
            width=2,
        )
        draw.text((cx - len(label) * 3, h - 34), label, fill=(245, 248, 255), font=font)


def generate_banner(
    prompt: str,
    font: str = "slant",
    width: int = 80,
    palette: Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = None,
) -> PromptResult:
    """Render a prompt as a crisp FIGlet ASCII banner grid."""
    text = str(prompt or "").strip() or "ASCII"
    chosen_font = font or "slant"
    lines: List[str] = []
    try:
        import pyfiglet

        rendered = pyfiglet.figlet_format(text, font=chosen_font, width=max(40, int(width)))
        lines = [line.rstrip() for line in rendered.splitlines()]
    except Exception:
        img = Image.new("RGB", (max(120, len(text) * 18), 48), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((10, 16), text.upper(), fill=(255, 255, 255), font=ImageFont.load_default())
        from .images import grid_lines, image_to_grid

        fallback_grid = image_to_grid(img, width=max(30, min(80, width)), preset="blocks")
        lines = grid_lines(fallback_grid, color=False)

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        lines = [text]

    grid = text_to_grid(lines, gradient=palette)
    return PromptResult(
        prompt=text,
        engine="banner",
        image=None,
        grid=grid,
        saved_path=None,
        note=f"FIGlet banner ({chosen_font})",
    )


def generate_procedural(
    prompt: str,
    size: Tuple[int, int] = (512, 320),
    save: bool = True,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Generate a high-contrast deterministic procedural illustration for any prompt."""
    text = str(prompt or "").strip() or "abstract art"
    digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    w, h = size
    c0, c1, accent = _detect_palette(text, rng)

    img = Image.new("RGB", (w, h), c0)
    _draw_gradient_sky(img, c0, c1)
    draw = ImageDraw.Draw(img)

    lower = text.lower()
    if any(k in lower for k in ("mountain", "fuji", "peak", "alp", "landscape")):
        _draw_motif_mountain(draw, w, h, accent, rng)
    elif any(k in lower for k in ("city", "cyberpunk", "skyline", "tower", "building")):
        _draw_motif_city(draw, w, h, accent, rng)
    elif any(k in lower for k in ("cat", "kitty", "fox", "wolf", "owl", "samurai")):
        _draw_motif_cat(draw, w, h, accent, rng)
    elif any(k in lower for k in ("skull", "skeleton", "bone")):
        _draw_motif_skull(draw, w, h, accent)
    elif any(k in lower for k in ("planet", "space", "saturn", "galaxy", "cosmos", "moon")):
        _draw_motif_planet(draw, w, h, accent, rng)
    elif any(k in lower for k in ("heart", "love")):
        _draw_motif_heart(draw, w, h, accent)
    elif any(k in lower for k in ("tree", "forest", "nature", "fractal")):
        _draw_motif_tree(draw, w, h, accent, rng)
    elif any(k in lower for k in ("wave", "ocean", "sea", "water")):
        _draw_motif_wave(draw, w, h, accent)
    elif any(k in lower for k in ("robot", "mech", "android", "bot")):
        _draw_motif_robot(draw, w, h, accent)
    elif any(k in lower for k in ("spiral", "vortex", "portal", "mandala")):
        _draw_motif_spiral(draw, w, h, accent)
    else:
        _draw_motif_abstract(draw, w, h, accent, rng, text)

    saved_path = _save_generated_image(img, text, cache_dir=cache_dir) if save else None
    return PromptResult(
        prompt=text,
        engine="procedural",
        image=img,
        grid=None,
        saved_path=saved_path,
        note="Offline procedural illustration",
    )


def generate_gemini_image(
    prompt: str,
    api_key: Optional[str] = None,
    save: bool = True,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Generate an illustration via Google Gemini image generation SDK."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY is not set")

    from google import genai
    from google.genai import types

    enhanced = (
        f"{prompt.strip()}, bold clear silhouette, high contrast lighting, "
        "clean composition suitable for ASCII art conversion"
    )
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=enhanced,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="4:3"),
        ),
    )

    for part in getattr(response, "parts", []) or []:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            img = Image.open(io.BytesIO(inline.data)).convert("RGB")
            saved = _save_generated_image(img, prompt, cache_dir=cache_dir) if save else None
            return PromptResult(
                prompt=prompt,
                engine="gemini",
                image=img,
                saved_path=saved,
                note="Generated with Gemini",
            )
    raise RuntimeError("Gemini did not return an image payload")


def generate_openai_image(
    prompt: str,
    api_key: Optional[str] = None,
    save: bool = True,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Generate an illustration via OpenAI Images API."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    import openai

    client = openai.OpenAI(api_key=key)
    enhanced = f"{prompt.strip()}, high contrast silhouette, bold composition"
    response = client.images.generate(
        model="gpt-image-1",
        prompt=enhanced,
        size="1024x1024",
    )
    item = response.data[0]
    b64 = getattr(item, "b64_json", None)
    if b64:
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    elif getattr(item, "url", None):
        req = urllib.request.Request(item.url, headers={"User-Agent": "ascii-player/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
    else:
        raise RuntimeError("OpenAI response had neither b64_json nor url")

    saved = _save_generated_image(img, prompt, cache_dir=cache_dir) if save else None
    return PromptResult(
        prompt=prompt,
        engine="openai",
        image=img,
        saved_path=saved,
        note="Generated with OpenAI",
    )


def generate_pollinations_image(
    prompt: str,
    timeout: int = 18,
    save: bool = True,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Generate an illustration via Pollinations zero-key image endpoint."""
    seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
    enhanced = f"{prompt.strip()}, high contrast, dramatic lighting, clean silhouette"
    url = (
        f"https://image.pollinations.ai/prompt/{quote(enhanced)}"
        f"?width=512&height=384&nologo=true&seed={seed}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "ascii-player/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        raw = response.read()
        if content_type and not content_type.startswith("image/"):
            raise RuntimeError(f"Unexpected content type: {content_type}")
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    saved = _save_generated_image(img, prompt, cache_dir=cache_dir) if save else None
    return PromptResult(
        prompt=prompt,
        engine="pollinations",
        image=img,
        saved_path=saved,
        note="Generated via Pollinations AI",
    )


def generate_web_image(
    prompt: str,
    timeout: int = 15,
    save: bool = True,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Fetch a matching reference image from the web without any API key."""
    candidate_urls: List[str] = []
    try:
        from ddgs import DDGS

        results = DDGS().images(prompt.strip(), max_results=6)
        for entry in results or []:
            img_url = entry.get("image") or entry.get("thumbnail")
            if img_url:
                candidate_urls.append(str(img_url))
    except Exception:
        pass

    if not candidate_urls:
        params = urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{prompt.strip()} filetype:bitmap",
                "gsrnamespace": "6",
                "gsrlimit": "5",
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            }
        )
        api_url = f"https://commons.wikimedia.org/w/api.php?{params}"
        payload = json.loads(
            fetch_url_bytes(api_url, timeout=timeout).decode("utf-8", "replace")
        )
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if infos and infos[0].get("url"):
                candidate_urls.append(str(infos[0]["url"]))

    last_err: Optional[Exception] = None
    for img_url in candidate_urls:
        try:
            raw = fetch_url_bytes(img_url, timeout=timeout)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            saved = _save_generated_image(img, prompt, cache_dir=cache_dir) if save else None
            return PromptResult(
                prompt=prompt,
                engine="web",
                image=img,
                saved_path=saved,
                note="Fetched reference image from web",
            )
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(f"No downloadable web image found ({last_err or 'empty results'})")


def generate_ollama_ascii(
    prompt: str,
    width: int = 72,
    model: Optional[str] = None,
    host: Optional[str] = None,
    timeout: int = 45,
) -> PromptResult:
    """Generate pure ASCII art via a local Ollama server and immediately unload weights."""
    base = (host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    chosen_model = model
    if not chosen_model:
        tags_req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(tags_req, timeout=3) as resp:
            tags = json.loads(resp.read().decode("utf-8", "replace"))
        models = tags.get("models") or []
        if not models:
            raise RuntimeError("No local Ollama models installed")
        chosen_model = str(models[0].get("name") or models[0].get("model"))

    instruction = (
        f"Draw clean, recognizable pure ASCII art of: {prompt.strip()}\n"
        f"Rules: max width {max(30, min(100, int(width)))} chars, use only printable ASCII "
        "characters, output ONLY the ASCII art with no markdown fences or explanation."
    )
    body = json.dumps(
        {
            "model": chosen_model,
            "prompt": instruction,
            "stream": False,
            "keep_alive": 0,
        }
    ).encode("utf-8")
    gen_req = urllib.request.Request(
        f"{base}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(gen_req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))

    raw_text = str(data.get("response") or "").strip()
    if not raw_text:
        raise RuntimeError("Ollama returned an empty response")
    lines = [
        line
        for line in raw_text.splitlines()
        if not line.strip().startswith("```")
    ]
    if not lines:
        raise RuntimeError("Ollama returned no usable ASCII lines")
    grid = text_to_grid(lines)
    return PromptResult(
        prompt=prompt,
        engine="ollama",
        image=None,
        grid=grid,
        saved_path=None,
        note=f"Local Ollama ({chosen_model})",
    )


def generate_from_prompt(
    prompt: str,
    engine: str = "auto",
    width: int = 80,
    font: str = "slant",
    api_keys: Optional[Dict[str, str]] = None,
    ollama_model: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> PromptResult:
    """Generate ASCII art from a text prompt using the requested engine or auto cascade."""
    cleaned = str(prompt or "").strip()
    if not cleaned:
        raise ValueError("Prompt cannot be empty")

    keys = api_keys or {}
    gemini_key = (
        keys.get("gemini")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    openai_key = keys.get("openai") or os.environ.get("OPENAI_API_KEY")
    selected = (engine or "auto").lower()

    if selected == "banner":
        return generate_banner(cleaned, font=font, width=width)
    if selected == "procedural":
        return generate_procedural(cleaned, cache_dir=cache_dir)
    if selected == "web":
        return generate_web_image(cleaned, cache_dir=cache_dir)
    if selected == "ollama":
        return generate_ollama_ascii(cleaned, width=width, model=ollama_model)

    if selected == "ai":
        errors: List[str] = []
        if gemini_key:
            try:
                return generate_gemini_image(cleaned, api_key=gemini_key, cache_dir=cache_dir)
            except Exception as exc:
                errors.append(f"gemini: {exc}")
        if openai_key:
            try:
                return generate_openai_image(cleaned, api_key=openai_key, cache_dir=cache_dir)
            except Exception as exc:
                errors.append(f"openai: {exc}")
        try:
            return generate_pollinations_image(cleaned, cache_dir=cache_dir)
        except Exception as exc:
            errors.append(f"pollinations: {exc}")
        raise RuntimeError("All AI image providers failed: " + "; ".join(errors))

    # "auto" cascade: AI (keyed -> Pollinations) -> Web image -> Local Ollama -> Procedural
    attempts = []
    if gemini_key:
        attempts.append(
            lambda: generate_gemini_image(cleaned, api_key=gemini_key, cache_dir=cache_dir)
        )
    if openai_key:
        attempts.append(
            lambda: generate_openai_image(cleaned, api_key=openai_key, cache_dir=cache_dir)
        )
    attempts.append(lambda: generate_pollinations_image(cleaned, cache_dir=cache_dir))
    attempts.append(lambda: generate_web_image(cleaned, cache_dir=cache_dir))
    attempts.append(lambda: generate_ollama_ascii(cleaned, width=width, model=ollama_model))

    notes: List[str] = []
    for attempt in attempts:
        try:
            return attempt()
        except Exception as exc:
            notes.append(str(exc))

    result = generate_procedural(cleaned, cache_dir=cache_dir)
    if notes:
        result.note = "Procedural fallback (online/local AI unavailable)"
    return result
