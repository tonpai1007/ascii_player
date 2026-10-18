"""Terminal User Interface for ASCII Video Player."""

import os
import re
import subprocess
import sys
from collections import OrderedDict

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
)

from . import __version__
from .config import ASCII_PRESETS
from .settings import load_config, save_config

PYTHON = sys.executable or "python"

try:
    import cv2
    _CV2_OK = True
except ImportError:
    cv2 = None
    _CV2_OK = False

try:
    from .core import frame_to_ascii
    _CORE_OK = True
except ImportError:
    frame_to_ascii = None
    _CORE_OK = False

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text):
    return _ANSI_RE.sub("", text)

VIDEO_EXT = (
    '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv',
    '.wmv', '.m4v', '.mpg', '.mpeg', '.3gp',
)
LYRICS_EXT = ('.lrc', '.srt', '.ass', '.ssa')

# Persist recent files across sessions.
RECENT_STORE = "ascii_player_recent.txt"
RECENT_LIMIT = 10


def is_url(text):
    return bool(re.match(r'https?://|www\.', text))


def _win_quote(arg):
    """Quote an argument for the Windows cmd shell.

    Always wraps in double quotes so cmd metacharacters like ``&``, ``|``,
    ``<``, ``>`` and ``^`` are treated literally instead of as operators.
    cmd expands ``%VAR%`` even inside double quotes, so a literal ``%`` is
    doubled to ``%%``.
    """
    s = str(arg)
    if "%" in s:
        s = s.replace("%", "%%")
    return f'"{s}"'


def launch_new_terminal(args):
    try:
        if sys.platform == "win32":
            quoted = " ".join(_win_quote(a) for a in args)
            subprocess.Popen(
                f'start "ASCII Player" /D {_win_quote(os.getcwd())} cmd /k {quoted}',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            script = 'tell application "Terminal" to do script "' + " ".join(args) + '"'
            subprocess.Popen(["osascript", "-e", script])
        else:
            for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]:
                try:
                    subprocess.Popen([term, "-e"] + args)
                    return True
                except FileNotFoundError:
                    continue
            return False
        return True
    except Exception:
        return False


def _load_recent():
    if not os.path.exists(RECENT_STORE):
        return []
    try:
        with open(RECENT_STORE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []


def _save_recent(recent, max_items=RECENT_LIMIT):
    recent = list(OrderedDict.fromkeys(recent))[:max_items]
    try:
        with open(RECENT_STORE, "w", encoding="utf-8") as f:
            f.write("\n".join(recent))
    except Exception:
        pass


def _auto_lyrics(video_path):
    """Look for a same-name sibling lyrics file next to the video."""
    from .lyrics import find_lyrics_file

    return find_lyrics_file(video_path)


class FileBrowser(Static):
    """Keyboard-navigable, list-based file browser."""

    def __init__(self, start_dir=".", **kwargs):
        super().__init__(**kwargs)
        self.current_dir = os.path.abspath(start_dir)
        self.entries = []          # list of (display, path, kind)
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
        for i, (name, path, kind) in enumerate(self.entries):
            if kind == "dir":
                line = f"[bold]{name}/[/bold]" if name != ".." else f"[dim]{name}[/dim]"
            elif kind == "video":
                line = f"{name}"
            else:
                line = f"[cyan]{name}[/cyan]"
            self._seq += 1
            item = ListItem(Static(line, classes=f"file-item {kind}"), id=f"file-{self._seq}")
            item.data_kind = kind
            item.data_path = path
            lv.append(item)
        if not self.entries:
            self._seq += 1
            lv.append(ListItem(
                Static("  (empty folder)", classes="file-item"),
                id=f"file-{self._seq}",
            ))
        # Track the highlighted item to keep our cursor in sync.
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
        if event.key == "up" or event.key == "down":
            # Direct the arrow keys toward the file list so browsing works from anywhere.
            if self.app.focused is not self._list_view():
                self._list_view().focus()
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
        if os.path.isdir(expanded):
            self.current_dir = os.path.abspath(expanded)
            self.refresh_files()
            self.query_one("#log").write(f"[dim]Changed directory: {self.current_dir}[/dim]")
        elif os.path.isfile(expanded):
            ext = os.path.splitext(expanded)[1].lower()
            if ext in LYRICS_EXT:
                self.app.select_file(expanded, "lyrics")
            else:
                self.app.select_file(expanded, "video")
                self.query_one("#log").write(
                    "  Type the folder path and press Enter to jump there."
                )
        else:
            self.query_one("#log").write(f"[yellow]Not a valid path: {raw}[/yellow]")

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == 'B' else f"{size:.1f}{unit}"
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
                    classes="setting-select"
                )
            with Horizontal(classes="setting-row"):
                yield Label("Color:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-color",
                    classes="setting-select"
                )
            with Horizontal(classes="setting-row"):
                yield Label("Audio:", classes="setting-label")
                yield Select(
                    [("On", True), ("Off", False)],
                    value=True,
                    id="select-audio",
                    classes="setting-select"
                )
            with Horizontal(classes="setting-row"):
                yield Label("FPS:", classes="setting-label")
                yield Input(value="", id="input-fps", type="integer", classes="setting-input",
                            placeholder="auto")
            with Horizontal(classes="setting-row"):
                yield Label("Export:", classes="setting-label")
                yield Select(
                    [("Off", "none"), ("GIF", "gif"), ("MP4", "mp4")],
                    value="none",
                    id="select-export",
                    classes="setting-select"
                )
            with Horizontal(classes="setting-row"):
                yield Label("Output:", classes="setting-label")
                yield Input(
                    value="", id="input-output", classes="setting-input",
                    placeholder="(optional) export filename",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Lyrics:", classes="setting-label")
                yield Select(
                    [("Auto", "auto"), ("Split", "split"), ("Fullscreen", "fullscreen")],
                    value="auto",
                    id="select-lyrics",
                    classes="setting-select"
                )
            with Horizontal(classes="setting-row"):
                yield Label("Cache:", classes="setting-label")
                yield Select(
                    [("Off", False), ("On", True)],
                    value=False,
                    id="select-cache",
                    classes="setting-select"
                )

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
            lv.append(ListItem(
                Static("(empty)", classes="recent-item"),
                id=f"recent-{self._recent_seq}",
            ))
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
            self.app.select_file(path, "video")


class CommandPreview(Static):
    """Live preview of the command that would be launched."""

    def compose(self) -> ComposeResult:
        yield Label("COMMAND", classes="section-title")
        yield Static("", id="cmd-preview", classes="cmd-preview")

    def show(self, text):
        self.query_one("#cmd-preview").update(text or "(nothing ready to play)")


class InlinePreview(Static):
    """Inline ASCII preview of the selected video's frame.

    Renders a representative frame through the same ASCII pipeline used for
    playback, giving immediate visual feedback for the chosen preset/width/color
    before launching the full player. Falls back to a short note if OpenCV or
    the core converter is unavailable.
    """

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
        # Plain text only -- the body disables markup so ASCII chars like
        # [ and ] in the detailed preset are never misparsed as tags.
        self.query_one("#preview-body").update(text)

    def show_frame(self, ascii_lines):
        if not ascii_lines:
            self.show_message("(no frame)")
            return
        self.query_one("#preview-body").update("\n".join(ascii_lines))


class StatusBar(Static):

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("Ready", id="status-text"),
            Static("", id="key-hints"),
            Static(f"v{__version__}", id="version-text"),
        )


class ASCIITuiApp(App):

    CSS = """
    Screen {
        layout: horizontal;
    }

    #sidebar {
        width: 40%;
        height: 100%;
        min-width: 44;
        border: tall $primary;
        padding: 1;
    }

    #main {
        width: 60%;
        height: 100%;
        padding: 1 1 1 0;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .url-bar {
        dock: top;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    .url-input {
        width: 1fr;
        margin-right: 1;
    }

    .play-url-btn {
        min-width: 14;
    }

    /* File browser */
    .dir-input-row {
        margin-bottom: 1;
    }

    .dir-input {
        width: 1fr;
    }

    #file-list {
        height: 1fr;
        border: round $primary-darken-1;
        margin-bottom: 1;
    }

    #file-list:focus {
        border: round $accent;
    }

    .file-item {
        padding: 0 1;
    }

    .file-item.video {
        color: $text;
    }

    .file-item.lyrics {
        color: $text-muted;
    }

    ListItem.selected {
        background: $accent;
        color: $text;
    }

    ListItem.selected .file-item {
        color: $text;
        text-style: bold;
    }

    #current-dir {
        text-style: bold;
        color: $accent;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .browser-buttons {
        margin-top: 1;
    }

    .browser-buttons Button {
        min-width: 9;
        margin-right: 1;
    }

    /* Recent */
    #recent-title {
        text-style: bold;
        color: $text-muted;
        margin-top: 1;
    }

    #recent-list {
        height: 6;
        border: hkey none;
    }

    .recent-item {
        padding: 0 1;
        color: $text-muted;
    }

    ListItem:hover {
        background: $primary-darken-2;
    }

    /* Selected file */
    #selected-file {
        text-style: bold;
        color: $success;
        margin: 1 0;
        padding: 0 1;
        min-height: 1;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Settings */
    .settings-inner {
        margin-top: 1;
    }

    .setting-row {
        height: auto;
        margin-bottom: 0;
    }

    .setting-label {
        width: 9;
        color: $text-muted;
    }

    .setting-input {
        width: 1fr;
    }

    .setting-select {
        width: 1fr;
    }

    /* Command preview */
    #cmd-preview {
        color: $text-muted;
        border: none;
        padding: 0;
        margin-top: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Inline preview */
    .preview-inner {
        height: auto;
    }

    #preview-body {
        max-height: 16;
        border: round $primary-darken-1;
        padding: 0 1 1 1;
        overflow-y: auto;
        color: $text;
        content-align: center middle;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #status-text {
        width: 1fr;
    }

    #key-hints {
        color: $text-muted;
        padding-right: 2;
    }

    #version-text {
        color: $text-muted;
    }

    .controls {
        dock: bottom;
        height: 3;
        padding: 1 0;
        margin-bottom: 1;
    }

    #btn-play {
        background: $success;
        color: $text;
        min-width: 14;
    }

    #btn-play:hover {
        background: $success-darken-1;
    }

    #btn-webcam {
        background: $warning;
        color: $text;
        min-width: 14;
    }

    #btn-webcam:hover {
        background: $warning-darken-1;
    }

    #btn-play-url {
        background: $accent;
        color: $text;
        min-width: 14;
    }

    #btn-play-url:hover {
        background: $accent-darken-1;
    }

    RichLog {
        height: 1fr;
        border: tall $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("p", "play", "Play"),
        Binding("w", "webcam", "Webcam"),
        Binding("g", "goto_path", "Go to path"),
        Binding("ctrl+l", "focus_log", "Log"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.selected_kind = None
        self._lyrics_auto = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="sidebar"):
            yield FileBrowser()
            yield Static("", id="selected-file")
            yield RecentList()

        with Container(id="main"):
            with Vertical():
                with Horizontal(classes="url-bar"):
                    yield Input(
                        placeholder="Paste YouTube URL or local file path, then press Enter...",
                        id="url-input",
                        classes="url-input",
                    )
                    yield Button("Play URL", id="btn-play-url", classes="play-url-btn")
                yield SettingsPanel()
                yield CommandPreview()

            with Horizontal(classes="controls"):
                yield Button("Play (P)", id="btn-play")
                yield Button("Webcam (W)", id="btn-webcam")

            yield InlinePreview()

            yield RichLog(id="log", highlight=True, markup=True)

        yield StatusBar()
        yield Footer()

    def on_mount(self):
        self.title = f"ASCII Video Player v{__version__}"
        self.sub_title = ""
        log = self.query_one("#log")
        log.write("[bold]How to use:[/bold]")
        log.write("")
        log.write("  [bold green]Option 1 -- Play a local file:[/bold green]")
        log.write("    1. Navigate with [Up]/[Down], jump with [Enter]")
        log.write("    2. [Enter] on a [VID] selects it, [Enter] again plays")
        log.write("")
        log.write("  [bold cyan]Option 2 -- Play a YouTube URL:[/bold cyan]")
        log.write("    1. Paste a link in the box above (Tab to reach it)")
        log.write("    2. Press Enter or click [Play URL]")
        log.write("")
        log.write("  [bold yellow]Option 3 -- Live webcam:[/bold yellow]")
        log.write("    Click [Webcam] or press W")
        log.write("")
        log.write("[dim][Backspace]=up dir  [G]=jump to path  [R]=refresh  [P]=play[/dim]")
        log.write(
            "[dim]A new terminal window opens with playback: "
            "Space=pause  Q=quit  +/-=speed[/dim]"
        )
        log.write("")
        log.write(
            "[dim]Settings on the left apply to the next playback; a live "
            "COMMAND preview shows what runs.[/dim]"
        )
        self.query_one("#url-input").focus()
        cfg = load_config()
        self.query_one(SettingsPanel).load_from_config(cfg)
        self._update_preview()
        self._update_key_hints()
        if cfg:
            log.write("")
            log.write("[dim]Loaded persisted settings from ascii_player.yaml.[/dim]")

    # ---- state helpers ----

    def _settings(self):
        return self.query_one(SettingsPanel).collect()

    def _selected_name(self):
        return os.path.basename(self.selected_file) if self.selected_file else None

    def _log(self):
        return self.query_one("#log")

    def _update_preview(self):
        s = self._settings()
        if self.selected_file:
            parts = [os.path.basename(self.selected_file)]
            parts.append(f"-w {s['width']}")
            if s["preset"]:
                parts.append(f"-p {s['preset']}")
            if s["color"]:
                parts.append("-c")
            if not s["audio"]:
                parts.append("--no-audio")
            if s["fps"]:
                parts.append(f"-f {s['fps']}")
            if s["export"] != "none":
                parts.append(f"--export {s['export']}")
                if (s.get("output") or "").strip():
                    parts.append(f"-o {s['output'].strip()}")
            if self._lyrics_auto and s["lyrics"] == "auto":
                parts.append(f"-l {os.path.basename(self._lyrics_auto)}")
            if s["cache"]:
                parts.append("--cache")
            self.query_one(CommandPreview).show("ascii-player " + " ".join(parts))
        else:
            self.query_one(CommandPreview).show("(nothing ready to play)")

    def _refresh_inline_preview(self):
        """Render a representative ASCII frame of the selected local video."""
        panel = self.query_one(InlinePreview)
        path = self.selected_file
        if not path or not os.path.isfile(path):
            panel.show_message("Select a video to see an ASCII preview here.")
            return
        if not _CV2_OK:
            panel.show_message("Preview needs OpenCV (opencv-python) to render frames inline.")
            return

        s = self._settings()
        try:
            width = int(s["width"]) if str(s["width"]).isdigit() else 80
        except ValueError:
            width = 80
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                panel.show_message("Could not open video for preview.")
                return
            frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
            # Seek to ~15% in for a representative frame.
            target = max(0, int(frames * 0.15))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                panel.show_message("No preview frame available.")
                return
            if _CORE_OK and frame_to_ascii:
                lines = frame_to_ascii(
                    frame, width=width, color=s["color"], preset=s["preset"] or "classic"
                )
                panel.show_frame([_strip_ansi(line) for line in lines])
            else:
                panel.show_message("Preview converter unavailable.")
        except Exception:
            panel.show_message("Preview failed.")

    def _update_key_hints(self):
        self.query_one("#key-hints").update(
            "↑↓ nav  Enter open  P play  G path  W webcam  R refresh"
        )

    # ---- selections ----

    def select_file(self, path, kind):
        if kind == "lyrics":
            self._lyrics_auto = path
            self._log().write(f"[cyan]Lyrics: {os.path.basename(path)}[/cyan]")
            self._update_preview()
            return
        self.selected_file = path
        self.selected_kind = kind or "video"
        self._lyrics_auto = _auto_lyrics(path)
        name = self._selected_name()
        self.query_one("#selected-file").update(f"> {name}")
        note = ""
        if self._lyrics_auto:
            note = f"  [dim](lyrics: {os.path.basename(self._lyrics_auto)})[/dim]"
        self._log().write(
            f"[green]Video ready: {name}[/green]{note}  --  Press [Play File] or P"
        )
        self._update_preview()
        self._refresh_inline_preview()

    # ---- command building ----

    def _build_player_args(self, video_path, export_output=None):
        s = self._settings()
        args = [PYTHON, "-m", "ascii_player", video_path]
        args.extend(["-w", str(s["width"])])
        if s["preset"]:
            args.extend(["-p", str(s["preset"])])
        if s["color"]:
            args.append("-c")
        if not s["audio"]:
            args.append("--no-audio")
        if s["fps"]:
            args.extend(["-f", str(s["fps"])])
        if s["export"] != "none":
            args.extend(["--export", str(s["export"])])
            out = export_output or (s.get("output") or "").strip()
            if out:
                args.extend(["-o", out])
        if (s["lyrics"] == "auto" and self._lyrics_auto) or s["lyrics"] in ("split", "fullscreen"):
            lyr = self._lyrics_auto if s["lyrics"] == "auto" else s["lyrics"]
            if lyr:
                args.extend(["-l", lyr])
                if s["lyrics"] == "fullscreen":
                    args.append("--lyrics-mode")
                    args.append("fullscreen")
        if s["cache"]:
            args.append("--cache")
        return args

    def _build_webcam_args(self):
        s = self._settings()
        args = [PYTHON, "-m", "ascii_player", "--webcam"]
        args.extend(["-w", str(s["width"])])
        if s["preset"]:
            args.extend(["-p", str(s["preset"])])
        if s["color"]:
            args.append("-c")
        if self._lyrics_auto:
            args.extend(["-l", self._lyrics_auto])
        return args

    def _record_recent(self, path):
        recent = _load_recent()
        recent = [p for p in recent if os.path.abspath(p) != os.path.abspath(path)]
        recent.insert(0, os.path.abspath(path))
        _save_recent(recent)

    def _persist_settings(self):
        """Save the current settings panel state to ascii_player.yaml."""
        s = self._settings()
        cfg = load_config()
        cfg.update({
            "width": int(s["width"]) if str(s["width"]).isdigit() else 80,
            "preset": s["preset"] or "classic",
            "color": s["color"],
            "audio": s["audio"],
        })
        if s["fps"]:
            cfg["fps"] = float(s["fps"])
        else:
            cfg.pop("fps", None)
        cfg.update({
            "export": s["export"],
            "output": s["output"] or "",
            "lyrics": s["lyrics"],
            "cache": s["cache"],
        })
        save_config(cfg)

    def _launch(self, args, message_ok, message_err, on_recent=None):
        self.query_one("#status-text").update("Launching...")
        if on_recent:
            self._record_recent(on_recent)
        self._persist_settings()
        if launch_new_terminal(args):
            self._log().write(message_ok)
        else:
            self._log().write(message_err)
            self.query_one("#status-text").update("Failed")
            return
        self.query_one("#status-text").update("Ready")
        self.query_one(RecentList).refresh_recent()

    # ---- actions ----

    def action_refresh(self):
        self.query_one(FileBrowser).refresh_files()
        self._log().write("[dim]File list refreshed.[/dim]")

    def action_play(self):
        self.play_file()

    def action_webcam(self):
        self.run_webcam()

    def action_goto_path(self):
        self.query_one("#dir-input").focus()

    def action_focus_log(self):
        self.query_one("#log").focus()

    # ---- event handlers ----

    @on(Input.Submitted, "#url-input")
    def on_url_submitted(self, event):
        self.play_url()

    @on(Button.Pressed, "#btn-play-url")
    def on_play_url_pressed(self, event):
        self.play_url()

    @on(Button.Pressed, "#btn-play")
    def on_play_pressed(self, event):
        self.play_file()

    @on(Button.Pressed, "#btn-webcam")
    def on_webcam_pressed(self, event):
        self.run_webcam()

    @on(Select.Changed)
    def on_setting_changed(self, event):
        self._update_preview()
        self._refresh_inline_preview()

    @on(Input.Changed)
    def on_input_changed(self, event):
        if event.input.id in ("input-width", "input-fps"):
            self._update_preview()
        if event.input.id == "input-output":
            self._update_preview()

    def on_list_view_selected(self, event):
        """Double-select the file (Enter) triggers play."""
        if event.list_view is self.query_one(FileBrowser)._list_view():
            self._handle_browser_enter()

    # ---- play methods ----

    def play_url(self):
        url = self.query_one("#url-input").value.strip()
        if not url:
            self._log().write("[yellow]Paste a URL or file path first, then press Enter[/yellow]")
            return

        if os.path.isfile(url):
            # Local path typed directly.
            ext = os.path.splitext(url)[1].lower()
            self.select_file(url, "lyrics" if ext.lower() in LYRICS_EXT else "video")
            args = self._build_player_args(url)
            self._launch(
                args,
                f"[green]Playing:[/green] {url}",
                "[red]Failed to open terminal window[/red]",
                on_recent=url if ext.lower() in VIDEO_EXT else None,
            )
            self.query_one("#url-input").value = ""
            return

        if not is_url(url):
            self._log().write(f"[red]Not a valid URL or path: {url}[/red]")
            return

        args = self._build_player_args(url)
        self._launch(
            args,
            f"[green]Playing:[/green] {url}",
            "[red]Failed to open terminal window[/red]",
            on_recent=url,
        )
        self.query_one("#url-input").value = ""

    def play_file(self):
        if not self.selected_file:
            self._log().write(
                "[yellow]No video selected -- navigate the file list and "
                "press Enter on a [VID] file[/yellow]"
            )
            return

        name = self._selected_name()
        args = self._build_player_args(self.selected_file)
        self._launch(
            args,
            f"[green]Playing:[/green] {name}",
            "[red]Failed to open terminal window[/red]",
            on_recent=self.selected_file,
        )

    def run_webcam(self):
        args = self._build_webcam_args()
        self._launch(
            args,
            "[green]Webcam started in new window[/green]",
            "[red]Failed to open webcam[/red]",
        )


def run_tui():
    app = ASCIITuiApp()
    app.run()
