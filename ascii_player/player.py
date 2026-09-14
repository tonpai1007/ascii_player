"""Video playback engine with refactored architecture."""

import os
import shutil
import sys
import time
from typing import Optional, Tuple, List

import cv2
import numpy as np
from loguru import logger

from .audio import cleanup_audio, extract_audio, play_audio, restart_audio, stop_audio
from .cache import FrameCache
from .config import PlayerConfig, Frame
from .controls import PlaybackControls
from .core import frame_to_ascii
from .exporter import ASCIIExporter, save_ascii_screenshot
from .lyrics import Lyrics, load_lyrics
from .renderer import FullscreenRenderer, SplitRenderer, Renderer
from .visualizer import AudioVisualizer


def get_terminal_size() -> Tuple[int, int]:
    """Get terminal dimensions.

    Returns:
        Tuple of (cols, rows)
    """
    cols, rows = shutil.get_terminal_size((80, 24))
    return cols, rows


class VideoPlayer:
    """Main video player class with separated concerns.
    
    This class handles video playback with ASCII conversion, managing
    all aspects of playback including audio, lyrics, controls, and export.
    """

    def __init__(
        self,
        video_path: str,
        config: PlayerConfig,
    ) -> None:
        """Initialize the video player.
        
        Args:
            video_path: Path to the video file
            config: Player configuration
        """
        self.video_path = video_path
        self.config = config
        
        # Video properties
        self.cap: Optional[cv2.VideoCapture] = None
        self.video_fps: float = 30.0
        self.total_frames: int = 0
        self.duration: float = 0.0
        self.fps: float = 30.0
        
        # Components
        self.controls: Optional[PlaybackControls] = None
        self.lyrics: Optional[Lyrics] = None
        self.renderer: Optional[Renderer] = None
        self.frame_cache: Optional[FrameCache] = None
        self.exporter: Optional[ASCIIExporter] = None
        
        # Audio
        self.audio_path: Optional[str] = None
        self.audio_process = None
        
        # Visualizer
        self.visualizer: Optional[AudioVisualizer] = None
        
        # Playback state
        self.frame_num: int = 0
        self.skipped: int = 0
        self.start_time: float = 0.0
        self.last_volume: int = 100
        self.paused_time: float = 0.0
        self._pause_start: float = 0.0
        self._total_paused: float = 0.0

    def play(self) -> None:
        """Start video playback.
        
        This is the main entry point that orchestrates the entire playback process.
        """
        self._validate_video()
        self._setup_video()
        self._setup_components()
        self._log_video_info()
        
        try:
            self._playback_loop()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self._cleanup()

    def _validate_video(self) -> None:
        """Validate that the video file exists and can be opened.
        
        Raises:
            SystemExit: If video file doesn't exist or can't be opened
        """
        if not os.path.exists(self.video_path):
            logger.error("File not found: {path}", path=self.video_path)
            raise SystemExit(1)

    def _setup_video(self) -> None:
        """Open the video file and extract metadata."""
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            logger.error("Cannot open video: {path}", path=self.video_path)
            raise SystemExit(1)

        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.video_fps
        self.fps = self.config.fps if self.config.fps else self.video_fps

    def _setup_components(self) -> None:
        """Initialize all playback components."""
        self._setup_controls()
        self._setup_lyrics()
        self._setup_audio()
        self._setup_visualizer()
        self._setup_cache()
        self._setup_exporter()
        self._setup_renderer()

    def _setup_controls(self) -> None:
        """Initialize playback controls."""
        self.controls = PlaybackControls()
        self.controls.start()

    def _setup_lyrics(self) -> None:
        """Load lyrics if specified."""
        if self.config.lyrics_path:
            self.lyrics = load_lyrics(self.config.lyrics_path)
            if self.lyrics and self.lyrics.lines:
                logger.info("Loaded lyrics: {n} lines", n=len(self.lyrics.lines))
            else:
                logger.warning("No lyrics found in file")
                self.lyrics = None

    def _setup_audio(self) -> None:
        """Extract and start audio playback."""
        if self.config.audio and not self.config.export:
            self.audio_path = extract_audio(self.video_path)
            if self.audio_path:
                self.audio_process = play_audio(self.audio_path)

    def _setup_visualizer(self) -> None:
        """Initialize audio visualizer if enabled."""
        if self.config.visualizer != "none" and self.audio_path:
            self.visualizer = AudioVisualizer(
                self.audio_path,
                fps=self.fps,
                mode=self.config.visualizer,
            )
            if self.visualizer._data is not None:
                logger.info("Visualizer: {mode}", mode=self.config.visualizer)
            else:
                self.visualizer = None

    def _setup_cache(self) -> None:
        """Initialize frame cache if enabled."""
        if self.config.cache:
            self.frame_cache = FrameCache()
            cached = self.frame_cache.load(
                self.video_path, 
                self.config.width, 
                self.config.color, 
                self.config.preset
            )
            if cached:
                logger.info("Using cached frames - faster playback!")
            else:
                self.frame_cache.set_cache_path(
                    self.video_path, 
                    self.config.width, 
                    self.config.color, 
                    self.config.preset
                )
                logger.info("Building cache for first run...")

    def _setup_exporter(self) -> None:
        """Initialize exporter if export is enabled."""
        if self.config.export:
            self.exporter = ASCIIExporter(self.config.width, int(self.fps))

    def _setup_renderer(self) -> None:
        """Setup the appropriate renderer based on configuration."""
        video_width = self.config.width
        lyrics_width = 0

        if self.lyrics and self.config.lyrics_mode == "split":
            cols, _ = get_terminal_size()
            lyrics_width = min(cols - self.config.width - 5, 50)
            video_width = cols - lyrics_width - 5
            self.renderer = SplitRenderer(video_width, lyrics_width)
        elif self.lyrics and self.config.lyrics_mode == "fullscreen":
            self.renderer = FullscreenRenderer(self.config.width)

    def _log_video_info(self) -> None:
        """Log video metadata and playback settings."""
        if not self.cap:
            return
            
        logger.info("Opening: {path}", path=os.path.basename(self.video_path))
        logger.info(
            "Resolution: {w}x{h}",
            w=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            h=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        logger.info(
            "FPS: {fps:.1f} | Frames: {frames} | Duration: {dur:.1f}s",
            fps=self.video_fps,
            frames=self.total_frames,
            dur=self.duration
        )
        logger.info(
            "Playback: {pfps:.1f} FPS | Width: {w} chars | Preset: {p} | Color: {c}",
            pfps=self.fps,
            w=self.config.width,
            p=self.config.preset,
            c=self.config.color
        )
        
        if self.config.cache:
            logger.info("Cache: enabled")
        if self.config.export:
            logger.info("Export: {fmt} mode", fmt=self.config.export.upper())
        if self.lyrics:
            logger.info("Lyrics: synced ({n} lines)", n=len(self.lyrics.lines))
        
        if self.controls:
            logger.info("Controls: [Space] Pause [Q] Quit [+/-] Speed [Arrows] Seek")
        else:
            logger.info("Controls: [Ctrl+C] to quit")

    def _playback_loop(self) -> None:
        """Main playback loop."""
        self.frame_num = 0
        self.skipped = 0
        self.start_time = time.time()
        self._pause_start = 0.0
        self._total_paused = 0.0
        self.last_volume = self.controls.get_volume() if self.controls else 100

        # Clear screen
        print("\033[2J\033[H", end="", flush=True)

        while self.frame_num < self.total_frames:
            if self._should_quit():
                break

            if self._is_paused():
                if self._pause_start == 0.0:
                    self._pause_start = time.time()
                time.sleep(0.1)
                continue

            if self._pause_start != 0.0:
                self._total_paused += time.time() - self._pause_start
                self._pause_start = 0.0

            if self._handle_seek():
                continue

            current_time = self._get_current_time()
            self._update_controls(current_time)
            self._handle_ab_loop(current_time)

            frame_start = time.time()
            ascii_frame = self._get_frame()

            if ascii_frame is None:
                break

            self._handle_screenshot(ascii_frame)
            self._handle_export(ascii_frame, current_time)

            if not self.config.export:
                self._render_frame(ascii_frame, current_time)
                self._handle_timing(frame_start)

            self._log_progress()
            self.frame_num += 1

    def _should_quit(self) -> bool:
        """Check if playback should stop."""
        return self.controls.should_quit() if self.controls else False

    def _is_paused(self) -> bool:
        """Check if playback is paused."""
        return self.controls.is_paused() if self.controls else False

    def _handle_seek(self) -> bool:
        """Handle seek operations.
        
        Returns:
            True if a seek was performed
        """
        if not self.controls:
            return False
            
        seek = self.controls.get_seek()
        if seek != 0:
            seek_frames = int(seek * self.fps)
            self.frame_num = max(0, min(self.total_frames - 1, self.frame_num + seek_frames))
            if self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_num)
            time.sleep(1.0 / self.fps)
            return True
        return False

    def _get_current_time(self) -> float:
        """Get current playback time in seconds."""
        return self.frame_num / self.video_fps

    def _update_controls(self, current_time: float) -> None:
        """Update control state."""
        if not self.controls:
            return
            
        self.controls.set_current_time(current_time)

        if self.audio_process:
            new_volume = self.controls.get_volume()
            if new_volume != self.last_volume:
                self.last_volume = new_volume
                self.audio_process = restart_audio(self.audio_process, self.audio_path, new_volume)

    def _handle_ab_loop(self, current_time: float) -> None:
        """Handle A-B loop functionality."""
        if not self.controls:
            return
            
        ab_lo, ab_hi = self.controls.ab_bounds()
        if ab_lo is not None and ab_hi is not None and self.controls.is_ab_loop_enabled():
            if current_time >= ab_hi:
                self.frame_num = int(ab_lo * self.video_fps)
                if self.cap:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_num)
                time.sleep(1.0 / self.fps)

    def _get_video_width(self) -> int:
        """Get the effective video width for ASCII conversion."""
        if self.renderer and hasattr(self.renderer, 'video_width'):
            return self.renderer.video_width
        return self.config.width

    def _get_frame(self) -> Optional[Frame]:
        """Get the next frame as ASCII art.
        
        Returns:
            ASCII frame or None if no more frames
        """
        if self.frame_cache and self.frame_cache.has_frame(self.frame_num):
            return self.frame_cache.get_frame(self.frame_num)

        if not self.cap:
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        video_width = self._get_video_width()
        ascii_frame = frame_to_ascii(
            frame, 
            video_width, 
            self.config.color, 
            self.config.preset
        )

        if self.frame_cache:
            self.frame_cache.add_frame(self.frame_num, ascii_frame)

        return ascii_frame

    def _handle_screenshot(self, ascii_frame: Frame) -> None:
        """Handle screenshot requests."""
        if self.controls and self.controls.pop_screenshot_request():
            video_width = self._get_video_width()
            save_ascii_screenshot(ascii_frame, self.frame_num, video_width, self.config.color)

    def _handle_export(self, ascii_frame: Frame, current_time: float) -> None:
        """Handle frame export."""
        if self.exporter:
            lyrics_context = None
            if self.lyrics:
                lyrics_context = self.lyrics.get_context_lines(current_time)
            self.exporter.add_frame(ascii_frame, self.frame_num, current_time, lyrics_context)

    def _render_frame(self, ascii_frame: Frame, current_time: float) -> None:
        """Render a frame to the terminal."""
        lines: List[str] = []

        if self.renderer and self.lyrics:
            lyrics_context = self.lyrics.get_context_lines(current_time)
            if isinstance(self.renderer, SplitRenderer):
                lines = self.renderer.render(ascii_frame, lyrics_context, current_time)
            elif isinstance(self.renderer, FullscreenRenderer):
                lines = self.renderer.render(lyrics_context, current_time)
        else:
            frame_interval = 1.0 / self.fps
            lines = _build_plain_frame_lines(
                ascii_frame,
                self._get_video_width(),
                self.frame_num,
                self.total_frames,
                frame_interval,
                self.duration,
                self.controls,
            )

        if self.visualizer:
            viz_lines = self.visualizer.render(current_time, self._get_video_width())
            if viz_lines:
                lines.append("")
                lines.extend(viz_lines)

        _write_frame("\033[H", lines)

    def _handle_timing(self, frame_start: float) -> None:
        """Handle frame timing and sleep."""
        frame_interval = 1.0 / self.fps
        speed = self.controls.get_speed() if self.controls else 1.0
        target = (
            self.start_time
            + self._total_paused
            + (self.frame_num + 1) * frame_interval / speed
        )
        sleep_time = target - time.time()

        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            self.skipped += 1

    def _log_progress(self) -> None:
        """Log playback progress periodically."""
        if self.frame_num % 50 == 0:
            elapsed = time.time() - self.start_time
            actual_fps = self.frame_num / elapsed if elapsed > 0 else 0
            logger.debug(
                "Frame {f}/{t} | {fps:.1f} actual FPS | {skip} skipped",
                f=self.frame_num,
                t=self.total_frames,
                fps=actual_fps,
                skip=self.skipped
            )

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self.controls:
            self.controls.stop()

        if self.cap:
            self.cap.release()

        stop_audio(self.audio_process)
        cleanup_audio(self.audio_path)

        if self.frame_cache:
            self.frame_cache.save()

        if self.exporter:
            self._handle_export_cleanup()

        self._log_final_stats()

    def _handle_export_cleanup(self) -> None:
        """Handle export file creation."""
        if not self.exporter:
            return
            
        output = self.config.export_output or f"output.{self.config.export}"
        if self.config.export == "gif":
            self.exporter.export_gif(output)
        elif self.config.export == "mp4":
            self.exporter.export_mp4(output)
        self.exporter.cleanup()

    def _log_final_stats(self) -> None:
        """Log final playback statistics."""
        elapsed = time.time() - self.start_time
        actual_fps = self.frame_num / elapsed if elapsed > 0 else 0
        logger.info(
            "Finished: {f}/{t} frames in {e:.1f}s ({fps:.1f} FPS, {s} skipped)",
            f=self.frame_num,
            t=self.total_frames,
            e=elapsed,
            fps=actual_fps,
            s=self.skipped
        )
        print(f"\n\033[1;32mDone. Played {self.frame_num}/{self.total_frames} frames in {elapsed:.1f}s\033[0m")


def _write_frame(prefix: str, lines: List[str]) -> None:
    """Write a redraw prefix + frame lines in a single buffered stdout call."""
    sys.stdout.write(prefix)
    if lines:
        sys.stdout.write("\n".join(lines))
        sys.stdout.write("\n")
    sys.stdout.flush()


_BORDER_CACHE: dict = {}


def _build_plain_frame_lines(
    ascii_frame: Frame,
    width: int,
    frame_num: int,
    total_frames: int,
    frame_interval: float,
    duration: float,
    controls: Optional[PlaybackControls] = None
) -> List[str]:
    """Build plain frame lines without writing to stdout.

    The top/bottom border and control bar are static per width/has-controls,
    so they are cached and reused across frames.
    """
    cache_key = (width, controls is not None)
    static = _BORDER_CACHE.get(cache_key)
    if static is None:
        border = f"\033[1;36m{'=' * width}\033[0m"
        if controls:
            bar, status_line_template = controls.render_controls(width)
            # status_line_template is static, but frame status is appended
            static = [border, bar, f"{status_line_template} | "]
        else:
            static = [border, "\033[1;33m"]
        _BORDER_CACHE.clear()
        _BORDER_CACHE[cache_key] = static

    lines: List[str] = [static[0]]
    lines.extend(ascii_frame)
    lines.append(static[0])

    status = (
        f"Frame {frame_num + 1}/{total_frames} | "
        f"{frame_num * frame_interval:.1f}s / {duration:.1f}s"
    )

    if controls:
        lines.append(static[1])
        lines.append(static[2] + status)
    else:
        lines.append(static[1] + status + "\033[0m")

    return lines


def _write_plain_frame(
    ascii_frame: Frame,
    width: int,
    frame_num: int,
    total_frames: int,
    frame_interval: float,
    duration: float,
    controls: Optional[PlaybackControls] = None
) -> None:
    """Render a single ASCII frame to terminal in one write."""
    lines = _build_plain_frame_lines(
        ascii_frame, width, frame_num, total_frames, frame_interval, duration, controls
    )
    _write_frame("\033[H", lines)


# Legacy function for backward compatibility
def play_video(
    video_path: str,
    width: int = 80,
    fps: Optional[float] = None,
    color: bool = False,
    preset: str = "classic",
    audio: bool = True,
    cache: bool = False,
    export: Optional[str] = None,
    export_output: Optional[str] = None,
    lyrics_path: Optional[str] = None,
    lyrics_mode: str = "split",
    controls: bool = True,
    visualizer: str = "none"
) -> None:
    """Play a video file as ASCII art in the terminal.
    
    This is a legacy wrapper around VideoPlayer for backward compatibility.
    
    Args:
        video_path: Path to video file
        width: ASCII output width in characters
        fps: Playback FPS (None for auto)
        color: Enable ANSI truecolor output
        preset: ASCII character preset name
        audio: Enable audio playback
        cache: Enable frame caching
        export: Export format (None, "gif", "mp4")
        export_output: Output file path for export
        lyrics_path: Path to lyrics file
        lyrics_mode: Lyrics display mode ("split", "fullscreen", "none")
        controls: Enable keyboard controls
        visualizer: Audio visualizer mode ("none", "bars", "wave")
    """
    config = PlayerConfig(
        width=width,
        color=color,
        preset=preset,
        audio=audio,
        fps=fps,
        export=export,
        export_output=export_output,
        lyrics_path=lyrics_path,
        lyrics_mode=lyrics_mode,
        cache=cache,
        visualizer=visualizer,
    )
    
    player = VideoPlayer(video_path, config)
    player.play()