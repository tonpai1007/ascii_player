"""Entry point for ASCII Video Player."""

import os

from . import __version__
from .cli import parse_args
from .config import PlayerConfig
from .logger import setup_logger
from .player import play_video
from .settings import load_config, merge_args_with_config
from .tui import run_tui
from .webcam import run_webcam
from .youtube import cleanup_temp_file, download_youtube_video, is_youtube_url


def _print_banner():
    """Print the application banner."""
    print(f"\033[1;35m{'=' * 40}\033[0m")
    print(f"\033[1;35m  ASCII VIDEO PLAYER v{__version__}\033[0m")
    print("\033[1;35m  Powered by OpenCV + Loguru\033[0m")
    print(f"\033[1;35m{'=' * 40}\033[0m\n")


def _validated_settings(args):
    """Merge config file + CLI values and validate before any side effects."""
    settings = merge_args_with_config(args, load_config())

    # These CLI-only values are not part of the config-file merge; include
    # them so an invalid value fails here rather than during playback/export.
    settings["export"] = getattr(args, "export", None)
    settings["lyrics_mode"] = getattr(args, "lyrics_mode", "split")
    settings["camera_index"] = getattr(args, "camera", 0)
    settings["controls"] = not getattr(args, "no_controls", False)
    settings["webcam"] = getattr(args, "webcam", False)

    try:
        PlayerConfig.from_dict(settings).validate()
    except ValueError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
    return settings


def _run_image(source, args):
    from .image_player import export_image, export_still, play_image

    if args.export in ("txt", "ans", "html", "png"):
        out = args.output or f"output.{args.export}"
        path = export_still(
            source,
            out,
            width=args.width,
            preset=args.preset or "classic",
            color=args.color,
            invert=args.invert,
            dither=args.dither,
            crop=args.crop,
            aspect=args.aspect,
        )
        print(f"Exported {path}")
        return

    if args.export in ("gif", "mp4"):
        out = args.output or f"output.{args.export}"
        path = export_image(
            source,
            out,
            width=args.width,
            preset=args.preset or "classic",
            invert=args.invert,
            dither=args.dither,
            crop=args.crop,
            aspect=args.aspect,
            export_format=args.export,
        )
        print(f"Exported {path}")
        return

    play_image(
        source,
        width=args.width,
        preset=args.preset or "classic",
        color=args.color,
        invert=args.invert,
        dither=args.dither,
        animation=args.animate,
        loop=args.loop,
        hold=args.hold,
        controls=not args.no_controls,
        cache=args.cache,
        crop=args.crop,
        aspect=args.aspect,
    )


def main():
    """Main entry point."""
    args = parse_args()
    setup_logger(console=not args.tui)
    settings = _validated_settings(args)

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
            filter=args.filter,
            camera_index=args.camera,
        )
        return

    if args.clipboard:
        from .images import clipboard_image, save_clipboard_image

        image = clipboard_image()
        if image is None:
            print("Error: no image found in the clipboard")
            raise SystemExit(1)
        path = save_clipboard_image(image)
        _run_image(path, args)
        return

    if args.prompt:
        from .images import grid_lines, save_grid
        from .prompt_gen import generate_from_prompt

        res = generate_from_prompt(
            args.prompt,
            engine=args.prompt_engine,
            width=args.width or 80,
            font=args.font,
        )
        if res.image is not None:
            _run_image(res.saved_path or res.image, args)
            return
        if res.grid is not None:
            if args.export in ("txt", "ans", "html", "png"):
                out = args.output or f"output.{args.export}"
                saved = save_grid(res.grid, out, color=args.color)
                print(f"Exported {saved}")
                return
            for line in grid_lines(res.grid, color=args.color):
                print(line)
            return

    if not args.video:
        print("Error: video argument is required (or use --tui, --webcam, --clipboard, --prompt)")
        raise SystemExit(1)

    from .images import is_image_file, is_image_url

    if is_image_file(args.video) or is_image_url(args.video):
        _run_image(args.video, args)
        return

    video_path = args.video
    if not is_youtube_url(args.video) and str(args.video).lower().startswith(
        ("http://", "https://", "www.")
    ):
        from .url_loader import resolve_url, resolved_video_source

        try:
            resolved = resolve_url(args.video)
        except Exception as exc:
            print(f"Warning: could not resolve URL: {exc}")
        else:
            if resolved.kind == "image" and (resolved.saved_path or resolved.image is not None):
                _run_image(resolved.saved_path or resolved.image, args)
                return
            downloaded = resolved_video_source(resolved)
            if downloaded:
                video_path = downloaded
            else:
                print(f"Error: URL did not resolve to a playable video or image: {args.video}")
                raise SystemExit(1)

    if args.export and args.export in ("txt", "ans", "html", "png"):
        print("Error: text/png exports are only supported for images")
        raise SystemExit(1)

    temp_file = None
    if is_youtube_url(args.video):
        temp_file = download_youtube_video(args.video)
        video_path = temp_file

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
            visualizer=settings.get("visualizer", args.visualizer),
        )
    finally:
        cleanup_temp_file(temp_file)


if __name__ == "__main__":
    main()
