"""Main Textual application for ASCII Video Player."""

import os
import sys
import time

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Select, Static

from .. import __version__
from ..audio import cleanup_audio, extract_audio
from ..images import (
    IMAGE_EXT,
    RainAnimator,
    decode_lines,
    grid_lines,
    image_to_grid,
    is_image_file,
    is_image_url,
    load_image,
    type_lines,
)
from ..launcher import PYTHON, launch_new_terminal
from ..settings import load_config, save_config
from ..themes import apply_theme, cycle_theme, load_theme, register_themes, save_theme
from ..visualizer import AudioVisualizer
from .helpers import (
    LYRICS_EXT,
    VIDEO_EXT,
    _auto_lyrics,
    _load_recent,
    _save_recent,
    _strip_ansi,
    build_player_args,
    format_command_preview,
    is_url,
)
from .screens import FilePickerScreen, HelpScreen
from .widgets import (
    CommandPreview,
    FileBrowser,
    InlinePreview,
    PlaylistPanel,
    RecentList,
    SettingsPanel,
    StatusBar,
)

try:
    import cv2

    _CV2_OK = True
except ImportError:
    cv2 = None
    _CV2_OK = False

try:
    from ..core import frame_to_ascii

    _CORE_OK = True
except ImportError:
    frame_to_ascii = None
    _CORE_OK = False


class ASCIITuiApp(App):
    """Unified Terminal User Interface for ASCII Video Player."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("p", "play", "Play"),
        Binding("w", "webcam", "Webcam"),
        Binding("g", "goto_path", "Go to path"),
        Binding("t", "toggle_theme", "Theme"),
        Binding("v", "toggle_visualizer", "Visualizer"),
        Binding("ctrl+l", "focus_log", "Log"),
        Binding("ctrl+v", "paste_clipboard", "Paste"),
        Binding("ctrl+p", "command_palette", "Help"),
        Binding("f", "toggle_fullscreen", "Fullscreen"),
        Binding("ctrl+right", "play_next", "Next"),
        Binding("ctrl+left", "play_prev", "Prev"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.selected_kind = None
        self._lyrics_auto = None
        self._preview_timer = None
        self._webcam_preview = None
        self._webcam_task = None
        self._playlist = []
        self._playlist_index = 0
        self._current_theme = load_theme()
        self._visualizer = None
        self._visualizer_task = None
        self._visualizer_audio_path = None
        self._visualizer_start = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="sidebar"):
            yield FileBrowser()
            yield Static("", id="selected-file")
            yield RecentList()
            yield PlaylistPanel()

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
                yield Button("Paste (Ctrl+V)", id="btn-paste")
                yield Button("Browse", id="btn-browse")

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
        log.write("  [bold green]Option 1 -- Play a local video/image:[/bold green]")
        log.write("    1. Navigate with [Up]/[Down], open with [Enter]")
        log.write("    2. [Enter] on a file selects it, [P] plays")
        log.write("")
        log.write("  [bold cyan]Option 2 -- Play a YouTube URL or path:[/bold cyan]")
        log.write("    1. Paste a link or path in the box above")
        log.write("    2. Press Enter or click [Play URL]")
        log.write("")
        log.write("  [bold yellow]Option 3 -- Live webcam:[/bold yellow]")
        log.write("    Click [Webcam] or press W")
        log.write("")
        log.write("  [bold magenta]Option 4 -- Clipboard:[/bold magenta]")
        log.write("    Press Ctrl+V or click [Paste] to render a copied image")
        log.write("")
        log.write(
            "[dim][Backspace]=up dir  [G]=jump  [R]=refresh  [P]=play  "
            "[T]=theme  [V]=visualizer  [Ctrl+V]=paste[/dim]"
        )
        log.write("")
        log.write(
            "[dim]A new terminal window opens with playback: "
            "Space=pause  Q=quit  +/-=speed[/dim]"
        )
        self.query_one("#url-input").focus()
        cfg = load_config()
        self.query_one(SettingsPanel).load_from_config(cfg)
        self._update_preview()
        self._update_key_hints()
        if cfg:
            log.write("")
            log.write("[dim]Loaded persisted settings from ascii_player.yaml.[/dim]")
        register_themes(self)
        apply_theme(self, self._current_theme)

    def on_unmount(self):
        self._stop_preview_timer()
        self._stop_webcam_preview()
        self._stop_visualizer()

    # ---- state helpers ----

    def _settings(self):
        return self.query_one(SettingsPanel).collect()

    def _selected_name(self):
        return os.path.basename(self.selected_file) if self.selected_file else None

    def _log(self):
        return self.query_one("#log")

    def _stop_preview_timer(self):
        if self._preview_timer is not None:
            try:
                self._preview_timer.stop()
            except Exception:
                pass
            self._preview_timer = None

    def _update_preview(self):
        if self.selected_file:
            args = self._build_player_args(self.selected_file)
            self.query_one(CommandPreview).show(format_command_preview(args))
        else:
            self.query_one(CommandPreview).show("(nothing ready to play)")

    def _refresh_inline_preview(self):
        """Render a representative ASCII frame of the selected local video or image."""
        panel = self.query_one(InlinePreview)
        path = self.selected_file
        if not path or not os.path.isfile(path):
            panel.show_message("Select a video to see an ASCII preview here.")
            return
        if is_image_file(path) or is_image_url(path):
            self._stop_preview_timer()
            s = self._settings()
            try:
                width = int(s["width"]) if str(s["width"]).isdigit() else 80
            except ValueError:
                width = 80
            width = min(width if width > 0 else 60, 60)
            preset = s["preset"] or "classic"
            invert = bool(s.get("invert", False))
            dither = bool(s.get("dither", False))
            crop = bool(s.get("crop", False))
            try:
                aspect = float(s.get("aspect", 0.55))
            except (TypeError, ValueError):
                aspect = 0.55
            animation = s.get("animate", "none")

            try:
                grid = image_to_grid(
                    load_image(path),
                    width,
                    preset,
                    invert=invert,
                    dither=dither,
                    crop=crop,
                    aspect=aspect,
                )
            except Exception:
                panel.show_message("Preview failed.")
                return

            if animation == "none":
                panel.show_frame(grid_lines(grid, color=False))
                return

            animator = RainAnimator(grid) if animation == "rain" else None
            start = time.monotonic()
            duration = 1.0

            def tick():
                elapsed = time.monotonic() - start
                progress = min(1.0, elapsed / duration)
                if animation == "decode":
                    lines = decode_lines(grid, progress, color=False)
                elif animation == "type":
                    lines = type_lines(grid, progress, color=False)
                else:
                    lines = animator.lines(progress, 0.06, color=False)
                try:
                    panel.show_frame(lines)
                except Exception:
                    return
                if progress >= 1.0:
                    try:
                        panel.show_frame(grid_lines(grid, color=False))
                    except Exception:
                        pass
                    self._stop_preview_timer()

            try:
                self._preview_timer = self.set_interval(0.06, tick)
            except Exception:
                panel.show_frame(grid_lines(grid, color=False))
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
            "Up/Down nav  Enter select  P play  W webcam  T theme  "
            "V viz  G path  R refresh  Ctrl+V paste  F full  Ctrl+P help"
        )

    def _start_webcam_preview(self):
        """Start live webcam preview in the inline preview pane."""
        if not _CV2_OK:
            self.query_one(InlinePreview).show_message("Webcam preview needs OpenCV.")
            return
        if self._webcam_task is not None:
            return
        self._webcam_preview = cv2.VideoCapture(0)
        if not self._webcam_preview.isOpened():
            self.query_one(InlinePreview).show_message("Could not open webcam.")
            self._webcam_preview = None
            return
        self._webcam_task = self.set_interval(0.1, self._tick_webcam_preview)

    def _tick_webcam_preview(self):
        """Capture and render a webcam frame to the preview."""
        if self._webcam_preview is None or not self._webcam_preview.isOpened():
            return
        s = self._settings()
        try:
            width = int(s["width"]) if str(s["width"]).isdigit() else 80
        except ValueError:
            width = 80
        width = min(width, 60)
        ret, frame = self._webcam_preview.read()
        if not ret or frame is None:
            return
        if _CORE_OK and frame_to_ascii:
            lines = frame_to_ascii(
                frame, width=width, color=s["color"], preset=s["preset"] or "classic"
            )
            self.query_one(InlinePreview).show_frame([_strip_ansi(line) for line in lines])
        else:
            self.query_one(InlinePreview).show_message("Preview converter unavailable.")

    def _stop_webcam_preview(self):
        """Stop the webcam preview and release the camera."""
        if self._webcam_task is not None:
            try:
                self._webcam_task.stop()
            except Exception:
                pass
            self._webcam_task = None
        if self._webcam_preview is not None:
            try:
                self._webcam_preview.release()
            except Exception:
                pass
            self._webcam_preview = None

    # ---- selections ----

    def select_file(self, path, kind):
        if kind == "lyrics":
            self._lyrics_auto = path
            self._log().write(f"[cyan]Lyrics: {os.path.basename(path)}[/cyan]")
            self._update_preview()
            return
        if kind == "image":
            self.selected_file = path
            self.selected_kind = "image"
            self._lyrics_auto = None
            name = self._selected_name()
            self.query_one("#selected-file").update(f"> {name}")
            self._log().write(
                f"[magenta]Image ready: {name}[/magenta]  --  Press [Play (P)] or P"
            )
            self._update_preview()
            self._refresh_inline_preview()
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
            f"[green]Video ready: {name}[/green]{note}  --  Press [Play (P)] or P"
        )
        self._update_preview()
        self._refresh_inline_preview()

    # ---- command building ----

    def _build_player_args(self, video_path, export_output=None):
        return build_player_args(
            video_path,
            self._settings(),
            selected_kind=self.selected_kind,
            lyrics_auto=self._lyrics_auto,
            export_output=export_output,
        )

    def _build_webcam_args(self):
        s = self._settings()
        args = [PYTHON, "-m", "ascii_player", "--webcam", "-w", str(s["width"])]
        if s["preset"]:
            args.extend(["-p", str(s["preset"])])
        if s["color"]:
            args.append("-c")
        if self._lyrics_auto:
            args.extend(["-l", self._lyrics_auto])
        return args

    def _record_recent(self, path):
        recent = _load_recent()
        if is_url(path):
            recent = [p for p in recent if p != path]
            recent.insert(0, path)
        else:
            abs_path = os.path.abspath(path)
            recent = [p for p in recent if os.path.abspath(p) != abs_path]
            recent.insert(0, abs_path)
        _save_recent(recent)

    def _persist_settings(self):
        """Save the current settings panel state to ascii_player.yaml."""
        s = self._settings()
        cfg = load_config()
        cfg.update(
            {
                "width": int(s["width"]) if str(s["width"]).isdigit() else 80,
                "preset": s["preset"] or "classic",
                "color": s["color"],
                "audio": s["audio"],
            }
        )
        if s["fps"]:
            cfg["fps"] = float(s["fps"])
        else:
            cfg.pop("fps", None)
        cfg.update(
            {
                "export": s["export"],
                "output": s["output"] or "",
                "lyrics": s["lyrics"],
                "cache": s["cache"],
                "animate": s["animate"],
                "dither": s["dither"],
                "invert": s["invert"],
                "loop": s["loop"],
                "crop": s["crop"],
                "aspect": s["aspect"],
            }
        )
        save_config(cfg)

    def toggle_playlist_item(self, path, kind):
        """Add or remove a file from the playlist."""
        entry = {"path": path, "kind": kind}
        for i, e in enumerate(self._playlist):
            if e["path"] == path:
                self._playlist.pop(i)
                self._log().write(f"[dim]Removed from playlist: {os.path.basename(path)}[/dim]")
                self.query_one(PlaylistPanel).refresh_playlist(
                    self._playlist, self._playlist_index
                )
                return
        self._playlist.append(entry)
        self._log().write(
            f"[green]Added to playlist:[/green] {os.path.basename(path)} "
            f"({len(self._playlist)} items)"
        )
        self.query_one(PlaylistPanel).refresh_playlist(self._playlist, self._playlist_index)

    def clear_playlist(self):
        self._playlist.clear()
        self._playlist_index = 0
        self._log().write("[dim]Playlist cleared[/dim]")
        self.query_one(PlaylistPanel).refresh_playlist(self._playlist, self._playlist_index)

    def play_next(self):
        if not self._playlist:
            return
        self._playlist_index = (self._playlist_index + 1) % len(self._playlist)
        item = self._playlist[self._playlist_index]
        self.select_file(item["path"], item["kind"])
        self.query_one(PlaylistPanel).refresh_playlist(self._playlist, self._playlist_index)
        self.play_file()

    def play_prev(self):
        if not self._playlist:
            return
        self._playlist_index = (self._playlist_index - 1) % len(self._playlist)
        item = self._playlist[self._playlist_index]
        self.select_file(item["path"], item["kind"])
        self.query_one(PlaylistPanel).refresh_playlist(self._playlist, self._playlist_index)
        self.play_file()

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

    def action_paste_clipboard(self):
        self.paste_clipboard()

    def action_toggle_fullscreen(self):
        """Toggle sidebar visibility for full-screen art mode."""
        sidebar = self.query_one("#sidebar")
        main = self.query_one("#main")
        if sidebar.styles.display == "none":
            sidebar.styles.display = "block"
            main.styles.width = "60%"
        else:
            sidebar.styles.display = "none"
            main.styles.width = "100%"

    def action_command_palette(self):
        """Show help overlay."""
        self.push_screen(HelpScreen())

    def action_toggle_theme(self):
        """Cycle to next theme."""
        self._current_theme = cycle_theme(self._current_theme)
        save_theme(self._current_theme)
        apply_theme(self, self._current_theme)
        theme_names = {
            "dark": "Dark",
            "light": "Light",
            "high_contrast": "High Contrast",
            "retro": "Retro",
            "steins_gate": "Steins Gate",
        }
        theme_name = theme_names.get(self._current_theme, self._current_theme)
        self._log().write(f"[cyan]Theme: {theme_name}[/cyan]")

    def action_toggle_visualizer(self):
        """Toggle audio visualizer on/off."""
        if self._visualizer is not None:
            self._stop_visualizer()
            self._log().write("[dim]Visualizer: off[/dim]")
        else:
            self._start_visualizer()
            self._log().write("[cyan]Visualizer: on (bars in preview)[/cyan]")

    def _start_visualizer(self):
        """Start audio visualizer for the selected video."""
        self._stop_visualizer()
        audio_path = None
        if self.selected_file and os.path.isfile(self.selected_file):
            audio_path = extract_audio(self.selected_file)
        self._visualizer_audio_path = audio_path
        self._visualizer = AudioVisualizer(audio_path, fps=30.0, mode="bars")
        self._visualizer_start = time.monotonic()

        def tick():
            if self._visualizer is None:
                return
            elapsed = time.monotonic() - self._visualizer_start
            viz_lines = self._visualizer.render(elapsed, 40)
            if viz_lines:
                self.query_one(InlinePreview).show_frame(viz_lines)

        self._visualizer_task = self.set_interval(0.1, tick)

    def _stop_visualizer(self):
        """Stop audio visualizer and remove any temporary extracted audio."""
        if self._visualizer_task is not None:
            try:
                self._visualizer_task.stop()
            except Exception:
                pass
            self._visualizer_task = None
        self._visualizer = None
        if self._visualizer_audio_path:
            cleanup_audio(self._visualizer_audio_path)
            self._visualizer_audio_path = None

    def action_play_next(self):
        self.play_next()

    def action_play_prev(self):
        self.play_prev()

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

    @on(Button.Pressed, "#btn-paste")
    def on_paste_pressed(self, event):
        self.paste_clipboard()

    @on(Button.Pressed, "#btn-browse")
    def on_browse_pressed(self, event):
        browser = self.query_one(FileBrowser)
        self.push_screen(FilePickerScreen(browser.current_dir))

    @on(Select.Changed)
    def on_setting_changed(self, event):
        self._update_preview()
        self._refresh_inline_preview()

    @on(Input.Changed)
    def on_input_changed(self, event):
        if event.input.id in ("input-width", "input-fps", "input-output", "input-aspect"):
            self._update_preview()

    # ---- play methods ----

    def play_url(self):
        url = self.query_one("#url-input").value.strip()
        if not url:
            self._log().write("[yellow]Paste a URL or file path first, then press Enter[/yellow]")
            return

        if os.path.isfile(url):
            ext = os.path.splitext(url)[1].lower()
            if ext in LYRICS_EXT:
                kind = "lyrics"
            elif ext in IMAGE_EXT:
                kind = "image"
            else:
                kind = "video"
            self.select_file(url, kind)
            args = self._build_player_args(url)
            self._launch(
                args,
                f"[green]Playing:[/green] {url}",
                "[red]Failed to open terminal window[/red]",
                on_recent=url if (ext in VIDEO_EXT or ext in IMAGE_EXT) else None,
            )
            self.query_one("#url-input").value = ""
            return

        if not is_url(url):
            self._log().write(f"[red]Not a valid URL or path: {url}[/red]")
            return

        if is_image_url(url):
            self.select_file(url, "image")
            args = self._build_player_args(url)
            self._launch(
                args,
                f"[green]Playing:[/green] {url}",
                "[red]Failed to open terminal window[/red]",
                on_recent=url,
            )
            self.query_one("#url-input").value = ""
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
                "press Enter on a file[/yellow]"
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

    def paste_clipboard(self):
        pkg = sys.modules.get(__package__)
        get_cb_image = getattr(pkg, "clipboard_image")
        save_cb_image = getattr(pkg, "save_clipboard_image")
        get_cb_text = getattr(pkg, "clipboard_text")

        image = get_cb_image()
        if image is not None:
            try:
                path = save_cb_image(image)
            except Exception:
                self._log().write("[red]Could not save clipboard image[/red]")
                return
            self.query_one(FileBrowser).refresh_files()
            self.select_file(path, "image")
            self._log().write(f"[green]Pasted image:[/green] {os.path.basename(path)}")
            self.query_one("#status-text").update("Clipboard image ready")
            return
        text = get_cb_text()
        if text:
            text = text.strip()
            inp = self.query_one("#url-input")
            inp.value = text
            inp.focus()
            self.query_one("#status-text").update("Clipboard text pasted")
            return
        self._log().write("[yellow]Clipboard is empty or unavailable[/yellow]")
        self.query_one("#status-text").update("Clipboard empty")

    def run_webcam(self):
        self._stop_webcam_preview()
        args = self._build_webcam_args()
        self._launch(
            args,
            "[green]Webcam started in new window[/green]",
            "[red]Failed to open webcam[/red]",
        )


def run_tui():
    """Launch the Textual TUI application."""
    app = ASCIITuiApp()
    app.run()
