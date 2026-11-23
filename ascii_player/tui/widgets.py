"""TUI widgets for ASCII Video Player."""

import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Button, Input, Label, ListItem, ListView, Select, Static

from .. import __version__
from ..config import ASCII_PRESETS
from ..images import IMAGE_EXT, is_image_file, is_image_url
from .helpers import LYRICS_EXT, VIDEO_EXT, _load_recent


class PlaylistPanel(Static):
    """Show and manage the playback queue."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._seq = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("PLAYLIST", id="playlist-title")
            yield ListView(id="playlist-list", classes="playlist-list")
            with Horizontal(classes="playlist-buttons"):
                yield Button("Clear", id="btn-clear-pl")
                yield Button("Prev", id="btn-prev-pl")
                yield Button("Next", id="btn-next-pl")

    def refresh_playlist(self, playlist, index):
        lv = self.query_one("#playlist-list", ListView)
        lv.clear()
        for i, item in enumerate(playlist):
            name = os.path.basename(item["path"])
            prefix = "► " if i == index else "  "
            self._seq += 1
            lv.append(ListItem(Static(f"{prefix}{name}"), id=f"pl-{self._seq}"))
        if not playlist:
            self._seq += 1
            lv.append(ListItem(Static("  (empty)"), id=f"pl-{self._seq}"))

    def on_button_pressed(self, event):
        if event.button.id == "btn-clear-pl":
            self.app.clear_playlist()
        elif event.button.id == "btn-prev-pl":
            self.app.play_prev()
        elif event.button.id == "btn-next-pl":
            self.app.play_next()


class FileBrowser(Static):
    """Keyboard-navigable, list-based file browser."""

    def __init__(self, start_dir=".", **kwargs):
        super().__init__(**kwargs)
        self.current_dir = os.path.abspath(start_dir)
        self.entries = []  # list of (display, path, kind)
        self._cursor = 0
        self._seq = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("FILES", id="current-dir")
            with Horizontal(classes="dir-input-row"):
                yield Input(
                    placeholder="Path: /dir or C:\\dir",
                    id="dir-input",
                    classes="dir-input",
                )
            yield ListView(id="file-list", classes="file-list")
            with Horizontal(classes="browser-buttons"):
                yield Button("Up Dir", id="btn-up")
                yield Button("Home", id="btn-home")
                yield Button("Refresh", id="btn-refresh")

    def on_mount(self):
        self.refresh_files()

    def _list_view(self):
        return self.query_one("#file-list", ListView)

    def refresh_files(self):
        self.entries = []
        try:
            entries = sorted(os.listdir(self.current_dir))

            parent = os.path.dirname(self.current_dir)
            if self.current_dir != parent:
                self.entries.append(("..  (parent directory)", parent, "dir"))

            for entry in entries:
                full_path = os.path.join(self.current_dir, entry)
                try:
                    if os.path.isdir(full_path):
                        self.entries.append((entry, full_path, "dir"))
                    elif entry.lower().endswith(VIDEO_EXT):
                        try:
                            size = self._format_size(os.path.getsize(full_path))
                        except OSError:
                            size = ""
                        self.entries.append((f"{entry}  [{size}]", full_path, "video"))
                    elif entry.lower().endswith(IMAGE_EXT):
                        try:
                            size = self._format_size(os.path.getsize(full_path))
                        except OSError:
                            size = ""
                        self.entries.append((f"{entry}  [{size}]", full_path, "image"))
                    elif entry.lower().endswith(LYRICS_EXT):
                        self.entries.append((entry, full_path, "lyrics"))
                except OSError:
                    continue
        except PermissionError:
            self.entries.append(("  (access denied)", "", "dir"))

        self._cursor = 0
        self._render_list()

        short = self.current_dir
        home = os.path.expanduser("~")
        if short.startswith(home):
            short = "~" + short[len(home):]
        self.query_one("#current-dir").update(f"FILES  --  {short}")

    def _render_list(self):
        lv = self._list_view()
        lv.clear()
        try:
            lv.index = 0
        except Exception:
            pass
        for name, path, kind in self.entries:
            if kind == "dir":
                line = f"[bold]{name}/[/bold]" if name != ".." else f"[dim]{name}[/dim]"
            elif kind == "video":
                line = f"{name}"
            elif kind == "image":
                line = f"[magenta]{name}[/magenta]"
            else:
                line = f"[cyan]{name}[/cyan]"
            self._seq += 1
            item = ListItem(Static(line, classes=f"file-item {kind}"), id=f"file-{self._seq}")
            item.data_kind = kind
            item.data_path = path
            lv.append(item)
        if not self.entries:
            self._seq += 1
            lv.append(
                ListItem(
                    Static("  (empty folder)", classes="file-item"),
                    id=f"file-{self._seq}",
                )
            )
        self._cursor = 0
        self._list_view().index = 0

    @on(ListView.Highlighted, "#file-list")
    def _on_highlighted(self, event: ListView.Highlighted):
        if self.entries:
            self._cursor = event.list_view.index or 0

    def _activate(self):
        if not self.entries:
            return
        item = self._cursor_item()
        if item is None:
            return
        path = getattr(item, "data_path", "")
        kind = getattr(item, "data_kind", "dir")
        if not path:
            return
        if kind == "dir":
            self.current_dir = path
            self.refresh_files()
        else:
            self.app.select_file(path, kind)

    def _cursor_item(self):
        lv = self._list_view()
        try:
            return lv.children[lv.index or 0]
        except (IndexError, TypeError):
            return None

    @on(ListView.Selected, "#file-list")
    def _on_selected(self, event: ListView.Selected):
        event.stop()
        self._activate()

    def on_mouse_scroll_down(self, event):
        """Scroll file list down."""
        lv = self._list_view()
        if lv:
            lv.action_scroll_down()
            event.stop()

    def on_mouse_scroll_up(self, event):
        """Scroll file list up."""
        lv = self._list_view()
        if lv:
            lv.action_scroll_up()
            event.stop()

    def on_button_pressed(self, event):
        if event.button.id == "btn-up":
            self.current_dir = os.path.dirname(self.current_dir)
            self.refresh_files()
        elif event.button.id == "btn-home":
            self.current_dir = os.path.expanduser("~")
            self.refresh_files()
        elif event.button.id == "btn-refresh":
            self.refresh_files()

    def on_key(self, event: Key):
        if event.key in ("up", "down"):
            if self.app.focused is not self._list_view():
                self._list_view().focus()
        elif event.key == "space":
            item = self._cursor_item()
            if item:
                path = getattr(item, "data_path", "")
                kind = getattr(item, "data_kind", "dir")
                if path and kind in ("video", "image"):
                    self.app.toggle_playlist_item(path, kind)
                    event.stop()
        elif event.key == "backspace":
            if not (self.app.focused and self.app.focused.id in ("dir-input",)):
                self.current_dir = os.path.dirname(self.current_dir)
                self.refresh_files()
                event.stop()
        elif event.key == "home" and self.app.focused is self._list_view():
            if self.entries:
                self._list_view().index = 0
                event.stop()
        elif event.key == "end" and self.app.focused is self._list_view():
            if self.entries:
                self._list_view().index = len(self.entries) - 1
                event.stop()

    @on(Input.Submitted, "#dir-input")
    def on_dir_input_submitted(self, event):
        raw = event.input.value.strip()
        expanded = os.path.expanduser(raw)
        log = self.app.query_one("#log")
        if os.path.isdir(expanded):
            self.current_dir = os.path.abspath(expanded)
            self.refresh_files()
            log.write(f"[dim]Changed directory: {self.current_dir}[/dim]")
        elif os.path.isfile(expanded):
            ext = os.path.splitext(expanded)[1].lower()
            if ext in LYRICS_EXT:
                self.app.select_file(expanded, "lyrics")
            elif ext in IMAGE_EXT:
                self.app.select_file(expanded, "image")
            else:
                self.app.select_file(expanded, "video")
                log.write("  Type the folder path and press Enter to jump there.")
        else:
            log.write(f"[yellow]Not a valid path: {raw}[/yellow]")

    def _format_size(self, size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class SettingsPanel(Static):
    """Extended settings with width, preset, color, audio, fps, export, lyrics."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="settings-inner"):
            yield Label("SETTINGS", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Label("Width:", classes="setting-label")
                yield Input(value="80", id="input-width", type="integer", classes="setting-input")
            with Horizontal(classes="setting-row"):
                yield Label("Preset:", classes="setting-label")
                yield Select(
                    [(name, name) for name in ASCII_PRESETS.keys()],
                    value="classic",
                    id="select-preset",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Color:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-color",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Audio:", classes="setting-label")
                yield Select(
                    [("On", True), ("Off", False)],
                    value=True,
                    id="select-audio",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("FPS:", classes="setting-label")
                yield Input(
                    value="",
                    id="input-fps",
                    type="integer",
                    classes="setting-input",
                    placeholder="auto",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Export:", classes="setting-label")
                yield Select(
                    [("Off", "none"), ("GIF", "gif"), ("MP4", "mp4")],
                    value="none",
                    id="select-export",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Output:", classes="setting-label")
                yield Input(
                    value="",
                    id="input-output",
                    classes="setting-input",
                    placeholder="(optional) export filename",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Lyrics:", classes="setting-label")
                yield Select(
                    [("Auto", "auto"), ("Split", "split"), ("Fullscreen", "fullscreen")],
                    value="auto",
                    id="select-lyrics",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Cache:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-cache",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Anim:", classes="setting-label")
                yield Select(
                    [(name, name) for name in ("none", "decode", "type", "rain")],
                    value="decode",
                    id="select-animate",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Dither:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-dither",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Invert:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-invert",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Loop:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-loop",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Crop:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-crop",
                    classes="setting-select",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Aspect:", classes="setting-label")
                yield Input(value="0.55", id="input-aspect", classes="setting-input")

    def collect(self):
        """Return a dict of current settings."""
        return {
            "width": self.query_one("#input-width").value,
            "preset": (self.query_one("#select-preset").value or ""),
            "color": bool(self.query_one("#select-color").value),
            "audio": bool(self.query_one("#select-audio").value),
            "fps": self.query_one("#input-fps").value,
            "export": (self.query_one("#select-export").value or "none"),
            "output": self.query_one("#input-output").value,
            "lyrics": (self.query_one("#select-lyrics").value or "auto"),
            "cache": bool(self.query_one("#select-cache").value),
            "animate": (self.query_one("#select-animate").value or "decode"),
            "dither": bool(self.query_one("#select-dither").value),
            "invert": bool(self.query_one("#select-invert").value),
            "loop": bool(self.query_one("#select-loop").value),
            "crop": bool(self.query_one("#select-crop").value),
            "aspect": self.query_one("#input-aspect").value,
        }

    def load_from_config(self, cfg):
        """Populate the panel from a persistence dict (keys may be missing)."""
        self.query_one("#input-width").value = str(cfg.get("width", 80))
        preset = cfg.get("preset", "classic")
        if preset in ASCII_PRESETS:
            self.query_one("#select-preset").value = preset
        self.query_one("#select-color").value = bool(cfg.get("color", False))
        self.query_one("#select-audio").value = bool(cfg.get("audio", True))
        fps = cfg.get("fps")
        self.query_one("#input-fps").value = str(int(fps)) if fps else ""
        export = cfg.get("export", "none")
        if export in ("gif", "mp4"):
            self.query_one("#select-export").value = export
        self.query_one("#input-output").value = str(cfg.get("output", "") or "")
        lyrics = cfg.get("lyrics", "auto")
        if lyrics in ("auto", "split", "fullscreen"):
            self.query_one("#select-lyrics").value = lyrics
        self.query_one("#select-cache").value = bool(cfg.get("cache", False))
        animate = cfg.get("animate", "decode")
        if animate in ("none", "decode", "type", "rain"):
            self.query_one("#select-animate").value = animate
        self.query_one("#select-dither").value = bool(cfg.get("dither", False))
        self.query_one("#select-invert").value = bool(cfg.get("invert", False))
        self.query_one("#select-loop").value = bool(cfg.get("loop", False))
        self.query_one("#select-crop").value = bool(cfg.get("crop", False))
        aspect = cfg.get("aspect", 0.55)
        try:
            self.query_one("#input-aspect").value = str(float(aspect))
        except (TypeError, ValueError):
            self.query_one("#input-aspect").value = "0.55"


class RecentList(Static):
    """Quick-access list of recently played items."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.recent = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("RECENT", id="recent-title")
            yield ListView(id="recent-list", classes="recent-list")

    def on_mount(self):
        self.refresh_recent()

    def refresh_recent(self):
        self.recent = _load_recent()
        self._recent_seq = getattr(self, "_recent_seq", 0) + 1
        lv = self.query_one("#recent-list", ListView)
        lv.clear()
        for path in self.recent:
            name = os.path.basename(path.rstrip("/\\")) or path
            self._recent_seq += 1
            item = ListItem(Static(name, classes="recent-item"), id=f"recent-{self._recent_seq}")
            item.data_path = path
            lv.append(item)
        if not self.recent:
            self._recent_seq += 1
            lv.append(
                ListItem(
                    Static("(empty)", classes="recent-item"),
                    id=f"recent-{self._recent_seq}",
                )
            )
        try:
            if lv.children:
                lv.index = 0
        except Exception:
            pass

    @on(ListView.Selected, "#recent-list")
    def on_recent_selected(self, event):
        item = event.item
        path = getattr(item, "data_path", None)
        if path:
            kind = "image" if (is_image_file(path) or is_image_url(str(path))) else "video"
            self.app.select_file(path, kind)


class CommandPreview(Static):
    """Live preview of the command that would be launched."""

    def compose(self) -> ComposeResult:
        yield Label("COMMAND", classes="section-title")
        yield Static("", id="cmd-preview", classes="cmd-preview")

    def show(self, text):
        self.query_one("#cmd-preview").update(text or "(nothing ready to play)")


class InlinePreview(Static):
    """Inline ASCII preview of the selected video or image frame."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="preview-inner"):
            yield Label("PREVIEW", classes="section-title")
            yield Static(
                "Select a video to see an ASCII preview here.",
                id="preview-body",
                classes="preview-body",
                markup=False,
            )

    def show_message(self, text):
        self.query_one("#preview-body").update(text)

    def show_frame(self, ascii_lines):
        if not ascii_lines:
            self.show_message("(no frame)")
            return
        self.query_one("#preview-body").update("\n".join(ascii_lines))


class StatusBar(Static):
    """Bottom status bar showing state, key hints, and version."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("Ready", id="status-text"),
            Static("", id="key-hints"),
            Static(f"v{__version__}", id="version-text"),
        )
