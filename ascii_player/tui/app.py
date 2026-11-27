"""Main Textual application for ASCII Art Studio (OpenCode / Claude Code CLI UX)."""

import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.events import Key
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Footer,
    Input,
    ListView,
    OptionList,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from .. import __version__
from ..audio import cleanup_audio, extract_audio
from ..config import ASCII_PRESETS, FILTER_MODES, POST_FX_MODES, PROMPT_ENGINES
from ..image_player import export_image
from ..images import (
    IMAGE_EXT,
    AsciiGrid,
    RainAnimator,
    copy_text_to_clipboard,
    decode_lines,
    grid_lines,
    image_to_grid,
    is_image_file,
    is_image_url,
    load_frames,
    load_image,
    save_grid,
    text_to_grid,
    type_lines,
)
from ..launcher import PYTHON, launch_new_terminal
from ..prompt_gen import (
    STARTER_PROMPTS,
    available_banner_fonts,
    generate_banner,
    generate_from_prompt,
)
from ..settings import load_config, save_config
from ..themes import THEMES, apply_theme, cycle_theme, load_theme, register_themes, save_theme
from ..url_loader import resolve_url
from ..visualizer import AudioVisualizer
from ..webcam import WebcamCapture
from .canvas_engine import ASCII_STENCILS
from .commands import (
    filter_slash_commands,
    find_matching_media_files,
    parse_omnibox_input,
)
from .draw_panel import DrawCanvas, DrawWorkspace
from .helpers import (
    LYRICS_EXT,
    VIDEO_EXT,
    _auto_lyrics,
    _load_recent,
    _save_recent,
    build_player_args,
    compute_autofit_width,
    format_command_preview,
    is_url,
)
from .screens import CommandPaletteScreen, ExportScreen, FilePickerScreen, HelpScreen
from .widgets import (
    CommandPreview,
    FileBrowser,
    InlinePreview,
    OmniboxBar,
    PlaylistPanel,
    PromptPanel,
    RecentList,
    SettingsPanel,
    StatusBar,
    StudioTopBar,
    UrlPanel,
    WebcamPanel,
    WelcomeHero,
)

try:
    import cv2

    _CV2_OK = True
except ImportError:
    cv2 = None
    _CV2_OK = False

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class ASCIITuiApp(App):
    """Canvas-first ASCII Art Studio modeled after OpenCode / Claude Code."""

    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("ctrl+d", "toggle_draw_mode", "Type"),
        Binding("ctrl+k", "open_palette", "Palette"),
        Binding("ctrl+o", "toggle_sidebar", "Files"),
        Binding("ctrl+b", "toggle_inspector", "Style"),
        Binding("ctrl+w", "toggle_webcam", "Webcam"),
        Binding("ctrl+y", "copy_ascii", "Copy"),
        Binding("ctrl+e", "save_ascii", "Export"),
        Binding("ctrl+t", "toggle_theme", "Theme"),
        Binding("ctrl+l", "focus_log", "Log"),
        Binding("ctrl+v", "paste_clipboard", "Paste"),
        Binding("ctrl+p", "command_palette", "Help"),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("alt+left", "history_prev", "Prev Art", show=False),
        Binding("alt+right", "history_next", "Next Art", show=False),
        Binding("escape", "dismiss_overlay", "Omnibox", show=False),
        Binding("p", "play", "Pop-out", show=False),
        Binding("w", "toggle_webcam", "Webcam", show=False),
        Binding("c", "toggle_color", "Color", show=False),
        Binding("y", "copy_ascii", "Copy", show=False),
        Binding("s", "save_ascii", "Save", show=False),
        Binding("f", "toggle_fullscreen", "Full", show=False),
        Binding("i", "toggle_inspector", "Style", show=False),
        Binding("+", "zoom_in", "Wider", show=False),
        Binding("=", "zoom_in", "Wider", show=False),
        Binding("-", "zoom_out", "Narrower", show=False),
        Binding("0", "zoom_autofit", "Fit", show=False),
        Binding("space", "space_action", "Freeze/Play", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("g", "goto_path", "Path", show=False),
        Binding("t", "toggle_theme", "Theme", show=False),
        Binding("v", "toggle_visualizer", "Viz", show=False),
        Binding("ctrl+right", "play_next", "Next", show=False),
        Binding("ctrl+left", "play_prev", "Prev", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.selected_file: Optional[str] = None
        self.selected_kind: Optional[str] = None
        self._lyrics_auto: Optional[str] = None
        self._preview_timer = None
        self._gif_timer = None
        self._gif_index: int = 0
        self._video_cap = None
        self._video_timer = None
        self._video_playing: bool = False
        self._resize_timer = None
        self._input_render_timer = None
        self._refit_timer = None
        self._spinner_timer = None
        self._spinner_idx: int = 0
        self._spinner_label: str = ""

        self._webcam_capture: Optional[WebcamCapture] = None
        self._webcam_preview = None
        self._webcam_task = None
        self._webcam_frames: int = 0
        self._cam_failures: int = 0
        self._webcam_start: float = 0.0
        self._webcam_opening: bool = False
        self._webcam_opening_requested: bool = False
        self._last_cam_image: Optional[Image.Image] = None
        self._cam_hue: float = 0.0

        self._playlist: List[dict] = []
        self._playlist_index: int = 0
        self._current_theme = load_theme()
        self._visualizer: Optional[AudioVisualizer] = None
        self._visualizer_task = None
        self._visualizer_audio_path: Optional[str] = None
        self._visualizer_start: float = 0.0
        self._visualizer_wanted: bool = False

        self._canvas_image: Optional[Image.Image] = None
        self._canvas_frames: List[Tuple[Image.Image, float]] = []
        self._canvas_direct_grid: Optional[AsciiGrid] = None
        self._canvas_last_grid: Optional[AsciiGrid] = None
        self._canvas_label: str = "ready"
        self._canvas_source_tag: str = "HOME"
        self._last_prompt_text: str = ""
        self._last_prompt_engine: str = "auto"

        self._omnibox_history: List[str] = []
        self._history_cursor: int = -1
        self._autocomplete_mode: Optional[str] = None
        self._autocomplete_items: List[Tuple[str, str]] = []

        self._art_history: List[Dict[str, Any]] = []
        self._art_history_idx: int = -1
        self._restoring_history: bool = False

        self._active_mode: str = "studio"
        self._hero_phase: float = 0.0
        self._hero_timer = None
        self._loading_settings: bool = False

    def compose(self) -> ComposeResult:
        yield StudioTopBar()
        with Horizontal(id="workspace"):
            with Container(id="sidebar"):
                with TabbedContent(initial="tab-file", id="source-tabs"):
                    with TabPane("Files", id="tab-file"):
                        yield FileBrowser()
                        yield Static("", id="selected-file")
                    with TabPane("Prompt", id="tab-prompt"):
                        yield PromptPanel()
                    with TabPane("URL", id="tab-url"):
                        yield UrlPanel()
                    with TabPane("Webcam", id="tab-webcam"):
                        yield WebcamPanel()
                with Collapsible(title="Recent & Queue", id="drawer-library", collapsed=True):
                    yield RecentList()
                    yield PlaylistPanel()

            with Container(id="main"):
                with Container(id="stage"):
                    yield WelcomeHero(id="welcome-hero")
                    yield InlinePreview(id="canvas-panel", classes="hidden")
                yield OmniboxBar(id="omnibox-container")
                yield DrawWorkspace(id="draw-workspace", classes="hidden")
                with Container(id="log-drawer"):
                    yield RichLog(id="log", highlight=True, markup=True)

            with VerticalScroll(id="inspector"):
                yield SettingsPanel()
                yield CommandPreview()
                with Horizontal(classes="inspector-actions"):
                    yield Button("Play (P)", id="btn-play", variant="success", compact=True)
                    yield Button("Log", id="btn-toggle-log", compact=True)

        yield StatusBar()
        yield Footer()

    def on_mount(self):
        self.title = f"ASCII Art Studio v{__version__}"
        self.sub_title = "OpenCode / Claude Code CLI Mode"
        log = self.query_one("#log", RichLog)
        log.write("[bold]ASCII Studio[/bold] -- type a prompt, path, URL, /command, or @file")

        self._loading_settings = True
        try:
            cfg = load_config()
            self.query_one(SettingsPanel).load_from_config(cfg)
            if cfg:
                log.write("[dim]Loaded persisted settings from ascii_player.yaml.[/dim]")
        finally:
            self._loading_settings = False

        register_themes(self)
        apply_theme(self, self._current_theme)
        self._canvas_last_grid = text_to_grid(WelcomeHero._WORDMARK.splitlines())
        self._sync_toolbar_buttons()
        self._update_preview()
        self._apply_responsive_layout()
        self._update_canvas_meta(None)
        self._start_hero_shimmer()
        self.query_one("#omnibox", Input).focus()

    def on_unmount(self):
        self._stop_spinner()
        self._stop_hero_shimmer()
        self._stop_all_animations()
        self._stop_webcam_preview()
        self._stop_visualizer()
        for timer_attr in ("_resize_timer", "_input_render_timer", "_refit_timer"):
            timer = getattr(self, timer_attr, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
                setattr(self, timer_attr, None)

    def _start_hero_shimmer(self):
        self._stop_hero_shimmer()

        def tick():
            if not self.is_mounted or self._active_mode != "studio":
                return
            try:
                hero = self.query_one("#welcome-hero", WelcomeHero)
                if hero.has_class("hidden"):
                    return
                self._hero_phase = (self._hero_phase + 0.14) % 6.28318
                compact = (self.size.width or 120) < 92
                hero.update_logo(self._current_theme, phase=self._hero_phase, compact=compact)
            except NoMatches:
                return

        self._hero_timer = self.set_interval(0.14, tick)

    def _stop_hero_shimmer(self):
        if self._hero_timer is not None:
            try:
                self._hero_timer.stop()
            except Exception:
                pass
            self._hero_timer = None

    def _apply_responsive_layout(self):
        if not self.is_mounted:
            return
        w = int(self.size.width or 120)
        h = int(self.size.height or 36)
        narrow = (w < 96) or (h <= 26)
        try:
            if narrow:
                self.screen.add_class("narrow")
            else:
                self.screen.remove_class("narrow")
        except Exception:
            pass
        try:
            self.query_one("#brand-mark", Static).update(
                "◆ studio" if w < 96 else "◆ ascii-studio"
            )
        except Exception:
            pass
        compact = w < 92
        try:
            self.query_one("#welcome-hero", WelcomeHero).update_logo(
                self._current_theme, phase=self._hero_phase, compact=compact
            )
        except Exception:
            pass
        if self._canvas_source_tag == "HOME":
            wm = WelcomeHero._COMPACT_WORDMARK if compact else WelcomeHero._WORDMARK
            self._canvas_last_grid = text_to_grid(wm.splitlines())
        self._update_key_hints()

    # ---- stage & visual chrome helpers ----

    def _show_canvas_stage(self):
        try:
            hero = self.query_one("#welcome-hero", WelcomeHero)
            if not hero.has_class("hidden"):
                hero.add_class("hidden")
            panel = self.query_one("#canvas-panel", InlinePreview)
            if panel.has_class("hidden"):
                panel.remove_class("hidden")
        except Exception:
            pass

    def _show_canvas_loading(self, title: str, detail: str = ""):
        self._show_canvas_stage()
        msg = f"[LOADING] {title}"
        if detail:
            msg = f"{msg}\n{detail}"
        try:
            self.query_one(InlinePreview).show_message(msg)
        except Exception:
            pass

    def _show_welcome_stage(self):
        self._stop_all_animations()
        self._stop_webcam_preview()
        self._canvas_image = None
        self._canvas_frames = []
        self._canvas_direct_grid = None
        compact = (self.size.width or 120) < 92
        wm = WelcomeHero._COMPACT_WORDMARK if compact else WelcomeHero._WORDMARK
        self._canvas_last_grid = text_to_grid(wm.splitlines())
        self._canvas_source_tag = "HOME"
        self._canvas_label = "ready"
        try:
            panel = self.query_one("#canvas-panel", InlinePreview)
            if not panel.has_class("hidden"):
                panel.add_class("hidden")
            hero = self.query_one("#welcome-hero", WelcomeHero)
            if hero.has_class("hidden"):
                hero.remove_class("hidden")
        except Exception:
            pass
        self._update_canvas_meta(None)
        self._set_status("Ready")
        self._set_activity("")
        self.query_one("#omnibox", Input).focus()

    def _start_spinner(self, label: str):
        self._stop_spinner()
        self._spinner_idx = 0
        self._spinner_label = label
        self._set_activity(f"{_SPINNER_FRAMES[0]} {label}")

        def tick():
            self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
            self._set_activity(f"{_SPINNER_FRAMES[self._spinner_idx]} {self._spinner_label}")

        self._spinner_timer = self.set_interval(0.08, tick)

    def _stop_spinner(self, final_note: str = ""):
        if self._spinner_timer is not None:
            try:
                self._spinner_timer.stop()
            except Exception:
                pass
            self._spinner_timer = None
        self._spinner_label = ""
        self._set_activity(final_note)

    def _set_activity(self, text: str, error: bool = False):
        try:
            line = self.query_one("#activity-line", Static)
            if error:
                line.add_class("error")
            else:
                line.remove_class("error")
            line.update(text)
        except Exception:
            pass

    def _report_error(self, msg: str, tag: str = "ERROR"):
        self._stop_spinner()
        self._set_activity(f"[ERROR] {msg}", error=True)
        self._set_status(f"[ERROR] {msg}")
        try:
            self._log().write(f"[red][{tag}] {msg}[/red]")
        except Exception:
            pass
        try:
            self.notify(msg, title=tag, severity="error", timeout=5)
        except Exception:
            pass

    # ---- state & timer helpers ----

    def _settings(self):
        return self.query_one(SettingsPanel).collect()

    def _selected_name(self):
        if not self.selected_file:
            return None
        if is_url(self.selected_file):
            return self.selected_file
        return os.path.basename(self.selected_file)

    def _log(self):
        return self.query_one("#log", RichLog)

    def _set_status(self, text: str):
        try:
            self.query_one("#status-text", Static).update(text)
        except Exception:
            pass

    def _stop_preview_timer(self):
        if self._preview_timer is not None:
            try:
                self._preview_timer.stop()
            except Exception:
                pass
            self._preview_timer = None

    def _stop_gif_timer(self):
        if self._gif_timer is not None:
            try:
                self._gif_timer.stop()
            except Exception:
                pass
            self._gif_timer = None

    def _stop_video_preview(self):
        self._video_playing = False
        if self._video_timer is not None:
            try:
                self._video_timer.stop()
            except Exception:
                pass
            self._video_timer = None
        if self._video_cap is not None:
            try:
                self._video_cap.release()
            except Exception:
                pass
            self._video_cap = None

    def _stop_all_animations(self):
        self._stop_preview_timer()
        self._stop_gif_timer()
        self._stop_video_preview()

    def _parse_float(self, value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _parse_width(self, settings: dict, img_w: int = 80, img_h: int = 45) -> int:
        if settings.get("auto_fit", True):
            avail_w, avail_h = self.query_one(InlinePreview).viewport_size()
            aspect = self._parse_float(settings.get("aspect", 0.55), 0.55)
            return compute_autofit_width(img_w, img_h, avail_w, avail_h, aspect=aspect)
        try:
            w = int(settings["width"]) if str(settings["width"]).strip().isdigit() else 80
        except (TypeError, ValueError):
            w = 80
        return max(12, min(260, w if w > 0 else 80))

    def _sync_toolbar_buttons(self):
        s = self._settings()
        try:
            color_btn = self.query_one("#btn-color-toggle", Button)
            color_btn.label = "rgb" if s["color"] else "mono"
            if s["color"]:
                color_btn.add_class("active")
            else:
                color_btn.remove_class("active")
        except Exception:
            pass
        try:
            fit_btn = self.query_one("#btn-autofit", Button)
            is_fit = bool(s.get("auto_fit", True))
            fit_btn.label = "fit" if is_fit else f"w:{s['width']}"
            if is_fit:
                fit_btn.add_class("active")
            else:
                fit_btn.remove_class("active")
        except Exception:
            pass
        self._update_omnibox_pills()

    def _update_omnibox_pills(self):
        s = self._settings()
        try:
            engine = str(self.query_one("#select-prompt-engine", Select).value or "auto")
        except Exception:
            engine = "auto"
        color_tag = "rgb" if s.get("color") else "mono"
        fit_tag = "fit" if s.get("auto_fit", True) else f"w={s.get('width', 80)}"
        preset = s.get("preset") or "classic"
        fx = s.get("filter") or "none"
        fx_list = list(s.get("post_fx") or ())
        parts = []
        if fx != "none":
            parts.append(fx)
        parts.extend(fx_list)
        fx_part = f" · fx:{'+'.join(parts)}" if parts else ""
        pills = f"{engine} · {preset} · {color_tag} · {fit_tag}{fx_part} · {self._current_theme}"
        try:
            self.query_one("#omnibox-pills", Static).update(pills)
        except Exception:
            pass

    def _update_preview(self):
        if self.selected_file:
            args = self._build_player_args(self.selected_file)
            self.query_one(CommandPreview).show(format_command_preview(args))
        else:
            self.query_one(CommandPreview).show("(nothing ready to pop-out)")

    def _update_canvas_meta(self, grid: Optional[AsciiGrid]):
        s = self._settings()
        color_tag = "RGB" if s["color"] else "MONO"
        preset = s["preset"] or "classic"
        hist_tag = ""
        if len(self._art_history) > 1 and self._art_history_idx >= 0:
            hist_tag = f" · #{self._art_history_idx + 1}/{len(self._art_history)}"
        if self._active_mode == "draw":
            meta = "·  type mode  ·  pure keyboard terminal ASCII"
        elif grid is None and self._canvas_source_tag == "HOME":
            meta = f"·  ready{hist_tag}"
        else:
            dims = f"{grid.width}x{grid.height}" if grid else "--"
            meta = (
                f"·  [{self._canvas_source_tag}] "
                f"{self._canvas_label} · {dims} · {preset} · {color_tag}{hist_tag}"
            )
        try:
            self.query_one("#canvas-meta", Static).update(meta)
        except Exception:
            pass
        self._update_omnibox_pills()

    def _update_key_hints(self):
        w = int(self.size.width or 120)
        if w >= 100:
            hints = "/ cmd · @ file · ^D type · ^K palette · ^T theme · ^Q quit"
        elif w >= 80:
            hints = "^D type · ^K palette · ^T theme · ^Q quit"
        else:
            hints = "^K · ^D · ^Q"
        try:
            self.query_one("#key-hints", Static).update(hints)
        except Exception:
            pass

    # ---- session artwork history ----

    def _push_art_history(
        self,
        tag: str,
        label: str,
        image: Optional[Image.Image] = None,
        frames: Optional[List[Tuple[Image.Image, float]]] = None,
        direct_grid: Optional[AsciiGrid] = None,
        saved_path: Optional[str] = None,
        kind: Optional[str] = None,
    ):
        if self._restoring_history:
            return
        entry = {
            "tag": tag,
            "label": label,
            "image": image,
            "frames": list(frames or []),
            "direct_grid": direct_grid,
            "saved_path": saved_path,
            "kind": kind,
        }
        if self._art_history_idx < len(self._art_history) - 1:
            self._art_history = self._art_history[: self._art_history_idx + 1]
        self._art_history.append(entry)
        if len(self._art_history) > 20:
            self._art_history.pop(0)
        self._art_history_idx = len(self._art_history) - 1

    def _restore_history_index(self, idx: int):
        if not (0 <= idx < len(self._art_history)):
            return
        self._restoring_history = True
        try:
            self._stop_all_animations()
            self._stop_webcam_preview()
            self._art_history_idx = idx
            entry = self._art_history[idx]
            self._canvas_source_tag = entry["tag"]
            self._canvas_label = entry["label"]
            self._canvas_image = entry["image"]
            self._canvas_frames = list(entry["frames"])
            self._canvas_direct_grid = entry["direct_grid"]
            if entry["saved_path"]:
                self.selected_file = entry["saved_path"]
                self.selected_kind = entry["kind"] or "image"
                self._update_preview()
            self._render_canvas(animate=False)
            self._set_activity(
                f"history #{idx + 1}/{len(self._art_history)}: {entry['label']}"
            )
        finally:
            self._restoring_history = False

    def action_history_prev(self):
        if self._art_history_idx > 0:
            self._restore_history_index(self._art_history_idx - 1)
        else:
            self._set_activity("at oldest session artwork")

    def action_history_next(self):
        if 0 <= self._art_history_idx < len(self._art_history) - 1:
            self._restore_history_index(self._art_history_idx + 1)
        else:
            self._set_activity("at newest session artwork")

    # ---- core dynamic canvas rendering ----

    def _grid_from_image(self, image: Image.Image, settings: dict) -> AsciiGrid:
        width = self._parse_width(settings, image.width, image.height)
        aspect = self._parse_float(settings.get("aspect", 0.55), 0.55)
        contrast = self._parse_float(settings.get("contrast", 1.0), 1.0)
        brightness = self._parse_float(settings.get("brightness", 1.0), 1.0)
        charset = (settings.get("charset") or "").strip() or None
        filter_mode = (settings.get("filter") or "none").strip().lower()
        post_fx = tuple(settings.get("post_fx") or ())
        return image_to_grid(
            image,
            width=width,
            preset=settings["preset"] or "classic",
            aspect=aspect,
            invert=bool(settings.get("invert", False)),
            dither=bool(settings.get("dither", False)),
            crop=bool(settings.get("crop", False)),
            charset=charset,
            contrast=contrast,
            brightness=brightness,
            filter_mode=filter_mode,
            colorcycle_hue=self._cam_hue,
            post_fx=post_fx,
        )

    def _render_canvas(self, animate: bool = False):
        """Re-render the active canvas source with current Inspector settings."""
        if not self.is_mounted:
            return
        try:
            panel = self.query_one(InlinePreview)
            s = self._settings()
        except NoMatches:
            return
        color = bool(s.get("color", False))

        if self._webcam_task is not None:
            return

        if self._canvas_direct_grid is not None:
            self._show_canvas_stage()
            self._stop_preview_timer()
            self._canvas_last_grid = self._canvas_direct_grid
            self._update_canvas_meta(self._canvas_direct_grid)
            anim = s.get("animate", "none") if animate else "none"
            if anim == "none":
                panel.show_grid(self._canvas_direct_grid, color=color)
                return
            self._play_reveal_animation(self._canvas_direct_grid, anim, color)
            return

        if self._canvas_frames:
            self._show_canvas_stage()
            self._start_gif_playback()
            return

        if self._canvas_image is None:
            self._update_canvas_meta(None)
            return

        self._show_canvas_stage()
        try:
            grid = self._grid_from_image(self._canvas_image, s)
        except Exception as exc:
            panel.show_message(f"Render failed: {exc}")
            return

        self._canvas_last_grid = grid
        self._update_canvas_meta(grid)
        self._stop_preview_timer()

        animation = s.get("animate", "none") if animate else "none"
        if animation == "none":
            panel.show_grid(grid, color=color)
            return
        self._play_reveal_animation(grid, animation, color)

    def _play_reveal_animation(self, grid: AsciiGrid, animation: str, color: bool):
        panel = self.query_one(InlinePreview)
        animator = RainAnimator(grid) if animation == "rain" else None
        start = time.monotonic()
        duration = 0.85

        def tick():
            elapsed = time.monotonic() - start
            progress = min(1.0, elapsed / duration)
            if animation == "decode":
                lines = decode_lines(grid, progress, color=color)
            elif animation == "type":
                lines = type_lines(grid, progress, color=color)
            else:
                lines = animator.lines(progress, 0.05, color=color)
            try:
                panel.show_frame(lines)
            except Exception:
                self._stop_preview_timer()
                return
            if progress >= 1.0:
                try:
                    panel.show_grid(grid, color=color)
                except Exception:
                    pass
                self._stop_preview_timer()

        try:
            self._preview_timer = self.set_interval(0.05, tick)
        except Exception:
            panel.show_grid(grid, color=color)

    def _start_gif_playback(self):
        self._stop_preview_timer()
        self._stop_gif_timer()
        if not self._canvas_frames:
            return
        self._gif_index = 0

        def render_step():
            try:
                if not self._canvas_frames:
                    self._stop_gif_timer()
                    return
                frame_img, _dur = self._canvas_frames[self._gif_index % len(self._canvas_frames)]
                self._gif_index = (self._gif_index + 1) % len(self._canvas_frames)
                s = self._settings()
                color = bool(s.get("color", False))
                grid = self._grid_from_image(frame_img, s)
                self._canvas_last_grid = grid
                self._update_canvas_meta(grid)
                self.query_one(InlinePreview).show_grid(grid, color=color)
            except Exception as exc:
                # A single bad frame must not kill the GIF timer for good.
                self._stop_gif_timer()
                self._log().write(f"[yellow][GIF] playback stopped: {exc}[/yellow]")

        render_step()
        avg_dur = max(0.05, min(0.25, self._canvas_frames[0][1]))
        self._gif_timer = self.set_interval(avg_dur, render_step)

    def _refresh_inline_preview(self, animate: bool = False):
        """Render the currently selected file or active canvas."""
        if (
            self._canvas_image is not None
            or self._canvas_frames
            or self._canvas_direct_grid is not None
        ):
            self._render_canvas(animate=animate)
            return
        path = self.selected_file
        if path and os.path.isfile(path):
            self._load_local_media_into_canvas(path, self.selected_kind or "video", animate=animate)

    def _load_local_media_into_canvas(self, path: str, kind: str, animate: bool = True):
        """Entry point: do the UI-thread setup, then decode in a worker."""
        self._stop_all_animations()
        self._stop_webcam_preview()
        name = os.path.basename(path)
        self._show_canvas_loading(f"Decoding {kind}: {name}")
        if not (kind == "image" or is_image_file(path)) and not _CV2_OK:
            self.query_one(InlinePreview).show_message(
                "Preview needs OpenCV (opencv-python) to render video frames."
            )
            return
        self._decode_local_media(path, kind, animate)

    @work(thread=True, exclusive=True, group="media-load")
    def _decode_local_media(self, path: str, kind: str, animate: bool = True):
        """Decode a local image/video preview off the UI thread.

        Opening and seeking a video file (and decoding a multi-frame GIF) can
        block for hundreds of milliseconds on cold or network-backed files, so
        the decode runs in a worker and only the paint happens on the loop.
        """
        if kind == "image" or is_image_file(path):
            try:
                frames = load_frames(path)
                image = frames[0][0] if frames else load_image(path)
            except Exception as exc:
                self.call_from_thread(self._media_message, f"Could not open image: {exc}")
                return
            self.call_from_thread(self._apply_local_image, path, frames, image, animate)
            return

        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                cap.release()
                self.call_from_thread(self._media_message, "Could not open video for preview.")
                return
            total_frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
            target = min(total_frames - 1, max(0, int(total_frames * 0.15)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                self.call_from_thread(self._media_message, "No preview frame available.")
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
        except Exception as exc:
            self.call_from_thread(self._media_message, f"Video preview failed: {exc}")
            return
        self.call_from_thread(self._apply_local_video, path, image, animate)

    def _media_message(self, text: str):
        try:
            self.query_one(InlinePreview).show_message(text)
        except Exception:
            pass
        self._report_error(text, tag="MEDIA")

    def _apply_local_image(self, path, frames, image, animate):
        try:
            self._canvas_direct_grid = None
            self._canvas_label = os.path.basename(path)
            self._canvas_source_tag = "IMAGE"
            if len(frames) > 1:
                self._canvas_frames = frames
                self._canvas_image = frames[0][0]
            else:
                self._canvas_frames = []
                self._canvas_image = image
            self._push_art_history(
                self._canvas_source_tag,
                self._canvas_label,
                image=self._canvas_image,
                frames=self._canvas_frames,
                saved_path=path,
                kind="image",
            )
            self._render_canvas(animate=animate)
        except Exception as exc:
            self.query_one(InlinePreview).show_message(f"Could not open image: {exc}")

    def _apply_local_video(self, path, image, animate):
        try:
            self._canvas_image = image
            self._canvas_frames = []
            self._canvas_direct_grid = None
            self._canvas_label = os.path.basename(path)
            self._canvas_source_tag = "VIDEO"
            self._push_art_history(
                self._canvas_source_tag,
                self._canvas_label,
                image=self._canvas_image,
                saved_path=path,
                kind="video",
            )
            self._render_canvas(animate=animate)
        except Exception as exc:
            self.query_one(InlinePreview).show_message(f"Video preview failed: {exc}")

    def _toggle_inline_video_playback(self):
        if not self.selected_file or not os.path.isfile(self.selected_file):
            return
        if self._video_playing:
            self._stop_video_preview()
            self._set_status("Inline video paused (Space to resume)")
            return
        if not _CV2_OK:
            self._set_status("OpenCV required for inline video playback")
            return
        cap = cv2.VideoCapture(self.selected_file)
        if not cap.isOpened():
            self._set_status("Could not open video for inline playback")
            return
        self._stop_all_animations()
        self._show_canvas_stage()
        self._video_cap = cap
        self._video_playing = True
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        interval = max(0.04, min(0.15, 1.0 / max(1.0, min(24.0, fps))))
        self._set_status("[PLAYING] Inline video preview (Space pause, P pop-out)")

        def tick_video():
            try:
                if not self._video_playing or self._video_cap is None:
                    return
                ok, frame = self._video_cap.read()
                if not ok or frame is None:
                    self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = self._video_cap.read()
                    if not ok or frame is None:
                        self._stop_video_preview()
                        return
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                self._canvas_image = img
                s = self._settings()
                grid = self._grid_from_image(img, s)
                self._canvas_last_grid = grid
                self._update_canvas_meta(grid)
                self.query_one(InlinePreview).show_grid(grid, color=bool(s.get("color", False)))
            except Exception as exc:
                # A decode hiccup or an unmounted widget must not kill the
                # playback interval for the rest of the session.
                self._stop_video_preview()
                self._set_status(f"[ERROR] Video preview stopped: {exc}")

        self._video_timer = self.set_interval(interval, tick_video)

    # ---- webcam live inline & snapshot ----

    def _start_webcam_preview(self):
        """Start live webcam streaming directly inside the Studio canvas."""
        if not _CV2_OK:
            self._show_canvas_stage()
            self.query_one(InlinePreview).show_message("Webcam preview needs OpenCV.")
            return
        if self._webcam_task is not None or getattr(self, "_webcam_opening", False):
            return
        self._stop_all_animations()
        self._show_canvas_stage()
        try:
            cam_idx = int(self.query_one("#input-camera", Input).value or 0)
        except Exception:
            cam_idx = 0

        try:
            cam_filter = str(self.query_one("#select-cam-filter", Select).value or "none")
        except Exception:
            cam_filter = "none"

        # Opening a camera device on Windows routinely blocks for hundreds of
        # milliseconds (sometimes seconds while the driver initialises), which
        # would freeze the whole TUI. Open it on a worker thread instead.
        self._webcam_opening = True
        self._webcam_opening_requested = True
        try:
            btn = self.query_one("#btn-cam-toggle", Button)
            btn.label = "Connecting..."
            btn.disabled = True
        except Exception:
            pass
        self._set_activity(f"[LIVE] opening camera #{cam_idx}...")
        self._open_webcam_worker(cam_idx, cam_filter)

    @work(thread=True, exclusive=True, group="webcam-open")
    def _open_webcam_worker(self, cam_idx: int, cam_filter: str):
        capture = WebcamCapture(camera_index=cam_idx, filter=cam_filter)
        if capture.open():
            opened, raw_cap = capture, capture.cap
        else:
            raw_cap = cv2.VideoCapture(cam_idx)
            if not raw_cap or not raw_cap.isOpened():
                if raw_cap:
                    raw_cap.release()
                raw_cap = None
            opened = None
        self.call_from_thread(self._apply_webcam_open, cam_idx, opened, raw_cap)

    def _apply_webcam_open(self, cam_idx: int, capture, raw_cap):
        self._webcam_opening = False
        try:
            btn = self.query_one("#btn-cam-toggle", Button)
            btn.disabled = False
        except Exception:
            pass
        # The user navigated away (or toggled) while the device was opening.
        if not self._webcam_opening_requested:
            if capture is not None:
                try:
                    capture.close() if hasattr(capture, "close") else capture.release()
                except Exception:
                    pass
            if raw_cap is not None:
                try:
                    raw_cap.release()
                except Exception:
                    pass
            return
        if raw_cap is None:
            self.query_one(InlinePreview).show_message(f"Could not open webcam #{cam_idx}.")
            try:
                self.query_one("#cam-stats", Static).update(
                    f"[ERROR] Camera #{cam_idx} unavailable"
                )
            except Exception:
                pass
            try:
                btn = self.query_one("#btn-cam-toggle", Button)
                btn.label = "Start Live Cam"
                btn.variant = "success"
            except Exception:
                pass
            self._report_error(f"Camera #{cam_idx} unavailable", tag="CAM")
            return
        self._webcam_capture = capture
        self._webcam_preview = raw_cap

        self._webcam_frames = 0
        self._cam_failures = 0
        self._webcam_start = time.monotonic()
        self._canvas_source_tag = "CAM"
        self._canvas_label = f"Camera #{cam_idx}"
        try:
            btn = self.query_one("#btn-cam-toggle", Button)
            btn.label = "Stop Live Cam"
            btn.variant = "error"
            self.query_one("#cam-stats", Static).update(f"[LIVE] Streaming camera #{cam_idx}...")
        except Exception:
            pass
        self._set_status(f"[LIVE] Webcam #{cam_idx} active (/snap or Space to freeze)")
        self._set_activity(f"[LIVE] streaming camera #{cam_idx} (/snap to freeze)")
        self._webcam_task = self.set_interval(0.08, self._tick_webcam_preview)

    def _tick_webcam_preview(self):
        """Capture and render one webcam frame through the Studio pipeline."""
        frame = None
        if self._webcam_capture is not None:
            try:
                cam_filter = str(self.query_one("#select-cam-filter", Select).value or "none")
            except Exception:
                cam_filter = "none"
            self._webcam_capture.filter = cam_filter
            frame = self._webcam_capture.read_frame()
            if frame is not None:
                frame = self._webcam_capture.apply_filter(frame)
        elif self._webcam_preview is not None and self._webcam_preview.isOpened():
            ret, raw = self._webcam_preview.read()
            if ret:
                frame = raw

        if frame is None:
            # Camera dropped out (unplugged, busy, driver reset). Without this
            # the timer spins forever on a dead handle instead of recovering.
            self._cam_failures += 1
            if self._cam_failures >= 15:
                self._stop_webcam_preview()
                self._set_status("[WARN] Webcam lost -- stopped preview")
                self._set_activity("[WARN] webcam signal lost")
                self._log().write("[yellow][CAM] Webcam signal lost -- preview stopped[/yellow]")
                try:
                    self.query_one("#cam-stats", Static).update("[ERROR] Camera signal lost")
                except Exception:
                    pass
            return
        self._cam_failures = 0

        try:
            if frame.ndim == 2:
                rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            else:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            self._last_cam_image = img
            self._cam_hue = (self._cam_hue + 4.0) % 256.0

            s = self._settings()
            grid = self._grid_from_image(img, s)
            self._show_canvas_stage()
            self._canvas_last_grid = grid
            self._webcam_frames += 1
            elapsed = max(0.01, time.monotonic() - self._webcam_start)
            fps = self._webcam_frames / elapsed
            self._update_canvas_meta(grid)
            self.query_one(InlinePreview).show_grid(grid, color=bool(s.get("color", False)))
        except Exception as exc:
            # One malformed frame must not kill the interval callback.
            self._cam_failures += 1
            if self._cam_failures == 1:
                self._log().write(f"[yellow][CAM] frame skipped: {exc}[/yellow]")
            if self._cam_failures >= 15:
                self._stop_webcam_preview()
                self._set_status(f"[ERROR] Webcam failed: {exc}")
            return
        try:
            self.query_one("#cam-stats", Static).update(
                f"[LIVE] {self._webcam_frames} frames | {fps:.1f} FPS | {grid.width}x{grid.height}"
            )
        except Exception:
            pass

    def _stop_webcam_preview(self):
        """Stop the live webcam preview and release the camera."""
        self._webcam_opening_requested = False
        if self._webcam_task is not None:
            try:
                self._webcam_task.stop()
            except Exception:
                pass
            self._webcam_task = None
        if self._webcam_capture is not None:
            try:
                self._webcam_capture.close()
            except Exception:
                pass
            self._webcam_capture = None
            self._webcam_preview = None
        elif self._webcam_preview is not None:
            try:
                self._webcam_preview.release()
            except Exception:
                pass
            self._webcam_preview = None

        try:
            btn = self.query_one("#btn-cam-toggle", Button)
            btn.label = "Start Live Cam"
            btn.variant = "success"
        except Exception:
            pass

    def _freeze_webcam_snapshot(self):
        """Capture the current live webcam frame onto the canvas for editing/export."""
        if self._last_cam_image is None and self._webcam_task is not None:
            self._tick_webcam_preview()
        snap = self._last_cam_image
        self._stop_webcam_preview()
        if snap is None:
            self._set_status("[WARN] No webcam frame to freeze")
            self._set_activity("[WARN] no webcam frame to freeze")
            return
        from ..images import save_clipboard_image

        try:
            saved_path = save_clipboard_image(snap)
            self.selected_file = saved_path
            self.selected_kind = "image"
            self.query_one("#selected-file", Static).update(f"> {os.path.basename(saved_path)}")
        except Exception:
            saved_path = None
        self._canvas_image = snap
        self._canvas_frames = []
        self._canvas_direct_grid = None
        self._canvas_source_tag = "SNAP"
        self._canvas_label = "Webcam Snapshot"
        self._push_art_history(
            "SNAP",
            "Webcam Snapshot",
            image=snap,
            saved_path=saved_path,
            kind="image",
        )
        self._render_canvas(animate=False)
        self._update_preview()
        try:
            self.query_one("#cam-stats", Static).update(
                "[SNAP] Frozen onto canvas -- ready to style/save"
            )
        except Exception:
            pass
        self._set_status("[OK] Webcam snapshot frozen -- style or export (/export)")
        self._set_activity("[SNAP] frozen onto canvas")
        if saved_path:
            self._log().write(f"[yellow][CAM] Snapshot frozen: {saved_path}[/yellow]")

    # ---- selections ----

    def select_file(self, path, kind):
        self._stop_webcam_preview()
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
            self.query_one("#selected-file", Static).update(f"> {name}")
            self._log().write(f"[magenta][FILE] Image loaded: {name}[/magenta]")
            self._set_status(f"Image loaded: {name}")
            self._set_activity(f"[FILE] {name}")
            self._update_preview()
            self._load_local_media_into_canvas(path, "image", animate=True)
            return
        self.selected_file = path
        self.selected_kind = kind or "video"
        self._lyrics_auto = _auto_lyrics(path)
        name = self._selected_name()
        self.query_one("#selected-file", Static).update(f"> {name}")
        note = ""
        if self._lyrics_auto:
            note = f"  [dim](lyrics: {os.path.basename(self._lyrics_auto)})[/dim]"
        self._log().write(f"[green][VIDEO] Ready: {name}[/green]{note}")
        self._set_status(f"Video ready: {name} (/popout or P for audio)")
        self._set_activity(f"[VIDEO] {name}")
        self._update_preview()
        self._load_local_media_into_canvas(path, "video", animate=False)

    # ---- prompt generation ----

    def generate_prompt_art(self, prompt: Optional[str] = None, engine: Optional[str] = None):
        """Start generating ASCII art from a prompt in a background worker."""
        prompt_inp = self.query_one("#prompt-input", Input)
        text = (prompt if prompt is not None else prompt_inp.value).strip()
        if not text:
            self._set_status("[WARN] Enter a prompt first")
            self._set_activity("[WARN] enter a prompt")
            return

        if prompt is not None:
            prompt_inp.value = text
        chosen_engine = engine or str(
            self.query_one("#select-prompt-engine", Select).value or "auto"
        )
        chosen_font = str(self.query_one("#select-banner-font", Select).value or "slant")
        s = self._settings()
        target_w = self._parse_width(s)

        self._last_prompt_text = text
        self._last_prompt_engine = chosen_engine
        self._stop_webcam_preview()
        self._stop_all_animations()

        try:
            self.query_one("#prompt-status", Static).update(
                f"[GENERATING] {chosen_engine}: {text[:28]}..."
            )
        except Exception:
            pass
        self._show_canvas_loading(
            f"Generating ({chosen_engine}): {text[:48]}",
            "Rendering ASCII frame...",
        )
        self._set_status(f"[GENERATING] Prompt ({chosen_engine}): {text}")
        self._start_spinner(f"generating ({chosen_engine}): {text[:40]}")
        self._run_prompt_worker(text, chosen_engine, target_w, chosen_font)

    @work(thread=True, exclusive=True, group="prompt")
    def _run_prompt_worker(self, text: str, engine: str, width: int, font: str):
        try:
            result = generate_from_prompt(text, engine=engine, width=width, font=font)
            self.call_from_thread(self._apply_prompt_result, result, None)
        except Exception as exc:
            self.call_from_thread(self._apply_prompt_result, None, str(exc))

    def _apply_prompt_result(self, result, error: Optional[str]):
        if error or result is None:
            msg = error or "Generation failed"
            try:
                self.query_one("#prompt-status", Static).update(f"[ERROR] {msg}")
            except Exception:
                pass
            try:
                self.query_one(InlinePreview).show_message(f"[ERROR] Prompt failed:\n{msg}")
            except Exception:
                pass
            self._report_error(f"Prompt failed: {msg}", tag="PROMPT")
            return

        self._canvas_frames = []
        self._canvas_image = result.image
        self._canvas_direct_grid = result.grid
        self._canvas_label = f"{result.prompt} ({result.engine})"
        self._canvas_source_tag = "PROMPT"
        if result.saved_path:
            self.selected_file = result.saved_path
            self.selected_kind = "image"
            self._lyrics_auto = None
            self.query_one("#selected-file", Static).update(
                f"> {os.path.basename(result.saved_path)}"
            )
            self._update_preview()

        self._push_art_history(
            "PROMPT",
            self._canvas_label,
            image=result.image,
            direct_grid=result.grid,
            saved_path=result.saved_path,
            kind="image",
        )
        self._render_canvas(animate=True)
        note = result.note or result.engine
        self._stop_spinner(f"[OK] {note}")
        try:
            self.query_one("#prompt-status", Static).update(f"[OK] {note}")
        except Exception:
            pass
        self._set_status(f"[OK] Prompt rendered via {result.engine}")
        self._log().write(f"[magenta][PROMPT] '{result.prompt}' -> {note}[/magenta]")

    # ---- universal URL loader ----

    def load_url_source(self, raw_url: Optional[str] = None):
        """Resolve any image/webpage/YouTube URL and render it onto the Studio canvas."""
        url_inp = self.query_one("#url-input", Input)
        url = (raw_url if raw_url is not None else url_inp.value).strip()
        if not url:
            self._set_status("[WARN] Paste a URL or file path first")
            return
        if raw_url is not None:
            url_inp.value = url

        if os.path.isfile(url):
            ext = os.path.splitext(url)[1].lower()
            kind = "lyrics" if ext in LYRICS_EXT else ("image" if ext in IMAGE_EXT else "video")
            self.select_file(url, kind)
            return

        if not is_url(url):
            self._set_status(f"[ERROR] Invalid URL: {url}")
            self._set_activity(f"[ERROR] invalid URL: {url}")
            try:
                self.query_one("#url-info", Static).update(
                    f"[ERROR] Not a valid URL or path: {url}"
                )
            except Exception:
                pass
            return

        self._stop_webcam_preview()
        self._stop_all_animations()
        try:
            self.query_one("#url-info", Static).update(f"[LOADING] Resolving {url[:45]}...")
        except Exception:
            pass
        self._show_canvas_loading(f"Resolving URL: {url[:52]}")
        self._set_status("[LOADING] Resolving URL...")
        self._start_spinner(f"resolving url: {url[:44]}")
        self._run_url_worker(url)

    @work(thread=True, exclusive=True, group="url")
    def _run_url_worker(self, url: str):
        try:
            resolved = resolve_url(url)
            self.call_from_thread(self._apply_url_result, resolved, None)
        except Exception as exc:
            self.call_from_thread(self._apply_url_result, None, str(exc))

    def _apply_url_result(self, resolved, error: Optional[str]):
        if error or resolved is None:
            msg = error or "Could not resolve URL"
            try:
                self.query_one("#url-info", Static).update(f"[ERROR] {msg}")
            except Exception:
                pass
            try:
                self.query_one(InlinePreview).show_message(f"[ERROR] URL failed:\n{msg}")
            except Exception:
                pass
            self._report_error(f"URL failed: {msg}", tag="URL")
            return

        self._canvas_direct_grid = None
        self._canvas_frames = list(resolved.frames or [])
        self._canvas_image = resolved.image
        self._canvas_label = resolved.title or resolved.url
        self._canvas_source_tag = "YOUTUBE" if resolved.kind == "youtube" else "URL"

        if resolved.is_playable_video:
            self.selected_file = resolved.url
            self.selected_kind = "video"
        elif resolved.saved_path:
            self.selected_file = resolved.saved_path
            self.selected_kind = "image"
        else:
            self.selected_file = resolved.url
            self.selected_kind = "image"
        self._lyrics_auto = None
        self._update_preview()
        self._record_recent(resolved.url)
        try:
            self.query_one(RecentList).refresh_recent()
        except Exception:
            pass

        if resolved.image is not None or resolved.frames:
            self._push_art_history(
                self._canvas_source_tag,
                self._canvas_label,
                image=resolved.image,
                frames=resolved.frames,
                saved_path=self.selected_file,
                kind=self.selected_kind,
            )
            self._render_canvas(animate=True)
            extra = " (/popout for full video+audio)" if resolved.is_playable_video else ""
            self._stop_spinner(f"[OK] {resolved.title}{extra}")
            try:
                self.query_one("#url-info", Static).update(f"[OK] {resolved.title}{extra}")
            except Exception:
                pass
            self._set_status(f"[OK] Loaded URL: {resolved.title}")
            self._log().write(f"[cyan][URL] Loaded ({resolved.kind}): {resolved.title}[/cyan]")
        else:
            self._show_canvas_stage()
            self._stop_spinner(f"[OK] video stream ready: {resolved.title}")
            self.query_one(InlinePreview).show_message(
                f"Video stream ready: {resolved.title}\n"
                "Run /popout or press P to launch playback."
            )
            self._set_status(f"[OK] Video URL ready: {resolved.title}")

    # ---- omnibox submission, autocomplete & slash commands ----

    def _hide_autocomplete(self):
        self._autocomplete_mode = None
        self._autocomplete_items = []
        try:
            self.query_one("#autocomplete-box").remove_class("visible")
        except Exception:
            pass
        try:
            popup = self.query_one("#autocomplete-popup", OptionList)
            popup.remove_class("visible")
            popup.clear_options()
        except Exception:
            pass

    def _update_autocomplete(self, text: str):
        val = text or ""
        try:
            popup = self.query_one("#autocomplete-popup", OptionList)
        except Exception:
            return

        if val.startswith("/") and " " not in val:
            matches = filter_slash_commands(val, limit=8)
            if not matches:
                self._hide_autocomplete()
                return
            self._autocomplete_mode = "slash"
            self._autocomplete_items = [(cmd.name, cmd.usage) for cmd in matches]
            popup.clear_options()
            for idx, cmd in enumerate(matches):
                popup.add_option(Option(f"{cmd.usage:<22} {cmd.description}", id=f"ac-{idx}"))
            popup.highlighted = 0
            popup.add_class("visible")
            try:
                self.query_one("#autocomplete-box").add_class("visible")
            except Exception:
                pass
            return

        if val.startswith("@"):
            query = val[1:]
            browser_dir = self.query_one(FileBrowser).current_dir
            matches = find_matching_media_files(browser_dir, query, limit=8)
            if not matches:
                self._hide_autocomplete()
                return
            self._autocomplete_mode = "at"
            self._autocomplete_items = [(rel, full) for rel, full, _kind in matches]
            popup.clear_options()
            for idx, (rel, _full, kind) in enumerate(matches):
                popup.add_option(Option(f"[{kind:<5}] @{rel}", id=f"ac-{idx}"))
            popup.highlighted = 0
            popup.add_class("visible")
            try:
                self.query_one("#autocomplete-box").add_class("visible")
            except Exception:
                pass
            return

        self._hide_autocomplete()

    def _apply_autocomplete_index(self, idx: int, execute: bool = False):
        if not (0 <= idx < len(self._autocomplete_items)):
            return
        label, payload = self._autocomplete_items[idx]
        inp = self.query_one("#omnibox", Input)
        mode = self._autocomplete_mode
        self._hide_autocomplete()
        if mode == "slash":
            if execute and "<" not in payload:
                inp.value = ""
                self.execute_slash_command(label, "")
            else:
                inp.value = f"{label} "
                inp.cursor_position = len(inp.value)
                inp.focus()
        elif mode == "at":
            if execute:
                inp.value = ""
                self.submit_omnibox(payload)
            else:
                inp.value = payload
                inp.cursor_position = len(inp.value)
                inp.focus()

    def submit_omnibox(self, raw: str):
        """Parse and execute any omnibox input (prompt, path, URL, /command, @file)."""
        kind, value, arg = parse_omnibox_input(raw)
        if kind == "empty":
            return
        if kind == "command":
            self.execute_slash_command(value, arg)
            return
        if kind == "at_file":
            browser_dir = self.query_one(FileBrowser).current_dir
            matches = find_matching_media_files(browser_dir, value, limit=1)
            if matches:
                _rel, full_path, media_kind = matches[0]
                self.select_file(full_path, media_kind)
            else:
                self._set_activity(f"[WARN] no media matching @{value}")
            return
        if kind == "file":
            ext = os.path.splitext(value)[1].lower()
            if ext in LYRICS_EXT:
                self.select_file(value, "lyrics")
            elif ext in IMAGE_EXT or is_image_file(value):
                self.select_file(value, "image")
            else:
                self.select_file(value, "video")
            return
        if kind == "dir":
            browser = self.query_one(FileBrowser)
            browser.current_dir = os.path.abspath(value)
            browser.refresh_files()
            self._open_sidebar_exclusive()
            self._set_activity(f"[DIR] {browser.current_dir}")
            return
        if kind == "url":
            self.load_url_source(value)
            return
        self.generate_prompt_art(prompt=value)

    def execute_slash_command(self, cmd: str, arg: str = ""):
        """Execute a canonical slash command with optional argument string."""
        name = cmd.strip().lower()
        val = (arg or "").strip()

        if name == "/prompt":
            if val:
                self.generate_prompt_art(prompt=val)
            else:
                self.generate_prompt_art(prompt=random.choice(STARTER_PROMPTS))
            return

        if name == "/banner":
            text = val or "ASCII STUDIO"
            self.generate_prompt_art(prompt=text, engine="banner")
            return

        if name == "/url":
            if val:
                self.load_url_source(val)
            else:
                self.action_tab_url()
            return

        if name == "/open":
            if not val:
                self.action_toggle_sidebar()
                return
            expanded = os.path.expanduser(val.strip('"').strip("'"))
            if os.path.isdir(expanded):
                browser = self.query_one(FileBrowser)
                browser.current_dir = os.path.abspath(expanded)
                browser.refresh_files()
                self._open_sidebar_exclusive()
                self._set_activity(f"[DIR] {browser.current_dir}")
            elif os.path.isfile(expanded):
                self.submit_omnibox(expanded)
            else:
                self._report_error(f"path not found: {val}", tag="OPEN")
            return

        if name == "/webcam":
            if val in ("none", "mirror", "edge", "invert", "colorcycle"):
                self.query_one("#select-cam-filter", Select).value = val
                if self._webcam_task is None:
                    self._start_webcam_preview()
                else:
                    self._set_activity(f"[CAM] filter -> {val}")
            else:
                self.action_toggle_webcam()
            return

        if name == "/snap":
            self._freeze_webcam_snapshot()
            return

        if name == "/paste":
            self.paste_clipboard()
            return

        if name == "/preset":
            sel = self.query_one("#select-preset", Select)
            names = list(ASCII_PRESETS.keys())
            if val in ASCII_PRESETS:
                sel.value = val
            elif not val:
                cur = str(sel.value or "classic")
                idx = (names.index(cur) + 1) % len(names) if cur in names else 0
                sel.value = names[idx]
            else:
                self._set_activity(f"[WARN] unknown preset '{val}' ({', '.join(names)})")
                return
            self._set_activity(f"[STYLE] preset -> {sel.value}")
            return

        if name == "/color":
            cb = self.query_one("#select-color", Checkbox)
            if val.lower() in ("on", "true", "1", "rgb"):
                cb.value = True
            elif val.lower() in ("off", "false", "0", "mono"):
                cb.value = False
            else:
                cb.value = not bool(cb.value)
            self._set_activity(f"[STYLE] color -> {'RGB' if cb.value else 'MONO'}")
            return

        if name == "/width":
            fit_cb = self.query_one("#check-autofit", Checkbox)
            if not val or val.lower() == "fit":
                fit_cb.value = True
                self._set_activity("[STYLE] width -> auto-fit")
                return
            if val.isdigit():
                w = max(12, min(260, int(val)))
                fit_cb.value = False
                self.query_one("#input-width", Input).value = str(w)
                self._sync_toolbar_buttons()
                self._update_preview()
                self._render_canvas(animate=False)
                self._set_activity(f"[STYLE] width -> {w}")
            else:
                self._set_activity("[WARN] usage: /width <12..260|fit>")
            return

        if name == "/filter":
            sel = self.query_one("#select-filter", Select)
            modes = list(FILTER_MODES)
            if val in modes:
                sel.value = val
            elif not val:
                cur = str(sel.value or "none")
                idx = (modes.index(cur) + 1) % len(modes) if cur in modes else 0
                sel.value = modes[idx]
            else:
                self._set_activity(f"[WARN] unknown filter '{val}'")
                return
            self._set_activity(f"[FX] filter -> {sel.value}")
            return

        if name == "/fx":
            tokens = [t.strip().lower() for t in val.replace(",", " ").split() if t.strip()]
            if not tokens:
                active = list(self._settings().get("post_fx") or ())
                if active:
                    self._set_activity(f"[FX] active: {'+'.join(active)} (/fx clear)")
                else:
                    self._set_activity(f"[FX] available: {', '.join(POST_FX_MODES)}")
                return
            if any(t in ("clear", "off", "none", "reset") for t in tokens):
                self._loading_settings = True
                try:
                    for mode in POST_FX_MODES:
                        self.query_one(f"#fx-{mode}", Checkbox).value = False
                finally:
                    self._loading_settings = False
                self._sync_toolbar_buttons()
                self._update_preview()
                self._render_canvas(animate=False)
                self._set_activity("[FX] cleared all post-fx")
                return
            unknown = [t for t in tokens if t not in POST_FX_MODES]
            if unknown:
                self._set_activity(
                    f"[WARN] unknown fx '{unknown[0]}' ({', '.join(POST_FX_MODES)})"
                )
                return
            self._loading_settings = True
            try:
                for tok in tokens:
                    cb = self.query_one(f"#fx-{tok}", Checkbox)
                    cb.value = not bool(cb.value)
            finally:
                self._loading_settings = False
            self._sync_toolbar_buttons()
            self._update_preview()
            self._render_canvas(animate=False)
            active = list(self._settings().get("post_fx") or ())
            self._set_activity(
                f"[FX] active: {'+'.join(active)}" if active else "[FX] cleared all post-fx"
            )
            return

        if name == "/dither":
            cb = self.query_one("#select-dither", Checkbox)
            cb.value = val.lower() in ("on", "true", "1") if val else not bool(cb.value)
            self._set_activity(f"[FX] dither -> {'ON' if cb.value else 'OFF'}")
            return

        if name == "/invert":
            cb = self.query_one("#select-invert", Checkbox)
            cb.value = val.lower() in ("on", "true", "1") if val else not bool(cb.value)
            self._set_activity(f"[FX] invert -> {'ON' if cb.value else 'OFF'}")
            return

        if name == "/crop":
            cb = self.query_one("#select-crop", Checkbox)
            cb.value = val.lower() in ("on", "true", "1") if val else not bool(cb.value)
            self._set_activity(f"[STYLE] crop -> {'ON' if cb.value else 'OFF'}")
            return

        if name == "/contrast":
            try:
                num = max(0.2, min(3.5, float(val)))
                self.query_one("#input-contrast", Input).value = f"{num:.2f}"
                self._render_canvas(animate=False)
                self._set_activity(f"[FX] contrast -> {num:.2f}")
            except ValueError:
                self._set_activity("[WARN] usage: /contrast <0.2..3.5>")
            return

        if name == "/brightness":
            try:
                num = max(0.2, min(3.0, float(val)))
                self.query_one("#input-brightness", Input).value = f"{num:.2f}"
                self._render_canvas(animate=False)
                self._set_activity(f"[FX] brightness -> {num:.2f}")
            except ValueError:
                self._set_activity("[WARN] usage: /brightness <0.2..3.0>")
            return

        if name == "/aspect":
            try:
                num = max(0.2, min(2.0, float(val)))
                self.query_one("#input-aspect", Input).value = f"{num:.2f}"
                self._render_canvas(animate=False)
                self._set_activity(f"[STYLE] aspect -> {num:.2f}")
            except ValueError:
                self._set_activity("[WARN] usage: /aspect <0.2..2.0>")
            return

        if name == "/charset":
            inp = self.query_one("#input-charset", Input)
            inp.value = "" if val.lower() in ("", "reset", "off") else val
            self._render_canvas(animate=False)
            msg = "[STYLE] custom charset updated" if inp.value else "[STYLE] charset reset"
            self._set_activity(msg)
            return

        if name == "/animate":
            sel = self.query_one("#select-animate", Select)
            if val in ("none", "decode", "type", "rain"):
                sel.value = val
                self._render_canvas(animate=True)
                self._set_activity(f"[FX] animate -> {val}")
            else:
                self._set_activity("[WARN] usage: /animate <none|decode|type|rain>")
            return

        if name == "/engine":
            sel = self.query_one("#select-prompt-engine", Select)
            if val in PROMPT_ENGINES:
                sel.value = val
                self._update_omnibox_pills()
                self._set_activity(f"[PROMPT] engine -> {val}")
            else:
                self._set_activity(f"[WARN] engines: {', '.join(PROMPT_ENGINES)}")
            return

        if name == "/font":
            sel = self.query_one("#select-banner-font", Select)
            fonts = available_banner_fonts()
            if val in fonts:
                sel.value = val
                self._set_activity(f"[BANNER] font -> {val}")
            else:
                self._set_activity(f"[WARN] fonts: {', '.join(fonts[:8])}")
            return

        if name == "/draw":
            sub = val.lower()
            if sub in ASCII_STENCILS or sub == "off":
                self.action_switch_draw(stencil=sub)
            elif sub == "trace":
                self.action_switch_draw(trace_current=True)
            else:
                self.action_switch_draw(import_current=(sub == "edit"))
            return

        if name == "/studio":
            self.action_switch_studio()
            return

        if name == "/style":
            self.action_toggle_inspector()
            return

        if name == "/palette":
            self.action_open_palette()
            return

        if name == "/copy":
            self.action_copy_ascii()
            return

        if name == "/export":
            if val:
                ext = os.path.splitext(val)[1].lstrip(".").lower() or "png"
                if ext not in ("txt", "ans", "html", "png", "gif"):
                    ext = "png"
                self.export_current_canvas(val, ext)
            else:
                self.action_save_ascii()
            return

        if name == "/popout":
            self.play_file()
            return

        if name == "/prev":
            self.action_history_prev()
            return

        if name == "/next":
            self.action_history_next()
            return

        if name == "/theme":
            if val in THEMES:
                self._current_theme = val
                save_theme(val)
                apply_theme(self, val)
                self._update_omnibox_pills()
                self._set_activity(f"[THEME] {val}")
            elif not val:
                self.action_toggle_theme()
            else:
                self._set_activity(f"[WARN] themes: {', '.join(THEMES.keys())}")
            return

        if name == "/log":
            self.action_focus_log()
            return

        if name == "/clear":
            self._show_welcome_stage()
            return

        if name == "/help":
            self.action_command_palette()
            return

        if name == "/quit":
            self.exit()
            return

        self._set_activity(f"[WARN] unknown command {name} (type /help or Ctrl+K)")

    # ---- command building & persistence ----

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
                "auto_fit": s["auto_fit"],
                "filter": s["filter"],
                "contrast": s["contrast"],
                "brightness": s["brightness"],
                "charset": s["charset"],
                "post_fx": list(s.get("post_fx") or ()),
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
        self._set_status("Launching...")
        if on_recent:
            self._record_recent(on_recent)
        self._persist_settings()
        if launch_new_terminal(args):
            self._log().write(message_ok)
        else:
            self._log().write(message_err)
            self._set_status("Failed")
            return
        self._set_status("Ready")
        self.query_one(RecentList).refresh_recent()

    # ---- copy & export ----

    def export_current_canvas(self, path: str, fmt: str):
        """Export the active Studio or Draw canvas grid directly to disk."""
        s = self._settings()
        if self._active_mode == "draw":
            color = True
            grid = self.query_one("#draw-workspace", DrawWorkspace).export_grid()
        else:
            color = bool(s.get("color", False))
            grid = self._canvas_last_grid
            if grid is None and self._canvas_image is not None:
                grid = self._grid_from_image(self._canvas_image, s)

        if fmt == "gif" and self.selected_file and os.path.isfile(self.selected_file):
            try:
                width = grid.width if grid else self._parse_width(s)
                out = export_image(
                    self.selected_file,
                    path,
                    width=width,
                    preset=s["preset"] or "classic",
                    invert=bool(s.get("invert", False)),
                    dither=bool(s.get("dither", False)),
                    crop=bool(s.get("crop", False)),
                    aspect=self._parse_float(s.get("aspect", 0.55), 0.55),
                    export_format="gif",
                )
                self._set_status(f"[OK] Exported GIF: {out}")
                self._set_activity(f"[EXPORT] saved {out}")
                self._log().write(f"[green][EXPORT] Saved {out}[/green]")
                return
            except Exception as exc:
                self._report_error(f"Export failed: {exc}", tag="EXPORT")
                return

        if grid is None:
            self._set_status("[WARN] Nothing on canvas to export")
            return
        try:
            target = path if path.lower().endswith(f".{fmt}") else f"{path}.{fmt}"
            saved = save_grid(grid, target, color=color)
            self._set_status(f"[OK] Saved {saved}")
            self._set_activity(f"[EXPORT] saved {saved}")
            self._log().write(f"[green][EXPORT] Saved {saved}[/green]")
        except Exception as exc:
            self._report_error(f"Export failed: {exc}", tag="EXPORT")

    # ---- actions ----

    def _switch_tab(self, tab_id: str):
        try:
            self.query_one("#source-tabs", TabbedContent).active = tab_id
        except Exception:
            pass

    def _sync_mode_tabs(self):
        try:
            st_btn = self.query_one("#btn-mode-studio", Button)
            dr_btn = self.query_one("#btn-mode-draw", Button)
            if self._active_mode == "draw":
                st_btn.remove_class("active")
                dr_btn.add_class("active")
            else:
                dr_btn.remove_class("active")
                st_btn.add_class("active")
        except Exception:
            pass

    def action_switch_studio(self):
        self._active_mode = "studio"
        try:
            self.query_one("#draw-workspace", DrawWorkspace).add_class("hidden")
            self.query_one("#stage", Container).remove_class("hidden")
            self.query_one("#omnibox-container", OmniboxBar).remove_class("hidden")
            self.query_one("#omnibox", Input).focus()
        except Exception:
            pass
        self._sync_mode_tabs()
        self._update_canvas_meta(self._canvas_last_grid)

    def action_switch_draw(
        self,
        import_current: bool = False,
        stencil: Optional[str] = None,
        trace_current: bool = False,
    ):
        self._stop_webcam_preview()
        self._stop_all_animations()
        self._active_mode = "draw"
        try:
            self.query_one("#stage", Container).add_class("hidden")
            self.query_one("#omnibox-container", OmniboxBar).add_class("hidden")
            dw = self.query_one("#draw-workspace", DrawWorkspace)
            dw.remove_class("hidden")
            if import_current and self._canvas_last_grid is not None:
                dw.import_grid(self._canvas_last_grid)
            elif trace_current and self._canvas_last_grid is not None:
                dw.trace_grid(self._canvas_last_grid)
            elif stencil is not None:
                dw.load_stencil(stencil)
            dw.focus_canvas()
        except Exception:
            pass
        self._sync_mode_tabs()
        self._update_canvas_meta(self._canvas_last_grid)
        self._set_status(
            "Type Mode: type directly · Alt+M mirror · Alt+A assist · Alt+P replay · ^D Studio"
        )

    def action_toggle_draw_mode(self):
        if self._active_mode == "draw":
            self.action_switch_studio()
        else:
            self.action_switch_draw()

    def import_studio_to_draw(self):
        """Load the current Studio artwork into the Type canvas for editing."""
        grid = self._canvas_last_grid
        if grid is None and self._canvas_image is not None:
            grid = self._grid_from_image(self._canvas_image, self._settings())
        if grid is None:
            self._set_status("[WARN] Nothing in Studio to import")
            return
        self.action_switch_draw(import_current=True)
        self._set_status("[OK] Imported Studio artwork into Type canvas")

    def trace_studio_in_draw(self):
        """Load the current Studio artwork as a dim ghost underlay to trace-type over."""
        grid = self._canvas_last_grid
        if grid is None and self._canvas_image is not None:
            grid = self._grid_from_image(self._canvas_image, self._settings())
        if grid is None:
            self._set_status("[WARN] Nothing in Studio to trace")
            return
        dw = self.query_one("#draw-workspace", DrawWorkspace)
        dw.trace_grid(grid)
        self._set_status("[OK] Studio art loaded as ghost stencil -- type over it!")

    def send_draw_to_studio(self):
        """Promote the typed terminal canvas into the Studio stage for animation & FX."""
        dw = self.query_one("#draw-workspace", DrawWorkspace)
        grid = dw.export_grid()
        self._canvas_image = None
        self._canvas_frames = []
        self._canvas_direct_grid = grid
        self._canvas_source_tag = "TYPE"
        self._canvas_label = f"Typed ASCII ({grid.width}x{grid.height})"
        self._push_art_history("TYPE", self._canvas_label, direct_grid=grid)
        self.action_switch_studio()
        self.query_one("#select-color", Checkbox).value = True
        self._render_canvas(animate=True)
        self._set_status("[OK] Typed ASCII art promoted to Studio")

    def _schedule_canvas_refit(self):
        if self._refit_timer is not None:
            try:
                self._refit_timer.stop()
            except Exception:
                pass
        self._refit_timer = self.set_timer(0.06, self._do_canvas_refit)

    def _do_canvas_refit(self):
        self._refit_timer = None
        if not self.is_mounted:
            return
        try:
            if self._settings().get("auto_fit", True) and self._webcam_task is None:
                self._render_canvas(animate=False)
        except NoMatches:
            return

    def _open_sidebar_exclusive(self):
        sidebar = self.query_one("#sidebar", Container)
        sidebar.add_class("open")
        if int(self.size.width or 120) < 115:
            self.query_one("#inspector", VerticalScroll).remove_class("open")
        self._schedule_canvas_refit()

    def action_open_palette(self):
        self.push_screen(CommandPaletteScreen())

    def action_toggle_sidebar(self):
        sidebar = self.query_one("#sidebar", Container)
        if sidebar.has_class("open"):
            sidebar.remove_class("open")
            self.query_one("#omnibox", Input).focus()
            self._schedule_canvas_refit()
        else:
            self._open_sidebar_exclusive()
            self.query_one("#file-list", ListView).focus()

    def action_toggle_inspector(self):
        inspector = self.query_one("#inspector", VerticalScroll)
        if inspector.has_class("open"):
            inspector.remove_class("open")
            if self._active_mode == "studio":
                self.query_one("#omnibox", Input).focus()
        else:
            if int(self.size.width or 120) < 115:
                self.query_one("#sidebar", Container).remove_class("open")
            inspector.add_class("open")
            try:
                self.query_one("#check-autofit", Checkbox).focus()
            except Exception:
                inspector.focus()
        self._schedule_canvas_refit()

    @staticmethod
    def _is_focusable(widget) -> bool:
        """True only when the widget and every ancestor are displayed and visible."""
        if widget is None:
            return False
        return all(
            bool(getattr(node, "display", True) and getattr(node, "visible", True))
            for node in widget.ancestors_with_self
        )

    def action_dismiss_overlay(self):
        if self._autocomplete_mode is not None:
            self._hide_autocomplete()
        else:
            for sel, cls in (
                ("#sidebar", "open"),
                ("#inspector", "open"),
                ("#log-drawer", "visible"),
            ):
                try:
                    w = self.query_one(sel)
                    if w.has_class(cls):
                        w.remove_class(cls)
                        self._schedule_canvas_refit()
                except Exception:
                    pass
        if self._active_mode == "draw":
            try:
                canvas = self.query_one("#draw-canvas", DrawCanvas)
            except Exception:
                canvas = None
            if self._is_focusable(canvas):
                canvas.focus()
            return
        try:
            omni = self.query_one("#omnibox", Input)
        except Exception:
            return
        if self._is_focusable(omni):
            omni.focus()

    def action_tab_files(self):
        self._open_sidebar_exclusive()
        self._switch_tab("tab-file")
        self.query_one("#file-list", ListView).focus()

    def action_tab_prompt(self):
        self._open_sidebar_exclusive()
        self._switch_tab("tab-prompt")
        self.query_one("#prompt-input", Input).focus()

    def action_tab_url(self):
        self._open_sidebar_exclusive()
        self._switch_tab("tab-url")
        self.query_one("#url-input", Input).focus()

    def action_tab_webcam(self):
        self._open_sidebar_exclusive()
        self._switch_tab("tab-webcam")

    def action_toggle_color(self):
        cb = self.query_one("#select-color", Checkbox)
        cb.value = not bool(cb.value)

    def action_zoom_in(self):
        self.query_one("#check-autofit", Checkbox).value = False
        inp = self.query_one("#input-width", Input)
        try:
            cur = int(inp.value or 80)
        except ValueError:
            cur = 80
        inp.value = str(min(240, cur + 10))
        self._sync_toolbar_buttons()
        self._render_canvas(animate=False)

    def action_zoom_out(self):
        self.query_one("#check-autofit", Checkbox).value = False
        inp = self.query_one("#input-width", Input)
        try:
            cur = int(inp.value or 80)
        except ValueError:
            cur = 80
        inp.value = str(max(16, cur - 10))
        self._sync_toolbar_buttons()
        self._render_canvas(animate=False)

    def action_zoom_autofit(self):
        cb = self.query_one("#check-autofit", Checkbox)
        cb.value = not bool(cb.value)

    def action_toggle_webcam(self):
        if self._webcam_task is not None:
            self._stop_webcam_preview()
            try:
                self.query_one("#cam-stats", Static).update("[IDLE] Camera stopped")
            except Exception:
                pass
            self._set_status("Webcam stopped")
            self._set_activity("webcam stopped")
        else:
            self._start_webcam_preview()

    def action_space_action(self):
        if self._webcam_task is not None:
            self._freeze_webcam_snapshot()
        elif (
            self.selected_kind == "video"
            and self.selected_file
            and os.path.isfile(self.selected_file)
        ):
            self._toggle_inline_video_playback()

    def action_copy_ascii(self):
        if self._active_mode == "draw":
            grid = self.query_one("#draw-workspace", DrawWorkspace).export_grid()
        else:
            grid = self._canvas_last_grid
            if grid is None and self._canvas_image is not None:
                grid = self._grid_from_image(self._canvas_image, self._settings())
        if grid is None:
            self._set_status("[WARN] Nothing on canvas to copy")
            return
        text = "\n".join(grid_lines(grid, color=False))
        if copy_text_to_clipboard(text):
            self._set_status(f"[OK] Copied {grid.width}x{grid.height} ASCII to clipboard")
            self._set_activity(f"[COPY] {grid.width}x{grid.height} copied to clipboard")
            self._log().write(f"[cyan][COPY] Copied {grid.width}x{grid.height} ASCII[/cyan]")
        else:
            self._set_status("[WARN] Clipboard unavailable on this system")

    def action_save_ascii(self):
        stem = os.path.splitext(os.path.basename(self._canvas_label or "ascii_art"))[0]
        clean_stem = (
            "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem).strip("_")
            or "ascii_art"
        )
        s = self._settings()
        # Pass the raw setting through: ExportScreen normalizes unsupported formats
        # to PNG and tells the user when a substitution happens.
        default_fmt = str(s.get("export") or "png").lower()
        self.push_screen(ExportScreen(default_name=clean_stem[:32], default_format=default_fmt))

    def action_refresh(self):
        self.query_one(FileBrowser).refresh_files()
        self._log().write("[dim]File list refreshed.[/dim]")

    def action_play(self):
        self.play_file()

    def action_webcam(self):
        self.run_webcam()

    def action_goto_path(self):
        self._open_sidebar_exclusive()
        self._switch_tab("tab-file")
        self.query_one("#dir-input", Input).focus()

    def action_focus_log(self):
        drawer = self.query_one("#log-drawer", Container)
        if drawer.has_class("visible"):
            drawer.remove_class("visible")
        else:
            drawer.add_class("visible")
            self.query_one("#log", RichLog).focus()
        self._schedule_canvas_refit()

    def action_paste_clipboard(self):
        focused = self.focused
        if isinstance(focused, Input) or any(
            isinstance(node, Input) for node in getattr(focused, "ancestors_with_self", ())
        ):
            # Textual Input handles Ctrl+V natively -- do not hijack it.
            return
        self.paste_clipboard()

    def action_toggle_fullscreen(self):
        """Close all drawers so the ASCII canvas occupies 100% of the workspace."""
        sidebar = self.query_one("#sidebar", Container)
        inspector = self.query_one("#inspector", VerticalScroll)
        if sidebar.has_class("open") or inspector.has_class("open"):
            sidebar.remove_class("open")
            inspector.remove_class("open")
        else:
            sidebar.add_class("open")
            if int(self.size.width or 120) >= 115:
                inspector.add_class("open")
        self._schedule_canvas_refit()

    def action_command_palette(self):
        """Show help overlay."""
        self.push_screen(HelpScreen())

    def action_toggle_theme(self):
        """Cycle to next theme."""
        self._current_theme = cycle_theme(self._current_theme)
        save_theme(self._current_theme)
        apply_theme(self, self._current_theme)
        self._update_omnibox_pills()
        try:
            self.query_one("#welcome-hero", WelcomeHero).update_logo(
                self._current_theme, phase=self._hero_phase
            )
        except Exception:
            pass
        self._log().write(f"[cyan]Theme: {self._current_theme}[/cyan]")
        self._set_status(f"Theme: {self._current_theme}")
        self._set_activity(f"[THEME] {self._current_theme}")

    def action_toggle_visualizer(self):
        """Toggle audio visualizer on/off."""
        if self._visualizer is not None:
            self._stop_visualizer()
            self._log().write("[dim]Visualizer: off[/dim]")
            self._render_canvas(animate=False)
        else:
            self._start_visualizer()
            self._log().write("[cyan]Visualizer: on (bars in preview)[/cyan]")

    def _start_visualizer(self):
        """Start audio visualizer for the selected video.

        Audio extraction shells out to ffmpeg (up to 60s), so it runs in a
        worker thread instead of blocking the Textual event loop.
        """
        self._stop_visualizer()
        if not self.selected_file or not os.path.isfile(self.selected_file):
            self._set_status("[WARN] Select a video before starting the visualizer")
            self._set_activity("[WARN] select a video first")
            return
        self._show_canvas_stage()
        self._visualizer_wanted = True
        self._set_activity("[VIZ] extracting audio...")
        self._start_spinner("extracting audio for visualizer")
        self._run_visualizer_worker(self.selected_file)

    @work(thread=True, exclusive=True, group="visualizer")
    def _run_visualizer_worker(self, path: str):
        try:
            audio_path = extract_audio(path)
            error = None
        except Exception as exc:  # defensive: ffmpeg missing/timeout
            audio_path, error = None, str(exc)
        self.call_from_thread(self._apply_visualizer_audio, path, audio_path, error)

    def _apply_visualizer_audio(self, path, audio_path, error):
        # Selection changed, or the user toggled the visualizer off, while
        # ffmpeg was still extracting -- discard the result.
        if not self._visualizer_wanted or path != self.selected_file:
            if audio_path:
                cleanup_audio(audio_path)
            self._stop_spinner()
            return
        if error or not audio_path:
            self._stop_spinner("[WARN] visualizer unavailable (no audio/ffmpeg)")
            self._set_status("[WARN] Visualizer unavailable: no audio track or ffmpeg")
            self._log().write("[yellow][VIZ] No audio track or ffmpeg missing[/yellow]")
            return
        self._visualizer_audio_path = audio_path
        viz = AudioVisualizer(audio_path, fps=30.0, mode="bars")
        if viz._data is None:
            cleanup_audio(audio_path)
            self._visualizer_audio_path = None
            self._stop_spinner("[WARN] visualizer unavailable (unreadable audio)")
            self._set_status("[WARN] Visualizer unavailable: could not read audio")
            return
        self._visualizer = viz
        self._visualizer_start = time.monotonic()

        def tick():
            if self._visualizer is None:
                return
            elapsed = time.monotonic() - self._visualizer_start
            viz_lines = self._visualizer.render(elapsed, 48)
            if viz_lines:
                self.query_one(InlinePreview).show_frame(viz_lines)

        self._visualizer_task = self.set_interval(0.1, tick)
        self._stop_spinner("[VIZ] bars active (V toggles off)")
        self._set_status("[VIZ] Visualizer on")
        self._log().write("[cyan][VIZ] Audio visualizer started[/cyan]")

    def _stop_visualizer(self):
        """Stop audio visualizer and remove any temporary extracted audio."""
        self._visualizer_wanted = False
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

    # ---- resize responsiveness ----

    def on_resize(self, event):
        self._apply_responsive_layout()
        if self._resize_timer is not None:
            try:
                self._resize_timer.stop()
            except Exception:
                pass
        self._resize_timer = self.set_timer(0.08, self._handle_resize_settled)

    def _handle_resize_settled(self):
        self._resize_timer = None
        if not self.is_mounted:
            return
        try:
            if self._settings().get("auto_fit", True) and self._webcam_task is None:
                self._render_canvas(animate=False)
        except NoMatches:
            return

    # ---- key handling for omnibox autocomplete & history ----

    def on_key(self, event: Key):
        omnibox = self.query_one("#omnibox", Input)
        if self.focused is not omnibox:
            return
        if self._autocomplete_mode is not None and self._autocomplete_items:
            popup = self.query_one("#autocomplete-popup", OptionList)
            cur = popup.highlighted if popup.highlighted is not None else 0
            if event.key == "down":
                popup.highlighted = min(len(self._autocomplete_items) - 1, cur + 1)
                event.stop()
            elif event.key == "up":
                popup.highlighted = max(0, cur - 1)
                event.stop()
            elif event.key == "tab":
                self._apply_autocomplete_index(cur, execute=False)
                event.stop()
            elif event.key == "escape":
                self._hide_autocomplete()
                event.stop()
            return

        if event.key == "up" and self._omnibox_history:
            if self._history_cursor < 0:
                self._history_cursor = len(self._omnibox_history) - 1
            else:
                self._history_cursor = max(0, self._history_cursor - 1)
            omnibox.value = self._omnibox_history[self._history_cursor]
            omnibox.cursor_position = len(omnibox.value)
            event.stop()
        elif event.key == "down" and self._omnibox_history and self._history_cursor >= 0:
            if self._history_cursor < len(self._omnibox_history) - 1:
                self._history_cursor += 1
                omnibox.value = self._omnibox_history[self._history_cursor]
            else:
                self._history_cursor = -1
                omnibox.value = ""
            omnibox.cursor_position = len(omnibox.value)
            event.stop()

    # ---- event handlers ----

    @on(Input.Changed, "#omnibox")
    def on_omnibox_changed(self, event):
        self._update_autocomplete(event.value)

    @on(Input.Submitted, "#omnibox")
    def on_omnibox_submitted(self, event):
        raw = (event.value or "").strip()
        if self._autocomplete_items and self._autocomplete_mode in ("at", "slash"):
            prefix = "@" if self._autocomplete_mode == "at" else "/"
            if raw.startswith(prefix):
                popup = self.query_one("#autocomplete-popup", OptionList)
                idx = popup.highlighted if popup.highlighted is not None else 0
                if 0 <= idx < len(self._autocomplete_items):
                    label, payload = self._autocomplete_items[idx]
                    raw = payload if self._autocomplete_mode == "at" else label
        self._hide_autocomplete()
        if not raw:
            return
        if not self._omnibox_history or self._omnibox_history[-1] != raw:
            self._omnibox_history.append(raw)
        self._history_cursor = -1
        event.input.value = ""
        self.submit_omnibox(raw)

    @on(OptionList.OptionSelected, "#autocomplete-popup")
    def on_autocomplete_selected(self, event):
        self._apply_autocomplete_index(event.option_index, execute=True)

    @on(Button.Pressed, "#btn-hero-1")
    def on_hero_1(self, event):
        self.generate_prompt_art(prompt="cyberpunk samurai cat")

    @on(Button.Pressed, "#btn-hero-2")
    def on_hero_2(self, event):
        self.generate_prompt_art(prompt="mount fuji at sunset")

    @on(Button.Pressed, "#btn-hero-3")
    def on_hero_3(self, event):
        self.action_toggle_webcam()

    @on(Button.Pressed, "#btn-hero-4")
    def on_hero_4(self, event):
        self.generate_prompt_art(prompt="ASCII STUDIO", engine="banner")

    @on(Button.Pressed, "#btn-hero-draw")
    def on_hero_draw(self, event):
        self.action_switch_draw(stencil="skull")

    @on(Button.Pressed, "#btn-mode-studio")
    def on_mode_studio_pressed(self, event):
        self.action_switch_studio()

    @on(Button.Pressed, "#btn-mode-draw")
    def on_mode_draw_pressed(self, event):
        self.action_switch_draw()

    @on(Button.Pressed, "#btn-edit-in-draw")
    def on_edit_in_draw_pressed(self, event):
        self.import_studio_to_draw()

    @on(Button.Pressed, "#btn-toggle-files")
    def on_toggle_files_pressed(self, event):
        self.action_toggle_sidebar()

    @on(Button.Pressed, "#btn-toggle-style")
    def on_toggle_style_pressed(self, event):
        self.action_toggle_inspector()

    @on(Button.Pressed, "#btn-open-palette")
    def on_open_palette_pressed(self, event):
        self.action_open_palette()

    @on(Input.Submitted, "#url-input")
    def on_url_submitted(self, event):
        self.load_url_source()

    @on(Button.Pressed, "#btn-load-url")
    def on_load_url_pressed(self, event):
        self.load_url_source()

    @on(Button.Pressed, "#btn-play-url")
    def on_play_url_pressed(self, event):
        self.play_url()

    @on(Button.Pressed, "#btn-paste-url")
    def on_paste_url_pressed(self, event):
        self.paste_clipboard()

    @on(Input.Submitted, "#prompt-input")
    def on_prompt_submitted(self, event):
        self.generate_prompt_art()

    @on(Button.Pressed, "#btn-generate")
    def on_generate_pressed(self, event):
        self.generate_prompt_art()

    @on(Button.Pressed, "#btn-surprise")
    def on_surprise_pressed(self, event):
        choice = random.choice(STARTER_PROMPTS)
        self.generate_prompt_art(prompt=choice)

    @on(ListView.Selected, "#prompt-presets")
    def on_prompt_preset_selected(self, event):
        prompt = getattr(event.item, "data_prompt", None)
        if prompt:
            self.generate_prompt_art(prompt=prompt)

    @on(Button.Pressed, "#btn-cam-toggle")
    def on_cam_toggle_pressed(self, event):
        self.action_toggle_webcam()

    @on(Button.Pressed, "#btn-cam-snap")
    def on_cam_snap_pressed(self, event):
        self._freeze_webcam_snapshot()

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

    @on(Button.Pressed, "#btn-color-toggle")
    def on_color_toggle_pressed(self, event):
        self.action_toggle_color()

    @on(Button.Pressed, "#btn-autofit")
    def on_autofit_pressed(self, event):
        self.action_zoom_autofit()

    @on(Button.Pressed, "#btn-copy-ascii")
    def on_copy_ascii_pressed(self, event):
        self.action_copy_ascii()

    @on(Button.Pressed, "#btn-export-now")
    def on_export_now_pressed(self, event):
        self.action_save_ascii()

    @on(Button.Pressed, "#btn-toggle-log")
    def on_toggle_log_pressed(self, event):
        self.action_focus_log()

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event):
        if self._loading_settings:
            return
        self._sync_toolbar_buttons()
        self._update_preview()
        if self._webcam_task is None:
            self._render_canvas(animate=False)

    @on(Select.Changed)
    def on_setting_changed(self, event):
        if self._loading_settings:
            return
        sid = event.select.id
        if sid in ("select-prompt-engine",):
            self._update_omnibox_pills()
            return
        if sid == "select-banner-font":
            if (
                self._canvas_source_tag == "PROMPT"
                and self._canvas_direct_grid is not None
                and self._last_prompt_text
                and self._last_prompt_engine == "banner"
            ):
                res = generate_banner(
                    self._last_prompt_text,
                    font=str(event.value or "slant"),
                    width=self._parse_width(self._settings()),
                )
                self._canvas_direct_grid = res.grid
                self._render_canvas(animate=False)
            return
        if sid == "select-cam-filter":
            return
        self._sync_toolbar_buttons()
        self._update_preview()
        if self._webcam_task is None:
            self._render_canvas(animate=False)

    @on(Input.Changed)
    def on_input_changed(self, event):
        if self._loading_settings or event.input.id == "omnibox":
            return
        iid = event.input.id
        if iid in ("input-width", "input-fps", "input-output", "input-aspect"):
            self._update_preview()
            self._sync_toolbar_buttons()
        if iid in (
            "input-width",
            "input-contrast",
            "input-brightness",
            "input-aspect",
            "input-charset",
        ):
            if self._input_render_timer is not None:
                try:
                    self._input_render_timer.stop()
                except Exception:
                    pass
            self._input_render_timer = self.set_timer(
                0.15, lambda: self._render_canvas(animate=False)
            )

    # ---- pop-out playback & clipboard ----

    def play_url(self):
        url = self.query_one("#url-input", Input).value.strip()
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
            return

        args = self._build_player_args(url)
        self._launch(
            args,
            f"[green]Playing:[/green] {url}",
            "[red]Failed to open terminal window[/red]",
            on_recent=url,
        )

    def play_file(self):
        if not self.selected_file:
            self._log().write(
                "[yellow]No media selected -- select a file, prompt, or URL first[/yellow]"
            )
            self._set_status("Nothing selected to pop-out")
            return

        name = self._selected_name()
        args = self._build_player_args(self.selected_file)
        self._launch(
            args,
            f"[green]Playing:[/green] {name}",
            "[red]Failed to open terminal window[/red]",
            on_recent=self.selected_file,
        )

    def _paste_text_into_canvas(self, canvas: DrawCanvas, text: str):
        """Type clipboard text into the visible Type canvas at its cursor."""
        line_start = canvas.cursor_x
        x, y = canvas.cursor_x, canvas.cursor_y
        canvas.model.push_undo()
        for ch in text:
            if ch in ("\n", "\r"):
                y = min(canvas.model.height - 1, y + 1)
                x = line_start
                continue
            canvas.model.type_char(x, y, ch, canvas.color, mirror=canvas.mirror)
            x += 1
            if x >= canvas.model.width:
                y = min(canvas.model.height - 1, y + 1)
                x = line_start
        canvas.cursor_x, canvas.cursor_y = x, y
        canvas.refresh()
        if self._is_focusable(canvas):
            canvas.focus()

    def paste_clipboard(self):
        pkg = sys.modules.get(__package__)
        get_cb_image = getattr(pkg, "clipboard_image")
        save_cb_image = getattr(pkg, "save_clipboard_image")
        get_cb_text = getattr(pkg, "clipboard_text")

        canvas = None
        if self._active_mode == "draw":
            try:
                canvas = self.query_one("#draw-canvas", DrawCanvas)
            except Exception:
                pass
            if not self._is_focusable(canvas):
                self._set_status("Clipboard paste needs the Type canvas")
                return

        image = get_cb_image()
        if image is not None:
            if canvas is not None:
                self._set_status("Type mode accepts text paste only")
                return
            try:
                path = save_cb_image(image)
            except Exception:
                self._log().write("[red]Could not save clipboard image[/red]")
                return
            self.query_one(FileBrowser).refresh_files()
            self.select_file(path, "image")
            self._canvas_source_tag = "CLIPBOARD"
            self._update_canvas_meta(self._canvas_last_grid)
            self._log().write(f"[green]Pasted image:[/green] {os.path.basename(path)}")
            self._set_status("Clipboard image ready")
            return
        text = get_cb_text()
        if text:
            text = text.strip()
            if canvas is not None:
                self._paste_text_into_canvas(canvas, text)
                self._set_status("Clipboard text pasted into Type canvas")
                return
            try:
                omni = self.query_one("#omnibox", Input)
            except Exception:
                return
            if not self._is_focusable(omni):
                return
            omni.value = text
            omni.cursor_position = len(text)
            omni.focus()
            if is_url(text):
                self._set_status("Clipboard URL pasted -- press Enter to load")
            else:
                self._set_status("Clipboard text pasted")
            return
        self._log().write("[yellow]Clipboard is empty or unavailable[/yellow]")
        self._set_status("Clipboard empty")

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
