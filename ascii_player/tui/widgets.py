"""TUI widgets for ASCII Art Studio & Video Player."""

import os
from typing import Optional, Tuple

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.events import Key
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    OptionList,
    Select,
    Static,
)

from .. import __version__
from ..config import ASCII_PRESETS, FILTER_MODES, POST_FX_MODES
from ..images import (
    IMAGE_EXT,
    AsciiGrid,
    ansi_to_content,
    grid_to_content,
    is_image_file,
    is_image_url,
)
from ..prompt_gen import STARTER_PROMPTS, available_banner_fonts
from .helpers import LYRICS_EXT, VIDEO_EXT, _load_recent

_TYPE_TAGS = {
    "dir": "[D]",
    "video": "[V]",
    "image": "[I]",
    "lyrics": "[L]",
}


def _queued_marker(app, path: str) -> str:
    """Non-color marker shown on rows already in the playback queue."""
    playlist = getattr(app, "_playlist", ()) or ()
    return "✓ " if any(item.get("path") == path for item in playlist) else ""


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
                yield Button(
                    "Clear", id="btn-clear-pl", compact=True, tooltip="Empty the queue"
                )
                yield Button(
                    "Prev",
                    id="btn-prev-pl",
                    compact=True,
                    tooltip="Play the previous queued item (Ctrl+Left)",
                )
                yield Button(
                    "Next",
                    id="btn-next-pl",
                    compact=True,
                    tooltip="Play the next queued item (Ctrl+Right)",
                )

    def refresh_playlist(self, playlist, index):
        lv = self.query_one("#playlist-list", ListView)
        lv.clear()
        for i, item in enumerate(playlist):
            name = os.path.basename(item["path"])
            prefix = "> " if i == index else "  "
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
        self.entries = []
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
                    compact=True,
                )
            yield ListView(id="file-list", classes="file-list")
            with Horizontal(classes="browser-buttons"):
                yield Button("Up", id="btn-up", compact=True, tooltip="Parent folder (Backspace)")
                yield Button(
                    "Home",
                    id="btn-home",
                    compact=True,
                    tooltip="Jump to your home folder",
                )
                yield Button(
                    "Refresh", id="btn-refresh", compact=True, tooltip="Re-read this folder"
                )
                yield Button(
                    "Paste",
                    id="btn-paste",
                    compact=True,
                    tooltip="Paste an image or URL from the clipboard (Ctrl+V)",
                )
                yield Button(
                    "Browse", id="btn-browse", compact=True, tooltip="Open the file picker"
                )

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
            tag = _TYPE_TAGS.get(kind, "")
            marker = _queued_marker(self.app, path)
            if kind == "dir":
                if name == "..  (parent directory)":
                    line = f"{tag} {marker}[dim]{escape(name)}[/dim]"
                else:
                    line = f"{tag} {marker}[bold]{escape(name)}/[/bold]"
            elif kind == "video":
                line = f"{tag} {marker}{escape(name)}"
            elif kind == "image":
                line = f"{tag} {marker}[magenta]{escape(name)}[/magenta]"
            else:
                line = f"{tag} {marker}[cyan]{escape(name)}[/cyan]"
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
        app = self.app
        if os.path.isdir(expanded):
            self.current_dir = os.path.abspath(expanded)
            self.refresh_files()
            app._log_line("dim", f"Changed directory: {self.current_dir}")
        elif os.path.isfile(expanded):
            ext = os.path.splitext(expanded)[1].lower()
            if ext in LYRICS_EXT:
                app.select_file(expanded, "lyrics")
            elif ext in IMAGE_EXT:
                app.select_file(expanded, "image")
            else:
                app.select_file(expanded, "video")
            app._log_line("green", f"Loaded file: {os.path.basename(expanded)}")
        else:
            app._report_error(f"Not a valid path: {raw}", tag="OPEN")

    def _format_size(self, size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class PromptPanel(Static):
    """Prompt-to-ASCII studio panel supporting AI, Web, Ollama, FIGlet, and Procedural."""

    def compose(self) -> ComposeResult:
        fonts = available_banner_fonts()
        default_font = "slant" if "slant" in fonts else fonts[0]
        with Vertical():
            yield Label("PROMPT TO ASCII", classes="section-title")
            yield Input(
                placeholder="Describe anything (e.g. cyberpunk cat)...",
                id="prompt-input",
                compact=True,
            )
            with Horizontal(classes="compact-row"):
                yield Label("Engine:", classes="compact-label")
                yield Select(
                    [
                        ("Auto", "auto"),
                        ("AI Image", "ai"),
                        ("Web Image", "web"),
                        ("Ollama (Local)", "ollama"),
                        ("Banner (FIGlet)", "banner"),
                        ("Procedural", "procedural"),
                    ],
                    value="auto",
                    id="select-prompt-engine",
                    allow_blank=False,
                    compact=True,
                    classes="compact-control",
                )
            with Horizontal(classes="compact-row"):
                yield Label("Font:", classes="compact-label")
                yield Select(
                    [(f, f) for f in fonts],
                    value=default_font,
                    id="select-banner-font",
                    allow_blank=False,
                    compact=True,
                    classes="compact-control",
                )
            with Horizontal(classes="action-row"):
                yield Button("Generate", id="btn-generate", variant="primary", compact=True)
                yield Button("Surprise", id="btn-surprise", compact=True)
            yield Static("[READY] Enter prompt + press Enter", id="prompt-status")
            yield Label("PRESETS", classes="section-title")
            yield ListView(id="prompt-presets")

    def on_mount(self):
        lv = self.query_one("#prompt-presets", ListView)
        for idx, prompt in enumerate(STARTER_PROMPTS):
            item = ListItem(Static(f"  {prompt}"), id=f"preset-prompt-{idx}")
            item.data_prompt = prompt
            lv.append(item)


class UrlPanel(Static):
    """Universal URL loader panel (PNG/JPG/GIF, webpage og:image, YouTube)."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("URL TO ASCII", classes="section-title")
            yield Input(
                placeholder="PNG/JPG, webpage, or YouTube URL...",
                id="url-input",
                compact=True,
            )
            with Horizontal(classes="action-row"):
                yield Button("Load", id="btn-load-url", variant="primary", compact=True)
                yield Button("Play URL", id="btn-play-url", compact=True)
                yield Button("Paste", id="btn-paste-url", compact=True)
            yield Static(
                "Supports direct images, webpages (extracts og:image), "
                "GIFs, and YouTube videos.",
                id="url-info",
            )


class WebcamPanel(Static):
    """Live inline ASCII webcam & snapshot controller."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("LIVE WEBCAM", classes="section-title")
            with Horizontal(classes="compact-row"):
                yield Label("Cam #:", classes="compact-label")
                yield Input(
                    value="0",
                    id="input-camera",
                    type="integer",
                    compact=True,
                    classes="compact-control",
                )
            with Horizontal(classes="compact-row"):
                yield Label("Filter:", classes="compact-label")
                yield Select(
                    [(f, f) for f in ("none", "mirror", "edge", "invert", "colorcycle")],
                    value="none",
                    id="select-cam-filter",
                    allow_blank=False,
                    compact=True,
                    classes="compact-control",
                )
            with Vertical(classes="cam-buttons"):
                yield Button("Start Live Cam", id="btn-cam-toggle", variant="success", compact=True)
                yield Button("Freeze Snapshot", id="btn-cam-snap", compact=True)
                yield Button("Pop-out Cam", id="btn-webcam", compact=True)
            yield Static("[IDLE] Camera stopped", id="cam-stats")


class SettingsPanel(Static):
    """Compact Style & Output Inspector with live reactive controls."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="settings-inner"):
            yield Label("STYLE", classes="group-title")
            with Horizontal(classes="toggle-row"):
                yield Checkbox(
                    "Auto-fit",
                    value=True,
                    id="check-autofit",
                    compact=True,
                    tooltip="Fit the canvas to the viewport (0 to toggle)",
                )
            with Horizontal(classes="toggle-row"):
                yield Checkbox(
                    "Color (RGB)",
                    value=False,
                    id="select-color",
                    compact=True,
                    tooltip="Render/copy/export with ANSI TrueColor instead of monochrome",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Width:", classes="setting-label")
                yield Input(
                    value="80",
                    id="input-width",
                    type="integer",
                    classes="setting-input",
                    compact=True,
                    tooltip="Fixed canvas width in columns (ignored while Auto-fit is on)",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Preset:", classes="setting-label")
                yield Select(
                    [(name, name) for name in ASCII_PRESETS.keys()],
                    value="classic",
                    id="select-preset",
                    allow_blank=False,
                    classes="setting-select",
                    compact=True,
                    tooltip="Character ramp / pixel density preset",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Chars:", classes="setting-label")
                yield Input(
                    value="",
                    id="input-charset",
                    placeholder="custom ramp",
                    classes="setting-input",
                    compact=True,
                    tooltip="Override the preset with a custom dark-to-light character ramp",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Aspect:", classes="setting-label")
                yield Input(
                    value="0.55",
                    id="input-aspect",
                    classes="setting-input",
                    compact=True,
                    tooltip="Character aspect correction (0.2 - 2.0)",
                )

            yield Label("IMAGE & FX", classes="group-title")
            with Horizontal(classes="setting-row"):
                yield Label("Filter:", classes="setting-label")
                yield Select(
                    [(mode, mode) for mode in FILTER_MODES],
                    value="none",
                    id="select-filter",
                    allow_blank=False,
                    classes="setting-select",
                    compact=True,
                    tooltip="Edge / blur filter applied before ASCII conversion",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Contrast:", classes="setting-label")
                yield Input(
                    value="1.0",
                    id="input-contrast",
                    classes="setting-input",
                    compact=True,
                    tooltip="Contrast multiplier (0.2 - 3.5)",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Bright:", classes="setting-label")
                yield Input(
                    value="1.0",
                    id="input-brightness",
                    classes="setting-input",
                    compact=True,
                    tooltip="Brightness multiplier (0.2 - 3.0)",
                )
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Dither",
                    value=False,
                    id="select-dither",
                    compact=True,
                    tooltip="Use error-diffusion dithering",
                )
                yield Checkbox(
                    "Invert",
                    value=False,
                    id="select-invert",
                    compact=True,
                    tooltip="Invert image brightness",
                )
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Crop",
                    value=False,
                    id="select-crop",
                    compact=True,
                    tooltip="Crop to the canvas instead of stretching",
                )
                yield Checkbox(
                    "Loop",
                    value=False,
                    id="select-loop",
                    compact=True,
                    tooltip="Loop animated GIF / video playback",
                )

            yield Label("POST-FX (STACKABLE)", classes="group-title")
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Scanlines",
                    value=False,
                    id="fx-scanlines",
                    compact=True,
                    tooltip="Overlay CRT scanlines",
                )
                yield Checkbox(
                    "Chromatic",
                    value=False,
                    id="fx-chromatic",
                    compact=True,
                    tooltip="Offset color channels (chromatic aberration)",
                )
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Vignette",
                    value=False,
                    id="fx-vignette",
                    compact=True,
                    tooltip="Darken the edges",
                )
                yield Checkbox(
                    "Bloom",
                    value=False,
                    id="fx-bloom",
                    compact=True,
                    tooltip="Glow around bright characters",
                )
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Halftone",
                    value=False,
                    id="fx-halftone",
                    compact=True,
                    tooltip="Halftone dot pattern",
                )
                yield Checkbox(
                    "Glitch",
                    value=False,
                    id="fx-glitch",
                    compact=True,
                    tooltip="Digital glitch distortion",
                )

            with Horizontal(classes="setting-row"):
                yield Label("Anim:", classes="setting-label")
                yield Select(
                    [(name, name) for name in ("none", "decode", "type", "rain")],
                    value="decode",
                    id="select-animate",
                    allow_blank=False,
                    classes="setting-select",
                    compact=True,
                    tooltip="Reveal animation for newly rendered art",
                )

            yield Label("PLAYBACK & EXPORT", classes="group-title")
            with Horizontal(classes="setting-row"):
                yield Label("FPS:", classes="setting-label")
                yield Input(
                    value="",
                    id="input-fps",
                    type="integer",
                    classes="setting-input",
                    placeholder="auto",
                    compact=True,
                    tooltip="Frame rate for pop-out video playback (blank = auto)",
                )
            with Horizontal(classes="toggle-grid"):
                yield Checkbox(
                    "Audio",
                    value=True,
                    id="select-audio",
                    compact=True,
                    tooltip="Play audio in pop-out playback",
                )
                yield Checkbox(
                    "Cache",
                    value=False,
                    id="select-cache",
                    compact=True,
                    tooltip="Cache decoded frames on disk",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Lyrics:", classes="setting-label")
                yield Select(
                    [("Auto", "auto"), ("Split", "split"), ("Fullscreen", "fullscreen")],
                    value="auto",
                    id="select-lyrics",
                    allow_blank=False,
                    classes="setting-select",
                    compact=True,
                    tooltip="Lyrics display mode for pop-out playback",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Export:", classes="setting-label")
                yield Select(
                    [
                        ("Off", "none"),
                        ("TXT", "txt"),
                        ("ANS", "ans"),
                        ("HTML", "html"),
                        ("PNG", "png"),
                        ("GIF", "gif"),
                        ("MP4 (CLI / pop-out only)", "mp4"),
                    ],
                    value="none",
                    id="select-export",
                    allow_blank=False,
                    classes="setting-select",
                    compact=True,
                    tooltip="MP4 is a CLI / pop-out feature; Ctrl+E exports images/text only.",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Output:", classes="setting-label")
                yield Input(
                    value="",
                    id="input-output",
                    classes="setting-input",
                    placeholder="output filename",
                    compact=True,
                    tooltip="Default export filename stem",
                )

    def collect(self):
        """Return a dict of current settings."""
        post_fx = [
            mode for mode in POST_FX_MODES if bool(self.query_one(f"#fx-{mode}").value)
        ]
        return {
            "width": self.query_one("#input-width").value,
            "preset": (self.query_one("#select-preset").value or "classic"),
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
            "auto_fit": bool(self.query_one("#check-autofit").value),
            "filter": (self.query_one("#select-filter").value or "none"),
            "contrast": self.query_one("#input-contrast").value,
            "brightness": self.query_one("#input-brightness").value,
            "charset": self.query_one("#input-charset").value,
            "post_fx": post_fx,
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
        if export in ("txt", "ans", "html", "png", "gif", "mp4"):
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

        if "auto_fit" in cfg:
            self.query_one("#check-autofit").value = bool(cfg["auto_fit"])
        filter_mode = cfg.get("filter", "none")
        if filter_mode in FILTER_MODES:
            self.query_one("#select-filter").value = filter_mode
        try:
            self.query_one("#input-contrast").value = str(float(cfg.get("contrast", 1.0)))
        except (TypeError, ValueError):
            self.query_one("#input-contrast").value = "1.0"
        try:
            self.query_one("#input-brightness").value = str(float(cfg.get("brightness", 1.0)))
        except (TypeError, ValueError):
            self.query_one("#input-brightness").value = "1.0"
        self.query_one("#input-charset").value = str(cfg.get("charset", "") or "")
        active_fx = {str(fx).strip().lower() for fx in (cfg.get("post_fx") or ())}
        for mode in POST_FX_MODES:
            self.query_one(f"#fx-{mode}").value = mode in active_fx


class RecentList(Static):
    """Quick-access list of recently played/loaded items."""

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
            marker = _queued_marker(self.app, path)
            self._recent_seq += 1
            item = ListItem(
                Static(f"{marker}{escape(name)}", classes="recent-item"),
                id=f"recent-{self._recent_seq}",
            )
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
            if str(path).lower().startswith(("http://", "https://", "www.")):
                self.app.load_url_source(str(path))
            else:
                kind = "image" if (is_image_file(path) or is_image_url(str(path))) else "video"
                self.app.select_file(path, kind)


class CommandPreview(Static):
    """Live preview of the CLI command that would be launched."""

    def compose(self) -> ComposeResult:
        yield Label("COMMAND", classes="group-title")
        preview = Static("", id="cmd-preview", classes="cmd-preview")
        # Static has no tooltip constructor argument in Textual; the property
        # is assignable after construction.
        preview.tooltip = "Exact CLI command used by pop-out playback and export"
        yield preview

    def show(self, text):
        self.query_one("#cmd-preview").update(text or "(nothing ready to play)")


class InlinePreview(Static):
    """Scrollable full-viewport TrueColor ASCII Art Canvas."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="art-bar"):
            yield Static("", id="art-bar-spacer")
            yield Button(
                "fit",
                id="btn-autofit",
                classes="chip",
                compact=True,
                tooltip="Auto-fit the canvas to the viewport (0)",
            )
            yield Button(
                "type over",
                id="btn-edit-in-draw",
                classes="chip",
                compact=True,
                tooltip="Import this art into the Type canvas (Ctrl+D)",
            )
            yield Button(
                "copy",
                id="btn-copy-ascii",
                classes="chip",
                compact=True,
                tooltip="Copy visible ASCII to clipboard (Ctrl+Y)",
            )
            yield Button(
                "save",
                id="btn-export-now",
                classes="chip",
                compact=True,
                tooltip="Export PNG / HTML / ANSI / TXT / GIF (Ctrl+E)",
            )
        with ScrollableContainer(id="canvas-scroll"):
            yield Static(
                "Select a file, type a prompt, paste a URL, or start webcam.",
                id="preview-body",
                classes="preview-body",
                markup=False,
            )

    def viewport_size(self) -> Tuple[int, int]:
        """Return usable character columns and rows of the canvas viewport."""
        try:
            scroll = self.query_one("#canvas-scroll", ScrollableContainer)
            cw = int(scroll.content_size.width or scroll.size.width or 0)
            ch = int(scroll.content_size.height or scroll.size.height or 0)
            if cw <= 0 or ch <= 0:
                stage = self.app.query_one("#stage")
                cw = int(stage.size.width or self.app.size.width or 80)
                ch = int(stage.size.height or max(10, self.app.size.height - 8) or 24)
            return max(24, cw - 2), max(8, ch - 1)
        except Exception:
            return 80, 24

    def show_message(self, text):
        self.query_one("#preview-body", Static).update(text)

    def show_frame(self, ascii_lines):
        if not ascii_lines:
            self.show_message("(no frame)")
            return
        joined = "\n".join(ascii_lines)
        # Native Content avoids Textual re-parsing every ANSI style on each
        # reveal-animation / visualizer frame.
        renderable = ansi_to_content(joined)
        dims = (len(ascii_lines), len(ascii_lines[0]))
        layout = dims != getattr(self, "_last_grid_dims", None)
        self._last_grid_dims = dims
        self.query_one("#preview-body", Static).update(renderable, layout=layout)

    def show_grid(self, grid: AsciiGrid, color: bool = True):
        if grid is None:
            self.show_message("(no frame)")
            return
        # Native Content skips Textual's per-frame re-parse of Rich style
        # strings (the dominant cost of the old rich-Text path).
        renderable = grid_to_content(grid, color=color)
        # Only pay for a layout pass when the grid actually changed size.
        dims = (grid.width, grid.height)
        layout = dims != getattr(self, "_last_grid_dims", None)
        self._last_grid_dims = dims
        self.query_one("#preview-body", Static).update(renderable, layout=layout)


class StatusBar(Static):
    """Bottom status bar showing state, key hints, and version."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("Ready", id="status-text", markup=False),
            Static("", id="key-hints", markup=False),
            Static(f"v{__version__}", id="version-text", markup=False),
            id="status-bar",
        )


class StudioTopBar(Static):
    """Minimalist 1-line top bar with Studio | Type tabs."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("◆ ascii-studio", id="brand-mark", markup=False),
            Button(
                "Studio",
                id="btn-mode-studio",
                classes="mode-tab active",
                compact=True,
                tooltip="Studio canvas mode",
            ),
            Button(
                "Type",
                id="btn-mode-draw",
                classes="mode-tab",
                compact=True,
                tooltip="Pure-keyboard terminal ASCII mode (Ctrl+D)",
            ),
            Static("·  ready", id="canvas-meta", markup=False),
            Button(
                "mono",
                id="btn-color-toggle",
                classes="chip",
                compact=True,
                tooltip="Toggle TrueColor / monochrome output",
            ),
            Button(
                "files ^O",
                id="btn-toggle-files",
                classes="chip",
                compact=True,
                tooltip="Open the Files drawer (Ctrl+O)",
            ),
            Button(
                "style ^B",
                id="btn-toggle-style",
                classes="chip",
                compact=True,
                tooltip="Open the Style Inspector (Ctrl+B)",
            ),
            Button(
                "^K",
                id="btn-open-palette",
                classes="chip accent-chip",
                compact=True,
                tooltip="Open the command palette (Ctrl+K)",
            ),
            Button(
                "^P help",
                id="btn-help",
                classes="chip",
                compact=True,
                tooltip="Show keyboard shortcuts and commands (Ctrl+P)",
            ),
            Button(
                "^L log",
                id="btn-log-top",
                classes="chip",
                compact=True,
                tooltip="Show / hide the detailed activity log (Ctrl+L)",
            ),
            id="topbar-row",
        )


_HERO_PALETTES = {
    "amber": ((245, 158, 11), (244, 114, 182), (167, 139, 250)),
    "sand": ((217, 119, 87), (245, 158, 11), (245, 240, 235)),
    "dark": ((88, 166, 255), (129, 140, 248), (192, 132, 252)),
    "retro": ((255, 176, 0), (255, 120, 0), (255, 228, 163)),
    "steins_gate": ((255, 140, 36), (96, 165, 250), (56, 189, 248)),
    "light": ((37, 99, 235), (79, 70, 229), (147, 51, 234)),
    "high_contrast": ((0, 255, 102), (0, 229, 255), (255, 255, 255)),
}


def render_gradient_logo(wordmark: str, theme_name: str = "amber", phase: float = 0.0):
    """Render the welcome ASCII wordmark with a smooth TrueColor gradient."""
    import math

    from rich.text import Text

    c0, c1, c2 = _HERO_PALETTES.get(theme_name, _HERO_PALETTES["amber"])
    lines = wordmark.splitlines()
    width = max((len(line) for line in lines), default=1) or 1
    out = Text(no_wrap=True)
    for r_idx, line in enumerate(lines):
        for c_idx, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
                continue
            pos = (c_idx / max(1, width - 1) + math.sin(phase + r_idx * 0.35) * 0.12) % 1.0
            if pos < 0.5:
                t = pos * 2.0
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
            else:
                t = (pos - 0.5) * 2.0
                r = int(c1[0] + (c2[0] - c1[0]) * t)
                g = int(c1[1] + (c2[1] - c1[1]) * t)
                b = int(c1[2] + (c2[2] - c1[2]) * t)
            out.append(ch, style=f"bold rgb({r},{g},{b})")
        if r_idx < len(lines) - 1:
            out.append("\n")
    return out


class WelcomeHero(Static):
    """Centered welcome screen shown when canvas is idle."""

    _WORDMARK = (
        " █████╗ ███████╗ ██████╗██╗██╗    ███████╗████████╗██╗   ██╗██████╗ ██╗ ██████╗ \n"
        "██╔══██╗██╔════╝██╔════╝██║██║    ██╔════╝╚══██╔══╝██║   ██║██╔══██╗██║██╔═══██╗\n"
        "███████║███████╗██║     ██║██║    ███████╗   ██║   ██║   ██║██║  ██║██║██║   ██║\n"
        "██╔══██║╚════██║██║     ██║██║    ╚════██║   ██║   ██║   ██║██║  ██║██║██║   ██║\n"
        "██║  ██║███████║╚██████╗██║██║    ███████║   ██║   ╚██████╔╝██████╔╝██║╚██████╔╝\n"
        "╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚═╝    ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝ "
    )

    _COMPACT_WORDMARK = (
        "▄▀█ █▀ █▀▀ █ █   █▀ ▀█▀ █ █ █▀▄ █ █▀█\n"
        "█▀█ ▄█ █▄▄ █ █   ▄█  █  █▄█ █▄▀ █ █▄█"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._compact: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-inner"):
            yield Static(render_gradient_logo(self._WORDMARK), id="welcome-logo")
            yield Static(
                "png  ·  prompt  ·  url  ·  webcam  ·  terminal type",
                id="welcome-tagline",
            )
            with Vertical(id="welcome-guide"):
                yield Static(
                    "  type text       generate ascii art from any prompt\n"
                    "  path / Ctrl+V   load png, jpg, gif, mp4 or clipboard\n"
                    "  paste url       image, webpage og:image, or youtube\n"
                    "  /webcam · ^D    live ascii cam / typing · ^Q quit\n"
                    "  /fx · /preset   HD halfblock, braille_hd & stackable FX\n"
                    "  Tab / Esc · ↑↓  navigate drawers, autocomplete & omnibox",
                    id="welcome-tips",
                )
            with Horizontal(id="welcome-starters"):
                yield Button(
                    "samurai cat",
                    id="btn-hero-1",
                    classes="starter-chip",
                    compact=True,
                )
                yield Button(
                    "mount fuji",
                    id="btn-hero-2",
                    classes="starter-chip",
                    compact=True,
                )
                yield Button(
                    "live webcam",
                    id="btn-hero-3",
                    classes="starter-chip",
                    compact=True,
                )
                yield Button(
                    "banner",
                    id="btn-hero-4",
                    classes="starter-chip",
                    compact=True,
                )
                yield Button(
                    "type skull (^D)",
                    id="btn-hero-draw",
                    classes="starter-chip accent-chip",
                    compact=True,
                )

    def update_logo(
        self, theme_name: str, phase: float = 0.0, compact: Optional[bool] = None
    ) -> None:
        if compact is not None:
            self._compact = compact
        wordmark = self._COMPACT_WORDMARK if self._compact else self._WORDMARK
        try:
            self.query_one("#welcome-logo", Static).update(
                render_gradient_logo(wordmark, theme_name=theme_name, phase=phase)
            )
        except Exception:
            pass


class OmniboxBar(Static):
    """Floating left-accent prompt card with live autocomplete popup."""

    def compose(self) -> ComposeResult:
        popup = OptionList(id="autocomplete-popup")
        popup.can_focus = False
        with Vertical(id="omnibox-shell"):
            yield Static("", id="activity-line", markup=False)
            with Vertical(id="autocomplete-box"):
                yield popup
                yield Static(
                    "↑↓ select · Tab complete · Enter run · Esc close",
                    id="autocomplete-hint",
                    markup=False,
                )
            with Vertical(id="omnibox-wrap"):
                with Horizontal(id="omnibox-input-row"):
                    yield Static("❯ ", id="omnibox-caret", markup=False)
                    yield Input(
                        placeholder=(
                            "Describe anything, paste a PNG path or URL, /command, or @file..."
                        ),
                        id="omnibox",
                        compact=True,
                    )
                with Horizontal(id="omnibox-meta"):
                    yield Static("", id="omnibox-pills", markup=False)
                    yield Button(
                        "amber",
                        id="btn-theme-pill",
                        classes="chip accent-chip",
                        compact=True,
                    )
