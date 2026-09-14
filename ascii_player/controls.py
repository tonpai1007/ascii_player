"""Keyboard controls for video playback with Command pattern."""

import sys
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

from loguru import logger


class Command(ABC):
    """Abstract base class for playback commands."""

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        pass


class TogglePauseCommand(Command):
    """Toggle pause state."""

    def __init__(self, controls: 'PlaybackControls') -> None:
        self.controls = controls

    def execute(self) -> None:
        self.controls.paused = not self.controls.paused
        state = "PAUSED" if self.controls.paused else "PLAYING"
        logger.info("Playback: {state}", state=state)


class QuitCommand(Command):
    """Request quit."""

    def __init__(self, controls: 'PlaybackControls') -> None:
        self.controls = controls

    def execute(self) -> None:
        self.controls.quit = True
        logger.info("Quit requested")


class ChangeSpeedCommand(Command):
    """Change playback speed."""

    def __init__(self, controls: 'PlaybackControls', delta: float) -> None:
        self.controls = controls
        self.delta = delta

    def execute(self) -> None:
        self.controls.speed = max(0.25, min(3.0, self.controls.speed + self.delta))
        logger.info("Speed: {speed:.2f}x", speed=self.controls.speed)


class ChangeVolumeCommand(Command):
    """Change volume."""

    def __init__(self, controls: 'PlaybackControls', delta: int) -> None:
        self.controls = controls
        self.delta = delta

    def execute(self) -> None:
        self.controls.volume = max(0, min(200, self.controls.volume + self.delta))
        logger.info("Volume: {v}%", v=self.controls.volume)


class SetABPointCommand(Command):
    """Set A-B loop point."""

    def __init__(self, controls: 'PlaybackControls', point: str) -> None:
        self.controls = controls
        self.point = point

    def execute(self) -> None:
        if self.point == 'a':
            self.controls._ab_start = self.controls._ab_current
            logger.info("A-B loop: point A set at {t:.1f}s", t=(self.controls._ab_start or 0))
        else:
            self.controls._ab_end = self.controls._ab_current
            logger.info("A-B loop: point B set at {t:.1f}s", t=(self.controls._ab_end or 0))


class ToggleABLoopCommand(Command):
    """Toggle A-B loop enabled state."""

    def __init__(self, controls: 'PlaybackControls') -> None:
        self.controls = controls

    def execute(self) -> None:
        self.controls._ab_enabled = not self.controls._ab_enabled
        logger.info("A-B loop: {state}", state="ON" if self.controls._ab_enabled else "OFF")


class RequestScreenshotCommand(Command):
    """Request a screenshot."""

    def __init__(self, controls: 'PlaybackControls') -> None:
        self.controls = controls

    def execute(self) -> None:
        self.controls._snap_flags |= 1
        logger.info("Screenshot requested")


class SeekCommand(Command):
    """Seek forward or backward."""

    def __init__(self, controls: 'PlaybackControls', amount: int) -> None:
        self.controls = controls
        self.amount = amount

    def execute(self) -> None:
        self.controls.seek_amount = self.amount
        logger.info("Seek: {s}s", s=self.amount)


class PlaybackControls:
    """Handle keyboard input for playback control using Command pattern."""

    def __init__(self) -> None:
        self.paused: bool = False
        self.speed: float = 1.0
        self.seek_amount: int = 0
        self.quit: bool = False
        self.volume: int = 100
        self._ab_enabled: bool = False
        self._ab_start: Optional[float] = None
        self._ab_end: Optional[float] = None
        self._ab_current: float = 0.0
        self._screenshot_requested: bool = False
        self._snap_flags: int = 0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Command mappings
        self._key_commands: Dict[str, Command] = {
            ' ': TogglePauseCommand(self),
            'q': QuitCommand(self),
            '+': ChangeSpeedCommand(self, 0.25),
            '=': ChangeSpeedCommand(self, 0.25),
            '-': ChangeSpeedCommand(self, -0.25),
            '[': ChangeVolumeCommand(self, -10),
            ']': ChangeVolumeCommand(self, 10),
            'a': SetABPointCommand(self, 'a'),
            'b': SetABPointCommand(self, 'b'),
            'l': ToggleABLoopCommand(self),
            's': RequestScreenshotCommand(self),
        }

    def start(self) -> None:
        """Start listening for keyboard input."""
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._windows_input, daemon=True)
        else:
            self._thread = threading.Thread(target=self._unix_input, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening."""
        with self._lock:
            self.quit = True
        if self._thread:
            self._thread.join(timeout=1)

    def _windows_input(self) -> None:
        """Handle input on Windows."""
        try:
            import msvcrt
            while not self.quit:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    self._process_key(key)
                time.sleep(0.01)
        except ImportError:
            logger.warning("msvcrt not available - keyboard controls disabled")

    def _unix_input(self) -> None:
        """Handle input on Unix."""
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                tty.setraw(fd)
                while not self.quit:
                    if sys.stdin.readable():
                        char = sys.stdin.read(1)
                        if char:
                            self._process_key(char.encode())
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception as e:
            logger.warning("Unix input error: {err}", err=str(e))

    def _process_key(self, key: bytes) -> None:
        """Process a key press using Command pattern.
        
        Args:
            key: Key bytes
        """
        with self._lock:
            if isinstance(key, bytes):
                key = key.decode("utf-8", errors="ignore")

            # Check for regular key commands
            command = self._key_commands.get(key)
            if command:
                command.execute()
            elif key == "\x1b":
                self._handle_escape_sequence()

    def _handle_escape_sequence(self) -> None:
        """Handle escape sequences (arrow keys) with a short timeout."""
        if sys.platform != "win32":
            import select
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not ready:
                return

        if sys.stdin.readable():
            seq = sys.stdin.read(2)
            if seq == "[C":
                SeekCommand(self, 5).execute()
            elif seq == "[D":
                SeekCommand(self, -5).execute()

    def set_current_time(self, current_time: float) -> None:
        """Track current playback time (used for A-B loop points)."""
        with self._lock:
            self._ab_current = current_time

    def get_volume(self) -> int:
        """Get current volume (0-200%).
        
        Returns:
            Current volume level
        """
        with self._lock:
            return self.volume

    def get_speed(self) -> float:
        """Get current playback speed.
        
        Returns:
            Current speed multiplier
        """
        with self._lock:
            return self.speed

    def is_paused(self) -> bool:
        """Check if playback is paused.
        
        Returns:
            True if paused
        """
        with self._lock:
            return self.paused

    def should_quit(self) -> bool:
        """Check if quit was requested.
        
        Returns:
            True if quit requested
        """
        with self._lock:
            return self.quit

    def pop_screenshot_request(self) -> bool:
        """Consume a screenshot request flag.
        
        Returns:
            True if screenshot was requested (flag reset)
        """
        with self._lock:
            requested = (self._snap_flags & 1) != 0
            self._snap_flags &= ~1
            return requested

    def is_ab_loop_enabled(self) -> bool:
        """Check if A-B loop is on.
        
        Returns:
            True if A-B loop enabled
        """
        with self._lock:
            return self._ab_enabled

    def set_ab_points(self, start: Optional[float] = None, end: Optional[float] = None) -> None:
        """Manually set A-B points (for TUI integration).
        
        Args:
            start: Start time in seconds
            end: End time in seconds
        """
        with self._lock:
            if start is not None:
                self._ab_start = start
            if end is not None:
                self._ab_end = end

    def ab_bounds(self) -> Tuple[Optional[float], Optional[float]]:
        """Get current A-B loop bounds.
        
        Returns:
            Tuple (start, end) or (None, None) if loop not fully set
        """
        with self._lock:
            if self._ab_start is not None and self._ab_end is not None:
                if self._ab_start != self._ab_end:
                    lo, hi = sorted((self._ab_start, self._ab_end))
                    return lo, hi
            return None, None

    def get_seek(self) -> int:
        """Get and reset seek amount.
        
        Returns:
            Seek amount in seconds
        """
        with self._lock:
            amount = self.seek_amount
            self.seek_amount = 0
            return amount

    def render_controls(self, width: int) -> Tuple[str, str]:
        """Render control overlay.
        
        Args:
            width: Output width
            
        Returns:
            Tuple of (control bar string, status line string)
        """
        with self._lock:
            state = "PAUSED" if self.paused else "PLAYING"
            speed = f"{self.speed:.2f}x"
            volume = f"{self.volume}%"
            loop = "ON" if self._ab_enabled else "OFF"

        controls = (
            "[Space] Pause/Play  [Q] Quit  [+/-] Speed  [Arrows] Seek  "
            "[/] Volume  [A/B/L] Loop  [S] Shot"
        )
        status = f"State: {state} | Speed: {speed} | Vol: {volume} | Loop: {loop}"

        bar = f"\033[1;37m{controls}\033[0m"
        status_line = f"\033[1;33m{status}\033[0m"

        return bar, status_line
