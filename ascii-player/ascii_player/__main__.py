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

    config = load_config()
    settings = merge_args_with_config(args, config)

    if args.webcam:
        run_webcam(
            width=settings["width"],
            color=settings["color"],
            preset=settings["preset"] or "classic",
            target_fps=int(settings.get("fps") or 30),
            filter=args.filter,
            camera_index=args.camera,
        )
        return

    if not args.video:
        print("Error: video argument is required (or use --tui, --webcam)")
        raise SystemExit(1)

    temp_file = None
    if is_youtube_url(args.video):
        temp_file = download_youtube_video(args.video)
        video_path = temp_file
    else:
        video_path = args.video

    lyrics_path = _resolve_lyrics(args, settings, video_path)
    export_format, export_output = _resolve_export(args, settings)

    try:
        play_video(
            video_path,
            width=settings["width"],
            fps=settings.get("fps"),
            color=settings["color"],
            preset=settings["preset"],
            audio=settings["audio"],
            cache=args.cache or bool(settings.get("cache")),
            export=export_format,
            export_output=export_output,
            lyrics_path=lyrics_path,
            lyrics_mode=settings.get("lyrics_mode") or "split",
            controls=not args.no_controls,
            visualizer=settings.get("visualizer") or "none",
        )
    finally:
        cleanup_temp_file(temp_file)


def _resolve_export(args, settings):
    """Resolve export format/output from CLI args, falling back to config."""
    export_format = args.export or settings.get("export")
    if export_format in (None, "", "none"):
        return None, None

    export_output = args.output or settings.get("output") or None
    return export_format, export_output


def _resolve_lyrics(args, settings, video_path):
    """Resolve the lyrics file from CLI args, config, or auto-detection."""
    if args.lyrics:
        if not os.path.exists(args.lyrics):
            print(f"Warning: Lyrics file not found: {args.lyrics}")
            return None
        return args.lyrics

    configured = settings.get("lyrics_path")
    if configured:
        if os.path.exists(configured):
            return configured
        print(f"Warning: Lyrics file not found: {configured}")

    if settings.get("lyrics", "auto") == "auto":
        from .lyrics import find_lyrics_file

        return find_lyrics_file(video_path)

    return None


def _print_banner():
    """Print the application banner."""
    print(f"\033[1;35m{'=' * 40}\033[0m")
    print(f"\033[1;35m  ASCII VIDEO PLAYER v{__version__}\033[0m")
    print("\033[1;35m  Powered by OpenCV + Loguru\033[0m")
    print(f"\033[1;35m{'=' * 40}\033[0m\n")


if __name__ == "__main__":
    main()
