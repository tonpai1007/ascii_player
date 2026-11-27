"""Interactive NumPy-backed ASCII art canvas engine for hand-drawn art."""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

import numpy as np

from ..images import AsciiGrid

RGB = Tuple[int, int, int]

DRAW_TOOLS = ("brush", "line", "box", "ellipse", "fill", "text", "eraser", "picker")
SYMMETRY_MODES = ("off", "x", "y", "xy")
BOX_STYLES = ("single", "double", "round", "solid")

QUICK_GLYPHS: List[str] = [
    "█",
    "▓",
    "▒",
    "░",
    "#",
    "@",
    "*",
    "+",
    "-",
    ".",
    "/",
    "\\",
    "─",
    "│",
    "┌",
    "┐",
    "└",
    "┘",
    "◆",
    "★",
]

COLOR_SWATCHES: List[Tuple[str, RGB]] = [
    ("White", (244, 244, 245)),
    ("Silver", (161, 161, 170)),
    ("Slate", (100, 116, 139)),
    ("Amber", (245, 158, 11)),
    ("Coral", (217, 119, 87)),
    ("Red", (239, 68, 68)),
    ("Rose", (251, 113, 133)),
    ("Magenta", (232, 121, 249)),
    ("Violet", (167, 139, 250)),
    ("Blue", (96, 165, 250)),
    ("Sky", (56, 189, 248)),
    ("Teal", (45, 212, 191)),
    ("Emerald", (52, 211, 153)),
    ("Lime", (163, 230, 53)),
    ("Yellow", (250, 204, 21)),
    ("Orange", (251, 146, 60)),
]

_DEFAULT_FG: RGB = (228, 228, 231)

MIRROR_CHAR_MAP: Dict[str, str] = {
    "(": ")",
    ")": "(",
    "/": "\\",
    "\\": "/",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
    "<": ">",
    ">": "<",
    "┌": "┐",
    "┐": "┌",
    "└": "┘",
    "┘": "└",
    "╭": "╮",
    "╮": "╭",
    "╰": "╯",
    "╯": "╰",
    "╔": "╗",
    "╗": "╔",
    "╚": "╝",
    "╝": "╚",
    "d": "b",
    "b": "d",
    "p": "q",
    "q": "p",
    "`": "'",
    "'": "`",
}


def mirror_char(ch: str) -> str:
    """Return horizontally mirrored glyph pair for pure-typing symmetry."""
    if not ch:
        return " "
    return MIRROR_CHAR_MAP.get(ch[0], ch[0])


TERMINAL_COLORS: List[Tuple[str, RGB]] = [
    ("White", (238, 238, 242)),
    ("Green", (74, 222, 128)),
    ("Amber", (245, 158, 11)),
    ("Cyan", (56, 189, 248)),
    ("Red", (248, 113, 113)),
    ("Magenta", (232, 121, 249)),
    ("Gold", (250, 204, 21)),
    ("Slate", (148, 163, 184)),
]

STENCIL_ORDER: Tuple[str, ...] = ("off", "skull", "cat", "sword", "rose", "studio")

ASCII_STENCILS: Dict[str, str] = {
    "skull": "\n".join(
        [
            '       ______       ',
            '    .-"      "-.    ',
            '   /            \\   ',
            '  |              |  ',
            '  |,  .-.  .-.  ,|  ',
            '  | )(__/  \\__)( |  ',
            '  |/     /\\     \\|  ',
            '  (_     ^^     _)  ',
            '   \\__|IIIIII|__/   ',
            '    | \\IIIIII/ |    ',
            '    \\          /    ',
            '     `--------`     ',
        ]
    ),
    "cat": "\n".join(
        [
            '    /\\_____/\\    ',
            '   /  o   o  \\   ',
            '  ( ==  ^  == )  ',
            '   )         (   ',
            '  (           )  ',
            ' ( (  )   (  ) ) ',
            '(__(__)___(__)__)',
        ]
    ),
    "sword": "\n".join(
        [
            '       /|        ',
            '      / |        ',
            '     |  |        ',
            '     |  |        ',
            '     |  |        ',
            '     |  |        ',
            '  ===+--+===     ',
            '      ||         ',
            '      ||         ',
            '      ()         ',
        ]
    ),
    "rose": "\n".join(
        [
            '     _ . - . _     ',
            '    /  .---.  \\    ',
            '   |  ( (@) )  |   ',
            '    \\  `---\'  /    ',
            '     `._   _.\'     ',
            '      \\ | /       ',
            '       \\|/        ',
            '        |         ',
            '      .-|--.      ',
            '        |         ',
        ]
    ),
}


def stencil_to_grid(name: str, width: int, height: int) -> np.ndarray:
    """Center a named built-in ASCII stencil into a (height, width) '<U1' grid."""
    grid = np.full((height, width), " ", dtype="<U1")
    art = ASCII_STENCILS.get((name or "").lower())
    if not art:
        return grid
    lines = art.splitlines()
    art_h = len(lines)
    art_w = max((len(line) for line in lines), default=0)
    top = max(0, (height - art_h) // 2)
    left = max(0, (width - art_w) // 2)
    for r, line in enumerate(lines):
        y = top + r
        if y >= height:
            break
        for c, ch in enumerate(line):
            x = left + c
            if 0 <= x < width and ch != " ":
                grid[y, x] = ch
    return grid

_BOX_SETS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "single": ("┌", "─", "┐", "│", "└", "┘"),
    "double": ("╔", "═", "╗", "║", "╚", "╝"),
    "round": ("╭", "─", "╮", "│", "╰", "╯"),
}


def symmetry_points(
    x: int, y: int, width: int, height: int, mode: str = "off"
) -> List[Tuple[int, int]]:
    """Return deduplicated in-bounds coordinates mirrored according to *mode*."""
    candidates = [(x, y)]
    mx = width - 1 - x
    my = height - 1 - y
    if mode in ("x", "xy"):
        candidates.append((mx, y))
    if mode in ("y", "xy"):
        candidates.append((x, my))
    if mode == "xy":
        candidates.append((mx, my))

    seen = set()
    out: List[Tuple[int, int]] = []
    for px, py in candidates:
        if 0 <= px < width and 0 <= py < height and (px, py) not in seen:
            seen.add((px, py))
            out.append((px, py))
    return out


def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    """Integer Bresenham line rasterizer from (x0, y0) to (x1, y1)."""
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cx, cy = x0, y0
    while True:
        points.append((cx, cy))
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            cx += sx
        if e2 <= dx:
            err += dx
            cy += sy
    return points


def ellipse_points(
    x0: int, y0: int, x1: int, y1: int, filled: bool = False
) -> List[Tuple[int, int]]:
    """Rasterize an ellipse outline or filled interior inside the given box."""
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    rx = max(0.5, (right - left) / 2.0)
    ry = max(0.5, (bottom - top) / 2.0)

    pts: List[Tuple[int, int]] = []
    if filled:
        for py in range(top, bottom + 1):
            for px in range(left, right + 1):
                val = ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2
                if val <= 1.05:
                    pts.append((px, py))
        return pts

    seen = set()
    steps = max(24, int(2.0 * np.pi * max(rx, ry) * 2.0))
    for i in range(steps):
        ang = (2.0 * np.pi * i) / steps
        px = int(round(cx + rx * np.cos(ang)))
        py = int(round(cy + ry * np.sin(ang)))
        if (px, py) not in seen:
            seen.add((px, py))
            pts.append((px, py))
    return pts


def box_cells(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    style: str = "single",
    glyph: str = "#",
) -> List[Tuple[int, int, str]]:
    """Compute (x, y, char) cells for a rectangle between two corners."""
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    ch = (glyph or "#")[0]

    if style not in _BOX_SETS:
        cells: List[Tuple[int, int, str]] = []
        for px in range(left, right + 1):
            cells.append((px, top, ch))
            if bottom != top:
                cells.append((px, bottom, ch))
        for py in range(top + 1, bottom):
            cells.append((left, py, ch))
            if right != left:
                cells.append((right, py, ch))
        return cells

    tl, h_bar, tr, v_bar, bl, br = _BOX_SETS[style]
    cells = []
    if left == right and top == bottom:
        return [(left, top, tl)]
    if top == bottom:
        for px in range(left, right + 1):
            cells.append((px, top, h_bar))
        return cells
    if left == right:
        for py in range(top, bottom + 1):
            cells.append((left, py, v_bar))
        return cells

    cells.append((left, top, tl))
    cells.append((right, top, tr))
    cells.append((left, bottom, bl))
    cells.append((right, bottom, br))
    for px in range(left + 1, right):
        cells.append((px, top, h_bar))
        cells.append((px, bottom, h_bar))
    for py in range(top + 1, bottom):
        cells.append((left, py, v_bar))
        cells.append((right, py, v_bar))
    return cells


class AsciiCanvasModel:
    """Mutable TrueColor ASCII grid model with undo/redo, symmetry, and shape tools."""

    def __init__(self, width: int = 76, height: int = 24):
        self.width = max(8, int(width))
        self.height = max(4, int(height))
        self.glyphs = np.full((self.height, self.width), " ", dtype="<U1")
        self.rgb = np.full((self.height, self.width, 3), _DEFAULT_FG, dtype=np.uint8)
        self.drawn = np.zeros((self.height, self.width), dtype=bool)
        self.stroke_log: List[Tuple[int, int, str, RGB]] = []
        self._undo: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self._redo: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    def push_undo(self) -> None:
        """Snapshot the current grid onto the undo stack."""
        self._undo.append((self.glyphs.copy(), self.rgb.copy(), self.drawn.copy()))
        if len(self._undo) > 50:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> bool:
        """Revert to the previous snapshot if available."""
        if not self._undo:
            return False
        self._redo.append((self.glyphs.copy(), self.rgb.copy(), self.drawn.copy()))
        g, c, d = self._undo.pop()
        self.height, self.width = g.shape
        self.glyphs = g
        self.rgb = c
        self.drawn = d
        return True

    def redo(self) -> bool:
        """Re-apply an undone snapshot if available."""
        if not self._redo:
            return False
        self._undo.append((self.glyphs.copy(), self.rgb.copy(), self.drawn.copy()))
        g, c, d = self._redo.pop()
        self.height, self.width = g.shape
        self.glyphs = g
        self.rgb = c
        self.drawn = d
        return True

    @property
    def undo_depth(self) -> int:
        return len(self._undo)

    def set_cell(self, x: int, y: int, glyph: str, color: RGB) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            ch = (glyph or " ")[0]
            self.glyphs[y, x] = ch
            self.rgb[y, x] = color
            self.drawn[y, x] = ch != " "

    def erase_cell(self, x: int, y: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.glyphs[y, x] = " "
            self.rgb[y, x] = _DEFAULT_FG
            self.drawn[y, x] = False

    def type_char(
        self, x: int, y: int, ch: str, color: RGB, mirror: bool = False
    ) -> None:
        """Place one typed character at (x, y) and optionally mirror across center axis."""
        glyph = (ch or " ")[0]
        self.set_cell(x, y, glyph, color)
        self.stroke_log.append((x, y, glyph, color))
        if mirror:
            mx = self.width - 1 - x
            if mx != x and 0 <= mx < self.width:
                mirrored = mirror_char(glyph)
                self.set_cell(mx, y, mirrored, color)
                self.stroke_log.append((mx, y, mirrored, color))

    def erase_at(self, x: int, y: int, mirror: bool = False) -> None:
        """Erase cell at (x, y) and optionally its horizontal mirror cell."""
        self.erase_cell(x, y)
        if mirror:
            mx = self.width - 1 - x
            if mx != x and 0 <= mx < self.width:
                self.erase_cell(mx, y)

    def _brush_offsets(self, size: int) -> List[Tuple[int, int]]:
        radius = max(0, int(size) - 1)
        if radius == 0:
            return [(0, 0)]
        offsets: List[Tuple[int, int]] = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius + 1:
                    offsets.append((dx, dy))
        return offsets

    def stamp_brush(
        self,
        x: int,
        y: int,
        glyph: str,
        color: RGB,
        size: int = 1,
        symmetry: str = "off",
    ) -> None:
        for sx, sy in symmetry_points(x, y, self.width, self.height, symmetry):
            for dx, dy in self._brush_offsets(size):
                self.set_cell(sx + dx, sy + dy, glyph, color)

    def erase_brush(
        self, x: int, y: int, size: int = 1, symmetry: str = "off"
    ) -> None:
        for sx, sy in symmetry_points(x, y, self.width, self.height, symmetry):
            for dx, dy in self._brush_offsets(size):
                self.erase_cell(sx + dx, sy + dy)

    def draw_stroke(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        glyph: str,
        color: RGB,
        size: int = 1,
        symmetry: str = "off",
        erase: bool = False,
    ) -> None:
        for px, py in bresenham_line(x0, y0, x1, y1):
            if erase:
                self.erase_brush(px, py, size=size, symmetry=symmetry)
            else:
                self.stamp_brush(px, py, glyph, color, size=size, symmetry=symmetry)

    def draw_line(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        glyph: str,
        color: RGB,
        symmetry: str = "off",
    ) -> None:
        for px, py in bresenham_line(x0, y0, x1, y1):
            for sx, sy in symmetry_points(px, py, self.width, self.height, symmetry):
                self.set_cell(sx, sy, glyph, color)

    def draw_box(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: RGB,
        style: str = "single",
        glyph: str = "#",
        symmetry: str = "off",
    ) -> None:
        for px, py, ch in box_cells(x0, y0, x1, y1, style=style, glyph=glyph):
            for sx, sy in symmetry_points(px, py, self.width, self.height, symmetry):
                self.set_cell(sx, sy, ch, color)

    def draw_ellipse(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        glyph: str,
        color: RGB,
        filled: bool = False,
        symmetry: str = "off",
    ) -> None:
        for px, py in ellipse_points(x0, y0, x1, y1, filled=filled):
            for sx, sy in symmetry_points(px, py, self.width, self.height, symmetry):
                self.set_cell(sx, sy, glyph, color)

    def flood_fill(self, x: int, y: int, glyph: str, color: RGB) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        target_glyph = str(self.glyphs[y, x])
        target_drawn = bool(self.drawn[y, x])
        new_ch = (glyph or " ")[0]
        if target_glyph == new_ch and target_drawn and tuple(self.rgb[y, x].tolist()) == color:
            return

        queue = deque([(x, y)])
        visited = {(x, y)}
        limit = self.width * self.height
        while queue and len(visited) <= limit:
            cx, cy = queue.popleft()
            self.set_cell(cx, cy, new_ch, color)
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < self.width and 0 <= ny < self.height and (nx, ny) not in visited:
                    if (
                        str(self.glyphs[ny, nx]) == target_glyph
                        and bool(self.drawn[ny, nx]) == target_drawn
                    ):
                        visited.add((nx, ny))
                        queue.append((nx, ny))

    def draw_text(self, x: int, y: int, text: str, color: RGB) -> int:
        if not (0 <= y < self.height):
            return x
        cx = x
        for ch in text:
            if cx >= self.width:
                break
            if cx >= 0 and ch not in ("\r", "\n"):
                self.set_cell(cx, y, ch, color)
            cx += 1
        return min(self.width - 1, cx)

    def pick_cell(self, x: int, y: int) -> Tuple[str, RGB]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return "█", _DEFAULT_FG
        ch = str(self.glyphs[y, x])
        if not self.drawn[y, x] or ch == " ":
            return "█", tuple(int(v) for v in self.rgb[y, x])
        return ch, tuple(int(v) for v in self.rgb[y, x])

    def clear(self) -> None:
        self.glyphs.fill(" ")
        self.rgb[:, :] = _DEFAULT_FG
        self.drawn.fill(False)
        self.stroke_log.clear()

    def flip_horizontal(self) -> None:
        self.glyphs = np.fliplr(self.glyphs).copy()
        self.rgb = np.fliplr(self.rgb).copy()
        self.drawn = np.fliplr(self.drawn).copy()

    def flip_vertical(self) -> None:
        self.glyphs = np.flipud(self.glyphs).copy()
        self.rgb = np.flipud(self.rgb).copy()
        self.drawn = np.flipud(self.drawn).copy()

    def resize(self, new_width: int, new_height: int) -> None:
        nw = max(16, min(180, int(new_width)))
        nh = max(8, min(64, int(new_height)))
        if nw == self.width and nh == self.height:
            return
        g = np.full((nh, nw), " ", dtype="<U1")
        c = np.full((nh, nw, 3), _DEFAULT_FG, dtype=np.uint8)
        d = np.zeros((nh, nw), dtype=bool)
        copy_h = min(nh, self.height)
        copy_w = min(nw, self.width)
        g[:copy_h, :copy_w] = self.glyphs[:copy_h, :copy_w]
        c[:copy_h, :copy_w] = self.rgb[:copy_h, :copy_w]
        d[:copy_h, :copy_w] = self.drawn[:copy_h, :copy_w]
        self.width, self.height = nw, nh
        self.glyphs, self.rgb, self.drawn = g, c, d

    def to_ascii_grid(self) -> AsciiGrid:
        """Export canvas as a Studio-compatible AsciiGrid."""
        return AsciiGrid(self.glyphs.copy(), self.rgb.copy(), self.width, self.height)

    def load_ascii_grid(self, grid: AsciiGrid) -> None:
        """Replace canvas contents with an imported AsciiGrid (clamped cleanly)."""
        nw = max(16, min(180, int(grid.width)))
        nh = max(8, min(64, int(grid.height)))
        self.width, self.height = nw, nh
        self.glyphs = np.full((nh, nw), " ", dtype="<U1")
        self.rgb = np.full((nh, nw, 3), _DEFAULT_FG, dtype=np.uint8)
        copy_h = min(nh, grid.height)
        copy_w = min(nw, grid.width)
        self.glyphs[:copy_h, :copy_w] = grid.glyphs[:copy_h, :copy_w]
        self.rgb[:copy_h, :copy_w] = grid.rgb[:copy_h, :copy_w]
        self.drawn = self.glyphs != " "
