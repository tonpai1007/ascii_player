"""Entry point for ASCII Video Player."""

import os

from . import __version__
from .cli import parse_args
from .logger import setup_logger
from .player import play_video
from .settings import load_config, merge_args_with_config
from .tui import run_tui
from .webcam import run_webcam
from .youtube import cleanup_temp_file, download_youtube_video, is_youtube_url


def main():
    """Main entry point."""
    args = parse_args()
    setup_logger(console=not args.tui)

    if args.tui:
        run_tui()
        return

    _print_banner()

    if args.webcam:
        run_webcam(
            width=args.width,
            color=args.color,
            preset=args.preset or "classic",
            target_fps=int(args.fps) if args.fps else 30,
            filter=args.filter
        )
        return

    if not args.video:
        print("Error: video argument is required (or use --tui, --webcam)")
        raise SystemExit(1)

    config = load_config()
    settings = merge_args_with_config(args, config)

    temp_file = None
    if is_youtube_url(args.video):
        temp_file = download_youtube_video(args.video)
        video_path = temp_file
    else:
        video_path = args.video

    lyrics_path = args.lyrics
    if lyrics_path and not os.path.exists(lyrics_path):
        print(f"Warning: Lyrics file not found: {lyrics_path}")
        lyrics_path = None

    try:
        play_video(
            video_path,
            width=settings["width"],
            fps=settings.get("fps"),
            color=settings["color"],
            preset=settings["preset"],
            audio=settings["audio"],
            cache=args.cache,
            export=args.export,
            export_output=args.output,
            lyrics_path=lyrics_path,
            lyrics_mode=args.lyrics_mode,
            controls=not args.no_controls,
            visualizer=args.visualizer
        )
    finally:
        cleanup_temp_file(temp_file)


def _print_banner():
    """Print the application banner."""
    print(f"\033[1;35m{'=' * 40}\033[0m")
    print(f"\033[1;35m  ASCII VIDEO PLAYER v{__version__}\033[0m")
    print("\033[1;35m  Powered by OpenCV + Loguru\033[0m")
    print(f"\033[1;35m{'=' * 40}\033[0m\n")


if __name__ == "__main__":
    main()
