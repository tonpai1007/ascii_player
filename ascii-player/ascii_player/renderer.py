"""Split-screen renderer for video + lyrics display with Strategy pattern."""

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Tuple, Optional

from .config import Frame

if TYPE_CHECKING:
    from .lyrics import LyricsLine

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Length of a string ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def _truncate_visible(text: str, width: int) -> str:
    """Truncate to ``width`` visible characters, keeping ANSI sequences."""
    if width <= 0:
        return ""
    out: List[str] = []
    visible = 0
    i = 0
    while i < len(text):
        match = _ANSI_RE.match(text, i)
        if match:
            out.append(match.group(0))
            i = match.end()
            continue
        if visible >= width:
            break
        out.append(text[i])
        visible += 1
        i += 1
    if visible >= width and "\x1b[" in text:
        out.append("\033[0m")
    return "".join(out)


def _pad_visible(text: str, width: int) -> str:
    """Right-pad a string to ``width`` visible characters."""
    return text + " " * max(0, width - _visible_len(text))


def _fit(text: str, width: int) -> str:
    """Truncate and pad to an exact visible width."""
    return _pad_visible(_truncate_visible(text, width), width)


class Renderer(ABC):
    """Abstract base class for renderers (Strategy pattern)."""
    
    @abstractmethod
    def render(self, *args, **kwargs) -> List[str]:
        """Render the output.
        
        Returns:
            List of strings to display
        """
        pass


class SplitRenderer(Renderer):
    """Render ASCII video and lyrics side by side."""

    def __init__(self, video_width: int = 60, lyrics_width: int = 40) -> None:
        """Initialize split renderer.

        Args:
            video_width: Width for video section
            lyrics_width: Width for lyrics section
        """
        self.video_width = video_width
        self.lyrics_width = lyrics_width
        self.total_width = video_width + lyrics_width + 3

    def render(
        self, 
        ascii_frame: Frame, 
        lyrics_context: List[Tuple['LyricsLine', bool]], 
        current_time: float, 
        progress: int = 0
    ) -> List[str]:
        """Render split-screen view.

        Args:
            ascii_frame: ASCII video frame (list of strings)
            lyrics_context: List of (line, is_current) tuples
            current_time: Current playback time
            progress: Playback progress (0-1)

        Returns:
            List of strings to print
        """
        output: List[str] = []
        video_lines = len(ascii_frame)
        lyrics_lines = self._prepare_lyrics(lyrics_context)

        max_lines = max(video_lines, len(lyrics_lines))

        for i in range(max_lines):
            left = ascii_frame[i] if i < video_lines else " " * self.video_width
            right = lyrics_lines[i] if i < len(lyrics_lines) else " " * self.lyrics_width

            output.append(f"{_fit(left, self.video_width)} │ {_fit(right, self.lyrics_width)}")

        return output

    def _prepare_lyrics(self, lyrics_context: List[Tuple['LyricsLine', bool]]) -> List[str]:
        """Prepare lyrics lines for display.

        Args:
            lyrics_context: List of (line, is_current) tuples

        Returns:
            List of formatted strings
        """
        lines: List[str] = []
        for line, is_current in lyrics_context:
            text = line.text[:self.lyrics_width - 2]
            if is_current:
                formatted = f"\033[1;33m► {text}\033[0m"
            else:
                formatted = f"  {text}"
            lines.append(formatted)
        return lines

    def render_header(
        self, 
        title: str = "", 
        artist: str = "", 
        duration: float = 0, 
        current: float = 0
    ) -> List[str]:
        """Render header with song info.

        Args:
            title: Song title
            artist: Artist name
            duration: Total duration
            current: Current time

        Returns:
            List of strings
        """
        lines: List[str] = []

        if title:
            info = f"♪ {title}"
            if artist:
                info += f" - {artist}"
            lines.append(f"\033[1;35m{info}\033[0m")

        time_str = f"{current:.0f}s / {duration:.0f}s"
        bar_width = max(0, self.total_width - len(time_str) - 4)
        filled = int(bar_width * (current / duration)) if duration > 0 else 0
        filled = max(0, min(bar_width, filled))
        bar = "█" * filled + "░" * (bar_width - filled)
        lines.append(f"\033[1;36m{bar}\033[0m {time_str}")

        return lines

    def render_footer(self, controls: bool = True) -> List[str]:
        """Render footer with controls.

        Args:
            controls: Show controls

        Returns:
            List of strings
        """
        if controls:
            return ["\033[90m[Space] Pause  [←→] Seek  [Q] Quit\033[0m"]
        return []


class FullscreenRenderer(Renderer):
    """Render full-screen lyrics display."""

    def __init__(self, width: int = 80) -> None:
        """Initialize fullscreen renderer.

        Args:
            width: Total width
        """
        self.width = width

    def render(
        self, 
        lyrics_context: List[Tuple['LyricsLine', bool]], 
        current_time: float
    ) -> List[str]:
        """Render full-screen lyrics.

        Args:
            lyrics_context: List of (line, is_current) tuples
            current_time: Current playback time

        Returns:
            List of strings to print
        """
        output: List[str] = []
        padding = 5

        for _ in range(padding):
            output.append("")

        for line, is_current in lyrics_context:
            text = line.text
            if len(text) > self.width - 4:
                text = text[:self.width - 7] + "..."

            if is_current:
                output.append("")
                output.append(f"\033[1;33m{'♪ ' + text + ' ♪':^{self.width}}\033[0m")
            else:
                formatted = f"\033[90m{text:^{self.width}}\033[0m"
                output.append(formatted)

        for _ in range(padding):
            output.append("")

        return output


class RendererFactory:
    """Factory for creating renderers based on mode."""

    @staticmethod
    def create(mode: str, **kwargs) -> Optional[Renderer]:
        """Create a renderer based on the mode.
        
        Args:
            mode: Renderer mode ("split", "fullscreen")
            **kwargs: Additional arguments for the renderer
            
        Returns:
            Renderer instance or None
        """
        if mode == "split":
            return SplitRenderer(
                video_width=kwargs.get('video_width', 60),
                lyrics_width=kwargs.get('lyrics_width', 40)
            )
        elif mode == "fullscreen":
            return FullscreenRenderer(width=kwargs.get('width', 80))
        return None