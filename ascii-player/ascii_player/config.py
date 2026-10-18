"""Configuration and constants for ASCII Video Player."""

from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any

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
}

DEFAULT_PRESET = "classic"
DEFAULT_WIDTH = 80
DEFAULT_FPS = None
DEFAULT_COLOR = False
DEFAULT_AUDIO = True

LOG_FORMAT = "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}"
LOG_ROTATION = "5 MB"
LOG_RETENTION = "7 days"

YOUTUBE_REGEX = (
    r"^(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)(?:/|$)"
)
YOUTUBE_MAX_HEIGHT = 720
YOUTUBE_TIMEOUT = 300

CONFIG_FILE = "ascii_player.yaml"
DEFAULT_CONFIG: Dict[str, Any] = {
    "width": DEFAULT_WIDTH,
    "fps": DEFAULT_FPS,
    "color": DEFAULT_COLOR,
    "audio": DEFAULT_AUDIO,
    "preset": DEFAULT_PRESET,
    "lyrics_mode": "split",
    "visualizer": "none",
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
        export: Export format (None, "gif", "mp4")
        export_output: Output file path for export
        lyrics_path: Path to lyrics file
        lyrics_mode: Lyrics display mode ("split", "fullscreen", "none")
        cache: Enable frame caching
        webcam: Enable webcam mode
        camera_index: Camera device index
        visualizer: Audio visualizer mode ("none", "bars", "wave")
        controls: Enable keyboard controls
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
    def from_args(cls, args: Any) -> 'PlayerConfig':
        """Create config from parsed command line arguments.
        
        Args:
            args: Parsed argparse namespace
            
        Returns:
            PlayerConfig instance
        """
        return cls(
            width=getattr(args, 'width', 80),
            color=getattr(args, 'color', False),
            preset=getattr(args, 'preset', 'classic'),
            audio=getattr(args, 'audio', True),
            fps=getattr(args, 'fps', None),
            export=getattr(args, 'export', None),
            export_output=getattr(args, 'output', None),
            lyrics_path=getattr(args, 'lyrics', None),
            lyrics_mode=getattr(args, 'lyrics_mode', 'split'),
            cache=getattr(args, 'cache', False),
            webcam=getattr(args, 'webcam', False),
            camera_index=getattr(args, 'camera', 0),
            visualizer=getattr(args, 'visualizer', 'none'),
            controls=not getattr(args, 'no_controls', False),
        )

    def validate(self) -> None:
        """Validate configuration values.
        
        Raises:
            ValueError: If any configuration value is invalid
        """
        if self.width <= 0:
            raise ValueError("Width must be positive")
        if self.preset not in ASCII_PRESETS:
            raise ValueError(f"Unknown preset: {self.preset}")
        if self.export and self.export not in ('gif', 'mp4'):
            raise ValueError(f"Unsupported export format: {self.export}")
        if self.lyrics_mode not in ('split', 'fullscreen', 'none'):
            raise ValueError(f"Invalid lyrics mode: {self.lyrics_mode}")
        if self.fps is not None and self.fps <= 0:
            raise ValueError("FPS must be positive")
        if self.visualizer not in ('none', 'bars', 'wave'):
            raise ValueError(f"Invalid visualizer mode: {self.visualizer}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary.
        
        Returns:
            Dictionary representation of config
        """
        return {
            'width': self.width,
            'color': self.color,
            'preset': self.preset,
            'audio': self.audio,
            'fps': self.fps,
            'export': self.export,
            'export_output': self.export_output,
            'lyrics_path': self.lyrics_path,
            'lyrics_mode': self.lyrics_mode,
            'cache': self.cache,
            'webcam': self.webcam,
            'camera_index': self.camera_index,
            'visualizer': self.visualizer,
            'controls': self.controls,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlayerConfig':
        """Create config from dictionary.
        
        Args:
            data: Dictionary with config values
            
        Returns:
            PlayerConfig instance
        """
        return cls(
            width=data.get('width', 80),
            color=data.get('color', False),
            preset=data.get('preset', 'classic'),
            audio=data.get('audio', True),
            fps=data.get('fps', None),
            export=data.get('export', None),
            export_output=data.get('export_output', None),
            lyrics_path=data.get('lyrics_path', None),
            lyrics_mode=data.get('lyrics_mode', 'split'),
            cache=data.get('cache', False),
            webcam=data.get('webcam', False),
            camera_index=data.get('camera_index', 0),
            visualizer=data.get('visualizer', 'none'),
            controls=data.get('controls', True),
        )


# Type aliases for better readability
Frame = List[str]
RGB = Tuple[int, int, int]
Size = Tuple[int, int]