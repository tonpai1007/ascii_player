"""Modal screens for the ASCII Art Studio TUI."""

from typing import List, Tuple

from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DirectoryTree, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from ..config import ASCII_PRESETS, FILTER_MODES, POST_FX_MODES, PROMPT_ENGINES
from ..images import is_image_file, is_image_url
from ..themes import THEME_ORDER
from .helpers import LYRICS_EXT


class FilePickerScreen(Screen):
    """Modal file picker built on DirectoryTree."""

    def __init__(self, start_dir=".", **kwargs):
        super().__init__(**kwargs)
        self.start_dir = start_dir

    def compose(self):
        with Vertical(id="picker-container"):
            yield Static("Pick a file (Enter), Esc to cancel", id="picker-title")
            yield DirectoryTree(self.start_dir, id="picker-tree")

    def on_directory_tree_file_selected(self, event):
        path = str(event.path)
        if is_image_file(path) or is_image_url(path):
            kind = "image"
        elif path.lower().endswith(tuple(LYRICS_EXT)):
            kind = "lyrics"
        else:
            kind = "video"
        self.app.select_file(path, kind)
        self.app.pop_screen()

    def on_key(self, event):
        if event.key == "escape":
            self.app.pop_screen()
            event.stop()


class ExportScreen(ModalScreen):
    """Modal dialog to export the active ASCII canvas to TXT/ANS/HTML/PNG/GIF."""

    SUPPORTED_FORMATS = ("txt", "ans", "html", "png", "gif")

    def __init__(self, default_name: str = "ascii_art", default_format: str = "png", **kwargs):
        super().__init__(**kwargs)
        self.default_name = default_name or "ascii_art"
        requested = str(default_format or "png").lower()
        self.requested_format = requested
        self.substitution_notice = ""
        if requested and requested != "none" and requested not in self.SUPPORTED_FORMATS:
            self.substitution_notice = (
                f"{requested.upper()} export is a CLI / pop-out feature; "
                "the TUI export dialog uses PNG instead."
            )
        self.default_format = requested if requested in self.SUPPORTED_FORMATS else "png"

    def on_mount(self):
        if self.substitution_notice:
            self.notify(self.substitution_notice, title="Export format substituted")

    def compose(self):
        with Vertical(id="export-dialog"):
            yield Static("EXPORT ASCII ART", id="export-title")
            with Horizontal(classes="compact-row"):
                yield Label("Format:", classes="compact-label")
                yield Select(
                    [
                        ("PNG Image (.png)", "png"),
                        ("HTML TrueColor (.html)", "html"),
                        ("ANSI Color (.ans)", "ans"),
                        ("Plain Text (.txt)", "txt"),
                        ("Animated GIF (.gif)", "gif"),
                    ],
                    value=self.default_format,
                    id="export-modal-fmt",
                    allow_blank=False,
                    compact=True,
                    classes="compact-control",
                )
            with Horizontal(classes="compact-row"):
                yield Label("File:", classes="compact-label")
                yield Input(
                    value=f"{self.default_name}.{self.default_format}",
                    id="export-modal-path",
                    compact=True,
                    classes="compact-control",
                )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-export-cancel", compact=True)
                yield Button("Export", id="btn-export-confirm", variant="primary", compact=True)

    @on(Select.Changed, "#export-modal-fmt")
    def _on_fmt_changed(self, event):
        fmt = str(event.value or "png")
        inp = self.query_one("#export-modal-path", Input)
        current = (inp.value or self.default_name).strip()
        stem = current.rsplit(".", 1)[0] if "." in current else current
        inp.value = f"{stem}.{fmt}"

    @on(Button.Pressed, "#btn-export-cancel")
    def _on_cancel(self, event):
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-export-confirm")
    def _on_confirm(self, event):
        self._submit()

    @on(Input.Submitted, "#export-modal-path")
    def _on_submit(self, event):
        self._submit()

    def _submit(self):
        fmt = str(self.query_one("#export-modal-fmt", Select).value or "png")
        path = (self.query_one("#export-modal-path", Input).value or "").strip()
        if not path:
            path = f"{self.default_name}.{fmt}"
        self.app.pop_screen()
        self.app.export_current_canvas(path, fmt)

    def on_key(self, event):
        if event.key == "escape":
            self.app.pop_screen()
            event.stop()


def _build_palette_entries() -> List[Tuple[str, str, str]]:
    """Return list of (label, slash_cmd, arg) for the floating Command Palette."""
    entries: List[Tuple[str, str, str]] = [
        ("[cmd] Open Terminal Type Tab (Ctrl+D)", "/draw", ""),
        ("[cmd] Type Skull Stencil in Terminal", "/draw", "skull"),
        ("[cmd] Trace Current Art in Type Tab", "/draw", "trace"),
        ("[cmd] Switch to Studio Tab", "/studio", ""),
        ("[cmd] Toggle Live Webcam (Ctrl+W)", "/webcam", ""),
        ("[cmd] Freeze Webcam Snapshot", "/snap", ""),
        ("[cmd] Paste Image or URL from Clipboard (Ctrl+V)", "/paste", ""),
        ("[cmd] Toggle Files Drawer (Ctrl+O)", "/open", ""),
        ("[cmd] Toggle Style Inspector Drawer (Ctrl+B)", "/style", ""),
        ("[cmd] Toggle TrueColor / Monochrome", "/color", ""),
        ("[cmd] Auto-Fit Canvas to Viewport", "/width", "fit"),
        ("[cmd] Toggle Dithering", "/dither", ""),
        ("[cmd] Toggle Invert Brightness", "/invert", ""),
        ("[cmd] Copy ASCII to Clipboard (Ctrl+Y)", "/copy", ""),
        ("[cmd] Export ASCII Art (Ctrl+E)", "/export", ""),
        ("[cmd] Pop-out Playback in Terminal", "/popout", ""),
        ("[cmd] Previous Session Art (Alt+Left)", "/prev", ""),
        ("[cmd] Next Session Art (Alt+Right)", "/next", ""),
        ("[cmd] Toggle Activity Log (Ctrl+L)", "/log", ""),
        ("[cmd] Clear to Welcome Screen", "/clear", ""),
        ("[cmd] Clear all stackable Post-FX", "/fx", "clear"),
        ("[prompt] cyberpunk samurai cat", "/prompt", "cyberpunk samurai cat"),
        ("[prompt] mount fuji at sunset", "/prompt", "mount fuji at sunset"),
        ("[prompt] ringed planet in deep space", "/prompt", "ringed planet in deep space"),
        ("[banner] ASCII STUDIO", "/banner", "ASCII STUDIO"),
    ]
    for preset in ASCII_PRESETS:
        entries.append((f"[preset] {preset}", "/preset", preset))
    for effect in POST_FX_MODES:
        entries.append((f"[fx] toggle {effect}", "/fx", effect))
    for mode in FILTER_MODES:
        entries.append((f"[filter] {mode}", "/filter", mode))
    for theme in THEME_ORDER:
        entries.append((f"[theme] {theme}", "/theme", theme))
    for engine in PROMPT_ENGINES:
        entries.append((f"[engine] {engine}", "/engine", engine))
    return entries


class CommandPaletteScreen(ModalScreen):
    """Floating fuzzy Command Palette (OpenCode / Claude Code Ctrl+K style)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all_entries = _build_palette_entries()
        self._visible_entries: List[Tuple[str, str, str]] = []
        self._last_query: str = ""

    def compose(self):
        with Vertical(id="palette-dialog"):
            yield Static("COMMAND PALETTE", id="palette-title")
            yield Input(
                placeholder="Type to filter commands, presets, filters, themes...",
                id="palette-search",
                compact=True,
            )
            yield OptionList(id="palette-list")
            yield Static("Enter run  |  Up/Down select  |  Esc close", id="palette-hint")

    def on_mount(self):
        self._refresh_options("")
        self.query_one("#palette-search", Input).focus()

    def _refresh_options(self, query: str):
        import re

        self._last_query = query or ""
        q = self._last_query.strip().lower()
        ol = self.query_one("#palette-list", OptionList)
        ol.clear_options()
        if not q:
            matches = self._all_entries[:18]
        else:
            tokens = [t for t in re.split(r"[\s:]+", q) if t]
            prefix = [e for e in self._all_entries if e[0].lower().startswith(q)]
            sub = [e for e in self._all_entries if q in e[0].lower() and e not in prefix]
            tok_hits = [
                e
                for e in self._all_entries
                if e not in prefix
                and e not in sub
                and all(tok in f"{e[0]} {e[1]} {e[2]}".lower() for tok in tokens)
            ]
            matches = (prefix + sub + tok_hits)[:18]
        self._visible_entries = matches
        for idx, (label, _cmd, _arg) in enumerate(matches):
            ol.add_option(Option(label, id=f"pal-{idx}"))
        if matches:
            ol.highlighted = 0

    @on(Input.Changed, "#palette-search")
    def _on_search_changed(self, event):
        self._refresh_options(event.value)

    @on(Input.Submitted, "#palette-search")
    def _on_search_submitted(self, event):
        ol = self.query_one("#palette-list", OptionList)
        idx = ol.highlighted if ol.highlighted is not None else 0
        self._run_index(idx)

    @on(OptionList.OptionSelected, "#palette-list")
    def _on_option_selected(self, event):
        self._run_index(event.option_index)

    def _run_index(self, idx: int):
        try:
            cur_query = self.query_one("#palette-search", Input).value or ""
            if cur_query != self._last_query:
                self._refresh_options(cur_query)
        except Exception:
            pass
        if 0 <= idx < len(self._visible_entries):
            _label, cmd, arg = self._visible_entries[idx]
            self.app.pop_screen()
            self.app.execute_slash_command(cmd, arg)
            return
        self.app.pop_screen()

    def on_key(self, event):
        ol = self.query_one("#palette-list", OptionList)
        if event.key == "escape":
            self.app.pop_screen()
            event.stop()
        elif event.key == "down":
            if self._visible_entries:
                cur = ol.highlighted if ol.highlighted is not None else -1
                ol.highlighted = min(len(self._visible_entries) - 1, cur + 1)
            event.stop()
        elif event.key == "up":
            if self._visible_entries:
                cur = ol.highlighted if ol.highlighted is not None else 0
                ol.highlighted = max(0, cur - 1)
            event.stop()


class HelpScreen(ModalScreen):
    """Help overlay with omnibox slash commands and keybindings."""

    def compose(self):
        with Vertical(id="help-dialog"):
            yield Static("ASCII STUDIO -- OMNIBOX & SHORTCUTS", id="help-title")
            with VerticalScroll(id="help-body-scroll"):
                yield Static(
                    "OMNIBOX (always ready at bottom)\n"
                    "  <text>         Generate ASCII art from any prompt\n"
                    "  <path>         Open local PNG/JPG/GIF/MP4 (quotes ok)\n"
                    "  <url>          Load image, webpage og:image, or YouTube\n"
                    "  /<command>     Slash commands (/fx, /preset halfblock, ...)\n"
                    "  @<query>       Fuzzy pick local media files inline\n\n"
                    "SHORTCUTS & NAVIGATION\n"
                    "  Tab / Esc      Move between drawers/fields; Esc -> omnibox / canvas\n"
                    "  Ctrl+D         Switch Studio / Terminal Type tab (/type skull)\n"
                    "  Alt+M / Alt+A  In Type mode: Mirror chars / Assist ghost typing\n"
                    "  Alt+P          In Type mode: Replay typing animation\n"
                    "  Ctrl+K         Command Palette\n"
                    "  Ctrl+O         Toggle Files / Sources drawer\n"
                    "  Ctrl+B         Toggle Style Inspector drawer\n"
                    "  Ctrl+W         Toggle live webcam (Space freezes)\n"
                    "  Ctrl+Y         Copy ASCII art to clipboard\n"
                    "  Ctrl+E         Export (.png / .html / .ans / .txt / .gif)\n"
                    "  Ctrl+T         Cycle theme (opencode, claude, retro...)\n"
                    "  Ctrl+V         Paste image or URL from clipboard\n"
                    "  Ctrl+L         Toggle activity log drawer\n"
                    "  Alt+Left/Right Step session artwork history\n"
                    "  Ctrl+P / ^Q    Show help / Quit",
                    id="help-body",
                )
            yield Static("Esc / Ctrl+P to close", id="help-hint")

    def on_key(self, event):
        if event.key in ("escape", "ctrl+p"):
            self.app.pop_screen()
            event.stop()
