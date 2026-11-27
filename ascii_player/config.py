"""Configuration and constants for ASCII Video Player."""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

COLOR_RESET = "\033[0m"

ASCII_PRESETS = {
    "classic": " .:-=+*#%@",
    "blocks": " ░▒▓█",
    "dots": " ·•●",
    "binary": " 01",
    "simple": " .oO0",
    "detailed": " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "unicode": " ▁▂▃▄▅▆▇█",
    "braille": " ⠁⠂⠃⠄⠅⠆⠇⠈⠉⠊⠋⠌⠍⠎⠏⠐⠑⠒⠓⠔⠕⠖⠗⠘⠙⠚⠛⠜⠝⠞⠟⠠⠡⠢⠣⠤⠥⠦⠧⠨⠩⠪⠫⠬⠭⠮⠯⠰⠱⠲⠳⠴⠵⠶⠷⠸⠹⠺⠻⠼⠽⠾⠿",
    "matrix": " .,:;01#$@",
    "hatch": " .-/\\|+xX#@",
    "halfblock": " ▀▄█",
    "braille_hd": " ⠁⠃⠇⠏⠟⠿⣿",
    "edge_art": " .-:/\\|+xX#@",
}

FILTER_MODES = (
    "none",
    "edge",
    "invert",
    "mirror",
    "emboss",
    "sharpen",
    "contour",
    "posterize",
    "colorcycle",
)

POST_FX_MODES = (
    "scanlines",
    "chromatic",
    "vignette",
    "bloom",
    "halftone",
    "glitch",
)

PROMPT_ENGINES = ("auto", "ai", "web", "ollama", "banner", "procedural")

DEFAULT_PRESET = "classic"
DEFAULT_WIDTH = 80
DEFAULT_FPS = None
DEFAULT_COLOR = False
DEFAULT_AUDIO = True

LOG_FORMAT = "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}"
LOG_FILE = "ascii_player.log"
LOG_ROTATION = "5 MB"
LOG_RETENTION = "7 days"

YOUTUBE_REGEX = r'(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|youtube\.com/watch\?v=|youtube\.com/shorts/)'
YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
)
YOUTUBE_MAX_HEIGHT = 720
YOUTUBE_TIMEOUT = 300

EXPORT_FORMATS = ("gif", "mp4", "txt", "ans", "html", "png")
LYRICS_MODES = ("split", "fullscreen", "none")
VISUALIZER_MODES = ("none", "bars", "wave")


def is_safe_youtube_url(url: Any) -> bool:
    """Return True only for exact YouTube hostnames (never suffix/prefix lookalikes).

    ``YOUTUBE_REGEX`` matches prefixes such as ``youtube.com.evil.com``; use this
    helper for any security-relevant host decision.
    """
    try:
        parsed = urlparse(str(url or "").strip())
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    return parsed.netloc.lower() in YOUTUBE_HOSTS

CONFIG_FILE = "ascii_player.yaml"
DEFAULT_CONFIG: Dict[str, Any] = {
    "width": DEFAULT_WIDTH,
    "fps": DEFAULT_FPS,
    "color": DEFAULT_COLOR,
    "audio": DEFAULT_AUDIO,
    "preset": DEFAULT_PRESET,
}


@dataclass
class PlayerConfig:
    """Configuration for video playback.

    Attributes:
        width: ASCII output width in characters
        color: Enable ANSI truecolor output
        preset: ASCII character preset name
        audio: Enable audio playback
        fps: Playback FPS (None for auto)
        export: Export format (None or one of EXPORT_FORMATS)
        export_output: Output file path for export
        lyrics_path: Path to lyrics file
        lyrics_mode: Lyrics display mode ("split", "fullscreen", "none")
        cache: Enable frame caching
        webcam: Enable webcam mode
        camera_index: Camera device index
    """
    width: int = 80
    color: bool = False
    preset: str = "classic"
    audio: bool = True
    fps: Optional[float] = None
    export: Optional[str] = None
    export_output: Optional[str] = None
    lyrics_path: Optional[str] = None
    lyrics_mode: str = "split"
    cache: bool = False
    webcam: bool = False
    camera_index: int = 0
    visualizer: str = "none"
    controls: bool = True

    @classmethod
    def from_args(cls, args: Any) -> "PlayerConfig":
        """Create config from parsed command line arguments.

        Args:
            args: Parsed argparse namespace

        Returns:
            PlayerConfig instance
        """
        return cls(
            width=getattr(args, "width", 80),
            color=getattr(args, "color", False),
            preset=getattr(args, "preset", None) or "classic",
            audio=not getattr(args, "no_audio", False),
            fps=getattr(args, "fps", None),
            export=getattr(args, "export", None),
            export_output=getattr(args, "output", None),
            lyrics_path=getattr(args, "lyrics", None),
            lyrics_mode=getattr(args, "lyrics_mode", "split"),
            cache=getattr(args, "cache", False),
            webcam=getattr(args, "webcam", False),
            camera_index=getattr(args, "camera", 0),
            visualizer=getattr(args, "visualizer", "none"),
            controls=not getattr(args, "no_controls", False),
        )

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid
        """
        # Width is used as a divisor and allocation size downstream; require a
        # real integer so bad YAML/CLI input cannot produce a blank frame or a
        # ZeroDivisionError.
        if isinstance(self.width, bool) or not isinstance(self.width, int) or self.width < 1:
            raise ValueError(f"Width must be an integer >= 1, got {self.width!r}")

        # FPS is used as a divisor when exporting; NaN/inf/zero would crash or
        # generate unusable output.
        if self.fps is not None:
            if (
                isinstance(self.fps, bool)
                or not isinstance(self.fps, (int, float))
                or not math.isfinite(self.fps)
                or self.fps <= 0
            ):
                raise ValueError(
                    f"FPS must be a finite number > 0 (or None), got {self.fps!r}"
                )

        if self.preset not in ASCII_PRESETS:
            raise ValueError(f"Unknown preset: {self.preset!r}")

        if self.export is not None and self.export not in EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported export format: {self.export!r} "
                f"(expected one of: {', '.join(EXPORT_FORMATS)})"
            )

        if self.lyrics_mode not in LYRICS_MODES:
            raise ValueError(f"Invalid lyrics mode: {self.lyrics_mode!r}")

        if self.visualizer not in VISUALIZER_MODES:
            raise ValueError(f"Invalid visualizer mode: {self.visualizer!r}")

        if (
            isinstance(self.camera_index, bool)
            or not isinstance(self.camera_index, int)
            or self.camera_index < 0
        ):
            raise ValueError(
                f"Camera index must be an integer >= 0, got {self.camera_index!r}"
            )

        for name in ("audio", "color", "cache", "controls", "webcam"):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise ValueError(f"{name.capitalize()} must be a boolean, got {value!r}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Dictionary representation of config
        """
        return {
            "width": self.width,
            "color": self.color,
            "preset": self.preset,
            "audio": self.audio,
            "fps": self.fps,
            "export": self.export,
            "export_output": self.export_output,
            "lyrics_path": self.lyrics_path,
            "lyrics_mode": self.lyrics_mode,
            "cache": self.cache,
            "webcam": self.webcam,
            "camera_index": self.camera_index,
            "visualizer": self.visualizer,
            "controls": self.controls,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerConfig":
        """Create config from dictionary.

        Args:
            data: Dictionary with config values

        Returns:
            PlayerConfig instance
        """
        return cls(
            width=data.get("width", 80),
            color=data.get("color", False),
            preset=data.get("preset", "classic"),
            audio=data.get("audio", True),
            fps=data.get("fps", None),
            export=data.get("export", None),
            export_output=data.get("export_output", None),
            lyrics_path=data.get("lyrics_path", None),
            lyrics_mode=data.get("lyrics_mode", "split"),
            cache=data.get("cache", False),
            webcam=data.get("webcam", False),
            camera_index=data.get("camera_index", 0),
            visualizer=data.get("visualizer", "none"),
            controls=data.get("controls", True),
        )


# Type aliases for better readability
Frame = List[str]
RGB = Tuple[int, int, int]
Size = Tuple[int, int]
