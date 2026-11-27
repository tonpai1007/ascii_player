"""Pure-Typing Terminal ASCII Art Studio workspace & canvas widgets."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np
from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.events import Key, MouseDown
from textual.widget import Widget
from textual.widgets import Button, Static

from ..images import AsciiGrid
from .canvas_engine import (
    ASCII_STENCILS,
    RGB,
    STENCIL_ORDER,
    TERMINAL_COLORS,
    AsciiCanvasModel,
    stencil_to_grid,
)

# App-level Ctrl+key shortcuts that must bubble through untouched.
_PASSTHROUGH_KEYS = {
    "ctrl+d",
    "ctrl+k",
    "ctrl+e",
    "ctrl+y",
    "ctrl+t",
    "ctrl+q",
    "ctrl+p",
    "ctrl+o",
    "ctrl+b",
    "ctrl+l",
}


class DrawCanvas(Widget):
    """Pure keyboard terminal ASCII typing surface with blinking cursor & stencils."""

    can_focus = True

    def __init__(
        self,
        width: int = 76,
        height: int = 24,
        on_change: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model = AsciiCanvasModel(width=width, height=height)
        self.color: RGB = TERMINAL_COLORS[0][1]
        self.typing_mode: str = "free"  # "free" or "assist"
        self.mirror: bool = False
        self.stencil_name: str = "off"
        self.stencil_grid: Optional[np.ndarray] = None
        self.show_grid: bool = False
        self.cursor_x: int = 0
        self.cursor_y: int = 0
        self._line_start_x: int = 0
        self._on_change = on_change

        self._cursor_visible: bool = True
        self._blink_timer = None
        self._replay_timer = None
        self._replay_steps: List[Tuple[int, int, str, RGB]] = []
        self._replay_index: int = 0
        self._replaying: bool = False

        # Lightweight compatibility attributes
        self.tool: str = "text"
        self.glyph: str = "#"
        self.brush_size: int = 1
        self.symmetry: str = "off"

    def on_mount(self) -> None:
        self._sync_dimensions()
        self._blink_timer = self.set_interval(0.55, self._toggle_blink)

    def on_unmount(self) -> None:
        if self._blink_timer is not None:
            try:
                self._blink_timer.stop()
            except Exception:
                pass
            self._blink_timer = None
        self.stop_replay()

    def _toggle_blink(self) -> None:
        if not self.is_mounted or not self.has_focus:
            return
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def _sync_dimensions(self) -> None:
        self.styles.width = self.model.width
        self.styles.height = self.model.height

    def _notify(self) -> None:
        self.refresh()
        if self._on_change:
            self._on_change()

    def set_stencil(self, name: str, custom_grid: Optional[AsciiGrid] = None) -> None:
        """Load a ghost underlay stencil ('off', 'skull', 'cat', 'sword', 'rose', 'studio')."""
        clean = (name or "off").strip().lower()
        if clean == "off":
            self.stencil_name = "off"
            self.stencil_grid = None
            self._notify()
            return
        if clean == "studio":
            if custom_grid is None:
                self.stencil_name = "off"
                self.stencil_grid = None
                self._notify()
                return
            w, h = self.model.width, self.model.height
            buf = np.full((h, w), " ", dtype="<U1")
            copy_h = min(h, custom_grid.height)
            copy_w = min(w, custom_grid.width)
            top = max(0, (h - copy_h) // 2)
            left = max(0, (w - copy_w) // 2)
            buf[top : top + copy_h, left : left + copy_w] = custom_grid.glyphs[:copy_h, :copy_w]
            self.stencil_name = "studio"
            self.stencil_grid = buf
            self._jump_to_first_stencil_cell()
            self._notify()
            return
        if clean in ASCII_STENCILS:
            self.stencil_name = clean
            self.stencil_grid = stencil_to_grid(clean, self.model.width, self.model.height)
            self._jump_to_first_stencil_cell()
            self._notify()

    def _jump_to_first_stencil_cell(self) -> None:
        cell = self._next_stencil_cell()
        if cell is not None:
            nx, ny, _ch = cell
            self.cursor_x = nx
            self.cursor_y = ny
            self._line_start_x = nx

    def _next_stencil_cell(self) -> Optional[Tuple[int, int, str]]:
        if self.stencil_grid is None:
            return None
        h, w = self.stencil_grid.shape
        for y in range(h):
            for x in range(w):
                ch = str(self.stencil_grid[y, x])
                if ch != " " and not self.model.drawn[y, x]:
                    return (x, y, ch)
        return None

    def _type_next_stencil_char(self) -> bool:
        cell = self._next_stencil_cell()
        if cell is None:
            return False
        nx, ny, ch = cell
        self.model.push_undo()
        self.model.type_char(nx, ny, ch, self.color, mirror=False)
        self.cursor_x = min(self.model.width - 1, nx + 1)
        self.cursor_y = ny
        return True

    def start_replay(self) -> bool:
        """Animate the canvas keystrokes one character at a time with a live cursor."""
        self.stop_replay()
        steps: List[Tuple[int, int, str, RGB]] = list(self.model.stroke_log)
        if not steps:
            for y in range(self.model.height):
                for x in range(self.model.width):
                    if self.model.drawn[y, x]:
                        ch = str(self.model.glyphs[y, x])
                        r, g, b = (int(v) for v in self.model.rgb[y, x])
                        steps.append((x, y, ch, (r, g, b)))
        if not steps and self.stencil_grid is not None:
            for y in range(self.model.height):
                for x in range(self.model.width):
                    ch = str(self.stencil_grid[y, x])
                    if ch != " ":
                        steps.append((x, y, ch, self.color))
        if not steps:
            return False

        self.model.push_undo()
        self.model.clear()
        self._replay_steps = steps
        self._replay_index = 0
        self._replaying = True
        self._cursor_visible = True
        self._replay_timer = self.set_interval(0.03, self._tick_replay)
        self._notify()
        return True

    def _tick_replay(self) -> None:
        if not self.is_mounted or not self._replaying:
            return
        if self._replay_index >= len(self._replay_steps):
            self.stop_replay()
            self._notify()
            return
        x, y, ch, rgb = self._replay_steps[self._replay_index]
        self._replay_index += 1
        self.model.type_char(x, y, ch, rgb, mirror=False)
        self.cursor_x = min(self.model.width - 1, x + 1)
        self.cursor_y = y
        self._cursor_visible = True
        self._notify()

    def stop_replay(self) -> None:
        self._replaying = False
        if self._replay_timer is not None:
            try:
                self._replay_timer.stop()
            except Exception:
                pass
            self._replay_timer = None

    def render(self) -> Text:
        out = Text(no_wrap=True)
        focused = self.has_focus and self._cursor_visible
        w, h = self.model.width, self.model.height
        mid_x = w // 2
        ghost_style = Style(color="rgb(68,72,88)")
        axis_style = Style(color="rgb(54,58,72)")
        grid_style = Style(color="rgb(44,46,56)")
        for y in range(h):
            for x in range(w):
                if self.model.drawn[y, x]:
                    ch = str(self.model.glyphs[y, x])
                    r, g, b = (int(v) for v in self.model.rgb[y, x])
                    style = Style(color=f"rgb({r},{g},{b})")
                elif self.stencil_grid is not None and str(self.stencil_grid[y, x]) != " ":
                    ch = str(self.stencil_grid[y, x])
                    style = ghost_style
                elif self.mirror and x == mid_x:
                    ch = "┆"
                    style = axis_style
                elif self.show_grid:
                    ch = "·"
                    style = grid_style
                else:
                    ch = " "
                    style = Style()

                if focused and x == self.cursor_x and y == self.cursor_y:
                    style = style + Style(reverse=True, bold=True)
                out.append(ch, style=style)
            if y < h - 1:
                out.append("\n")
        return out

    def on_mouse_down(self, event: MouseDown) -> None:
        self.focus()
        self.cursor_x = max(0, min(self.model.width - 1, int(event.x)))
        self.cursor_y = max(0, min(self.model.height - 1, int(event.y)))
        self._line_start_x = self.cursor_x
        self._cursor_visible = True
        self._notify()
        event.stop()

    def _row_end_x(self, y: int) -> int:
        row = self.model.drawn[y]
        indices = np.flatnonzero(row)
        if len(indices) == 0:
            return 0
        return min(self.model.width - 1, int(indices[-1]) + 1)

    def _advance_cursor_after_char(self) -> None:
        if self.cursor_x + 1 < self.model.width:
            self.cursor_x += 1
        elif self.cursor_y + 1 < self.model.height:
            self.cursor_y += 1
            self.cursor_x = self._line_start_x

    def on_key(self, event: Key) -> None:
        key = event.key
        if key in _PASSTHROUGH_KEYS:
            return

        self._cursor_visible = True
        if self._replaying:
            if key == "escape":
                self.stop_replay()
                self._notify()
                event.stop()
                event.prevent_default()
            return

        if key == "ctrl+z":
            self.model.undo()
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key in ("ctrl+shift+z", "ctrl+r"):
            self.model.redo()
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "alt+m":
            self.mirror = not self.mirror
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "alt+a":
            self.typing_mode = "assist" if self.typing_mode == "free" else "free"
            if self.typing_mode == "assist" and self.stencil_grid is None:
                self.set_stencil("skull")
            else:
                self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "alt+p":
            if self._replaying:
                self.stop_replay()
            else:
                self.start_replay()
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if key == "left":
            self.cursor_x = max(0, self.cursor_x - 1)
            self._line_start_x = self.cursor_x
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "right":
            self.cursor_x = min(self.model.width - 1, self.cursor_x + 1)
            self._line_start_x = self.cursor_x
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "up":
            self.cursor_y = max(0, self.cursor_y - 1)
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "down":
            self.cursor_y = min(self.model.height - 1, self.cursor_y + 1)
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "home":
            self.cursor_x = 0
            self._line_start_x = 0
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "end":
            self.cursor_x = self._row_end_x(self.cursor_y)
            self._notify()
            event.stop()
            event.prevent_default()
            return
        if key == "tab":
            self.cursor_x = min(self.model.width - 1, self.cursor_x + 4)
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if key == "enter":
            if self.typing_mode == "assist" and self.stencil_grid is not None:
                self._type_next_stencil_char()
            else:
                self.cursor_y = min(self.model.height - 1, self.cursor_y + 1)
                self.cursor_x = self._line_start_x
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if key == "backspace":
            if self.typing_mode == "assist" and self.model.undo_depth > 0:
                self.model.undo()
            else:
                if self.cursor_x > 0:
                    self.cursor_x -= 1
                elif self.cursor_y > 0:
                    self.cursor_y -= 1
                    self.cursor_x = self._row_end_x(self.cursor_y)
                self.model.push_undo()
                self.model.erase_at(self.cursor_x, self.cursor_y, mirror=self.mirror)
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if key == "delete":
            self.model.push_undo()
            self.model.erase_at(self.cursor_x, self.cursor_y, mirror=self.mirror)
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if key == "space":
            if self.typing_mode == "assist" and self.stencil_grid is not None:
                self._type_next_stencil_char()
            else:
                self.model.push_undo()
                self.model.erase_at(self.cursor_x, self.cursor_y, mirror=self.mirror)
                self._advance_cursor_after_char()
            self._notify()
            event.stop()
            event.prevent_default()
            return

        if event.character and event.is_printable and len(event.character) == 1:
            if self.typing_mode == "assist" and self.stencil_grid is not None:
                self._type_next_stencil_char()
            else:
                self.model.push_undo()
                self.model.type_char(
                    self.cursor_x,
                    self.cursor_y,
                    event.character,
                    self.color,
                    mirror=self.mirror,
                )
                self._advance_cursor_after_char()
            self._notify()
            event.stop()
            event.prevent_default()


class DrawWorkspace(Static):
    """Pure-typing terminal ASCII Art Studio tab with stencils, mirror & replay."""

    def compose(self) -> ComposeResult:
        canvas = DrawCanvas(width=76, height=24, on_change=self.sync_toolbar, id="draw-canvas")
        with Vertical(id="draw-shell"):
            with Horizontal(id="draw-toolbar-top"):
                yield Button("mode:free", id="dt-mode", classes="draw-btn active", compact=True)
                yield Button("stencil:off", id="dt-stencil", classes="draw-btn", compact=True)
                yield Button("mirror:off", id="dt-mirror", classes="draw-btn", compact=True)
                yield Button("replay", id="dt-replay", classes="draw-btn", compact=True)
                yield Button("grid", id="dt-grid", classes="draw-btn", compact=True)
                yield Button("undo", id="dt-undo", classes="draw-btn", compact=True)
                yield Button("clr", id="dt-clear", classes="draw-btn", compact=True)
                yield Button("trace-st", id="dt-trace", classes="draw-btn", compact=True)
                yield Button("->studio", id="dt-send", classes="draw-btn accent-chip", compact=True)
                for idx, (_name, (r, g, b)) in enumerate(TERMINAL_COLORS):
                    swatch = Text("█", style=f"rgb({r},{g},{b})")
                    yield Button(
                        swatch,
                        id=f"dc-{idx}",
                        classes="swatch-btn active" if idx == 0 else "swatch-btn",
                        compact=True,
                    )

            with ScrollableContainer(id="draw-scroll"):
                with Container(id="draw-frame"):
                    yield canvas

            yield Static("", id="draw-status", markup=False)

    def on_mount(self) -> None:
        self.sync_toolbar()

    @property
    def canvas(self) -> DrawCanvas:
        return self.query_one("#draw-canvas", DrawCanvas)

    def focus_canvas(self) -> None:
        self.canvas.focus()

    def set_tool(self, tool: str) -> None:
        self.canvas.tool = tool
        self.focus_canvas()

    def set_glyph(self, glyph: str) -> None:
        if glyph:
            self.canvas.glyph = glyph[0]
            self.focus_canvas()

    def set_color(self, rgb: RGB) -> None:
        self.canvas.color = rgb
        self.sync_toolbar()
        self.canvas.focus()

    def load_stencil(self, name: str, custom_grid: Optional[AsciiGrid] = None) -> None:
        self.canvas.set_stencil(name, custom_grid=custom_grid)
        self.sync_toolbar()
        self.canvas.focus()

    def trace_grid(self, grid: AsciiGrid) -> None:
        self.canvas.set_stencil("studio", custom_grid=grid)
        self.sync_toolbar()
        self.canvas.focus()

    def import_grid(self, grid: AsciiGrid) -> None:
        self.canvas.model.push_undo()
        self.canvas.model.load_ascii_grid(grid)
        self.canvas._sync_dimensions()
        self.canvas.cursor_x = 0
        self.canvas.cursor_y = 0
        self.canvas._line_start_x = 0
        self.canvas.refresh()
        self.sync_toolbar()

    def export_grid(self) -> AsciiGrid:
        return self.canvas.model.to_ascii_grid()

    def sync_toolbar(self) -> None:
        try:
            c = self.canvas
            mode_btn = self.query_one("#dt-mode", Button)
            mode_btn.label = f"mode:{c.typing_mode}"
            if c.typing_mode == "assist":
                mode_btn.add_class("active")
            else:
                mode_btn.remove_class("active")

            stencil_btn = self.query_one("#dt-stencil", Button)
            stencil_btn.label = f"stencil:{c.stencil_name}"
            if c.stencil_name != "off":
                stencil_btn.add_class("active")
            else:
                stencil_btn.remove_class("active")

            mirror_btn = self.query_one("#dt-mirror", Button)
            mirror_btn.label = "mirror:on" if c.mirror else "mirror:off"
            if c.mirror:
                mirror_btn.add_class("active")
            else:
                mirror_btn.remove_class("active")

            replay_btn = self.query_one("#dt-replay", Button)
            replay_btn.label = "stop" if c._replaying else "replay"
            if c._replaying:
                replay_btn.add_class("active")
            else:
                replay_btn.remove_class("active")

            grid_btn = self.query_one("#dt-grid", Button)
            if c.show_grid:
                grid_btn.add_class("active")
            else:
                grid_btn.remove_class("active")

            for idx, (_name, rgb) in enumerate(TERMINAL_COLORS):
                sbtn = self.query_one(f"#dc-{idx}", Button)
                if c.color == rgb:
                    sbtn.add_class("active")
                else:
                    sbtn.remove_class("active")

            mode_label = "ASSIST" if c.typing_mode == "assist" else "FREE"
            mirror_label = "on" if c.mirror else "off"
            self.query_one("#draw-status", Static).update(
                f"Ln {c.cursor_y + 1}, Col {c.cursor_x + 1} | {c.model.width}x{c.model.height} | "
                f"{mode_label} | stencil:{c.stencil_name} | mirror:{mirror_label} | "
                f"type directly · Alt+M mirror · Alt+A assist · Alt+P replay · Ctrl+Z undo"
            )
        except Exception:
            pass

    @on(Button.Pressed)
    def _on_draw_button(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        c = self.canvas
        if bid == "dt-mode":
            c.typing_mode = "assist" if c.typing_mode == "free" else "free"
            if c.typing_mode == "assist" and c.stencil_grid is None:
                c.set_stencil("skull")
            else:
                self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-stencil":
            cur_idx = STENCIL_ORDER.index(c.stencil_name) if c.stencil_name in STENCIL_ORDER else 0
            nxt = STENCIL_ORDER[(cur_idx + 1) % len(STENCIL_ORDER)]
            if nxt == "studio":
                studio_grid = getattr(self.app, "_canvas_last_grid", None)
                if studio_grid is None:
                    nxt = STENCIL_ORDER[(cur_idx + 2) % len(STENCIL_ORDER)]
                    c.set_stencil(nxt)
                else:
                    c.set_stencil("studio", custom_grid=studio_grid)
            else:
                c.set_stencil(nxt)
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-mirror":
            c.mirror = not c.mirror
            c.refresh()
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-replay":
            if c._replaying:
                c.stop_replay()
            else:
                c.start_replay()
            c.refresh()
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-grid":
            c.show_grid = not c.show_grid
            c.refresh()
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-undo":
            c.model.undo()
            c.refresh()
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-clear":
            c.stop_replay()
            c.model.push_undo()
            c.model.clear()
            c.refresh()
            self.sync_toolbar()
            c.focus()
            return
        if bid == "dt-trace":
            self.app.trace_studio_in_draw()
            return
        if bid == "dt-send":
            self.app.send_draw_to_studio()
            return
        if bid.startswith("dc-"):
            idx = int(bid[3:])
            if 0 <= idx < len(TERMINAL_COLORS):
                self.set_color(TERMINAL_COLORS[idx][1])
            return
