"""Split-screen renderer for video + lyrics display with Strategy pattern."""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

from .config import Frame


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

            left = left[:self.video_width].ljust(self.video_width)
            right = right[:self.lyrics_width].ljust(self.lyrics_width)

            output.append(f"{left} │ {right}")

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
        bar_width = self.total_width - len(time_str) - 4
        filled = int(bar_width * (current / duration)) if duration > 0 else 0
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
                formatted = f"\033[1;32m{'':^{self.width}}\033[0m"
                formatted += f"\n\033[1;33m  ♪ {text} ♪\033[0m"
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