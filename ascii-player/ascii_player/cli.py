"""Command-line interface for ASCII Video Player."""

import argparse

from . import __version__
from .config import ASCII_PRESETS, DEFAULT_FPS, DEFAULT_WIDTH


def parse_args():
    """Parse command-line arguments.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="ascii-player",
        description="ASCII Video Player - Play videos as ASCII art in your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4                    Play local video
  %(prog)s -t                           Launch TUI interface
  %(prog)s video.mp4 -w 120             Wider output
  %(prog)s video.mp4 -c                 Color mode
  %(prog)s video.mp4 -p blocks          Use block characters
  %(prog)s video.mp4 --no-audio         Disable audio
  %(prog)s video.mp4 --no-controls      Disable keyboard controls
  %(prog)s video.mp4 --cache            Cache frames for replay
  %(prog)s video.mp4 --export gif       Export to GIF
  %(prog)s video.mp4 --export mp4       Export to MP4
  %(prog)s video.mp4 -l lyrics.lrc      Play with synced lyrics
  %(prog)s video.mp4 -l lyrics.srt --lyrics-mode fullscreen
  %(prog)s --webcam                     Live ASCII webcam
  %(prog)s https://youtube.com/watch?v=XYZ   YouTube video
  %(prog)s https://youtu.be/XYZ -c -w 100    YouTube + color

Presets: {presets}
Lyrics: LRC, SRT, ASS/SSA formats
Controls: Space=pause, Q=quit, +/-=speed, Arrows=seek
        """.format(presets=", ".join(ASCII_PRESETS.keys()))
    )

    parser.add_argument(
        "video",
        nargs="?",
        help="Path to video file or YouTube URL"
    )
    parser.add_argument(
        "-t", "--tui",
        action="store_true",
        help="Launch terminal user interface"
    )
    parser.add_argument(
        "-w", "--width",
        type=lambda x: max(1, int(x)),
        default=None,
        help=(
            f"ASCII output width in characters "
            f"(default: {DEFAULT_WIDTH}, or the value from ascii_player.yaml)"
        )
    )
    parser.add_argument(
        "-f", "--fps",
        type=lambda x: max(0.1, float(x)),
        default=DEFAULT_FPS,
        help="Playback FPS (default: auto from video)"
    )
    parser.add_argument(
        "-c", "--color",
        action="store_true",
        default=None,
        help="Enable ANSI truecolor output (overrides config)"
    )
    parser.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        help="Disable ANSI truecolor output (overrides config)"
    )
    parser.add_argument(
        "-p", "--preset",
        choices=list(ASCII_PRESETS.keys()),
        default=None,
        help="ASCII character preset (default: classic)"
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        default=False,
        help="Disable audio playback"
    )
    parser.add_argument(
        "--no-controls",
        action="store_true",
        help="Disable keyboard controls"
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Cache decoded frames for faster replay"
    )
    parser.add_argument(
        "--export",
        choices=["gif", "mp4"],
        default=None,
        help="Export ASCII video to file"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file path for export (default: output.<format>)"
    )
    parser.add_argument(
        "-l", "--lyrics",
        default=None,
        help="Path to lyrics file (.lrc, .srt, .ass)"
    )
    parser.add_argument(
        "--lyrics-mode",
        choices=["split", "fullscreen"],
        default=None,
        help="Lyrics display mode (default: split)"
    )
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Run live ASCII webcam mode"
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera device index (default: 0)"
    )
    parser.add_argument(
        "--visualizer",
        choices=["none", "bars", "wave"],
        default=None,
        help="Audio visualizer mode (default: none)"
    )
    parser.add_argument(
        "--filter",
        choices=["none", "edge", "invert", "colorcycle", "mirror"],
        default="none",
        help="Webcam filter mode (default: none)"
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args()
