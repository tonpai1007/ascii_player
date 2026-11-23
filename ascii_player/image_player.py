"""Terminal playback for still images and animated GIFs.

Renders a single image through the same presets as video playback, optionally
revealing it with a decode/type/rain animation, and keeps it on screen until
the user quits. Animated GIFs play frame-by-frame.
"""

from __future__ import annotations

import sys
import time

from .controls import PlaybackControls
from .images import (
    ANIMATIONS,
    IMAGE_EXT,
    RainAnimator,
    decode_lines,
    grid_lines,
    image_to_grid,
    load_frames,
    save_grid,
    type_lines,
)

CURSOR_HIDE = "\x1b[?25l"
CURSOR_SHOW = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"

ANIMATION_DURATIONS = {
    "decode": 1.2,
    "type": 1.2,
    "rain": 1.6,
}


def _terminal_size():
    import shutil

    return shutil.get_terminal_size((80, 24))


def _begin():
    sys.stdout.write(CURSOR_HIDE + CLEAR)
    sys.stdout.flush()


def _end():
    sys.stdout.write(CURSOR_SHOW)
    sys.stdout.flush()


def _draw(lines):
    sys.stdout.write("\x1b[H")
    if lines:
        sys.stdout.write("\n".join(lines))
        sys.stdout.write("\n")
    sys.stdout.flush()


def _wait_for_quit(controls, hold):
    if hold and hold > 0:
        deadline = time.time() + float(hold)
        while time.time() < deadline:
            if controls is not None and controls.should_quit():
                return
            time.sleep(0.05)
        return
    if controls is not None:
        while not controls.should_quit():
            if controls.is_paused():
                time.sleep(0.05)
                continue
            time.sleep(0.05)


def _play_still(grid, animation, color, controls, duration):
    animation = animation if animation in ANIMATIONS else "none"
    if animation == "none" or duration <= 0:
        _draw(grid_lines(grid, color))
        return

    animator = RainAnimator(grid) if animation == "rain" else None
    start = time.perf_counter()
    total = float(duration)
    while True:
        if controls is not None and controls.should_quit():
            break
        if controls is not None and controls.is_paused():
            time.sleep(0.05)
            continue
        elapsed = time.perf_counter() - start
        progress = min(1.0, elapsed / total)
        if animation == "decode":
            lines = decode_lines(grid, progress, color)
        elif animation == "type":
            lines = type_lines(grid, progress, color)
        else:
            lines = animator.lines(progress, 0.04, color)
        _draw(lines)
        if progress >= 1.0:
            break
        time.sleep(0.03)
    _draw(grid_lines(grid, color))


def _play_frames(grids, controls, loop, color=False):
    # grids: list of (AsciiGrid, duration)

    index = 0
    next_time = time.perf_counter()
    while True:
        if controls is not None and controls.should_quit():
            break

        if controls is not None and controls.is_paused():
            time.sleep(0.05)
            next_time = time.perf_counter()
            continue

        if index >= len(grids):
            if loop:
                index = 0
                next_time = time.perf_counter()
                continue
            break

        grid, duration = grids[index]
        _draw(grid_lines(grid, color))
        index += 1

        wait = duration if duration > 0 else 0.1
        next_time += wait
        now = time.perf_counter()
        if next_time <= now:
            next_time = now
        sleep_for = next_time - time.perf_counter()
        if sleep_for > 0:
            remaining = sleep_for
            while remaining > 0 and not (controls and controls.should_quit()):
                step = min(0.05, remaining)
                time.sleep(step)
                remaining -= step
                if controls and controls.is_paused():
                    next_time = time.perf_counter()
                    break


def play_image(
    source,
    width: int = 80,
    preset: str = "classic",
    color: bool = False,
    invert: bool = False,
    dither: bool = False,
    crop: bool = False,
    aspect: float = 0.55,
    animation: str = "none",
    loop: bool = False,
    hold: float = 0.0,
    controls: bool = True,
    duration: float = 1.4,
    cache: bool = False,
):
    """Play a still image or animated GIF in the terminal."""
    import shutil as _shutil

    if width <= 0:
        width = min(200, _shutil.get_terminal_size((80, 24)).columns or 80)
        if width <= 0:
            width = 80

    frames = load_frames(source)

    # Build rendered grids (with optional disk cache for faster replay).
    import hashlib as _hashlib
    import os as _os
    import pickle as _pickle

    from .images import image_to_grid

    def _cache_path():
        if not cache:
            return None
        try:
            stat = _os.stat(source) if isinstance(source, str) and _os.path.isfile(source) else None
            mtime = stat.st_mtime if stat else 0
        except OSError:
            mtime = 0
        key = _hashlib.sha256()
        key.update(str(source).encode("utf-8", "replace"))
        key.update(str(mtime).encode())
        key.update(f"{width}|{preset}|{int(invert)}|{int(dither)}".encode())
        directory = _os.path.join(_os.path.expanduser("~"), ".cache", "ascii_player")
        _os.makedirs(directory, exist_ok=True)
        return _os.path.join(directory, key.hexdigest() + ".pkl")

    cache_file = _cache_path()
    grids = None
    if cache_file and _os.path.isfile(cache_file):
        try:
            with open(cache_file, "rb") as handle:
                grids = _pickle.load(handle)
        except Exception:
            grids = None

    if grids is None:
        grids = []
        for frame, duration in frames:
            grids.append((image_to_grid(frame, width, preset, invert=invert, dither=dither, crop=crop, aspect=aspect), duration))
        if cache_file:
            try:
                with open(cache_file, "wb") as handle:
                    _pickle.dump(grids, handle)
            except Exception:
                pass

    input_controls = None
    if controls:
        try:
            input_controls = PlaybackControls()
            if sys.stdin.isatty():
                input_controls.start()
            else:
                input_controls = None
        except Exception:
            input_controls = None

    _begin()
    try:
        if len(frames) == 1:
            grid = grids[0][0]
            _play_still(grid, animation, color, input_controls, duration)
            _draw(grid_lines(grid, color))
            sys.stdout.write("\n \x1b[2mQ quit\x1b[0m\n")
            sys.stdout.flush()
            _wait_for_quit(input_controls, hold)
        else:
            _play_frames(grids, input_controls, loop, color=color)
            if not loop:
                sys.stdout.write("\n \x1b[2mQ quit\x1b[0m\n")
                sys.stdout.flush()
            _wait_for_quit(input_controls, hold)
    except KeyboardInterrupt:
        pass
    finally:
        if input_controls is not None:
            input_controls.stop()
        _end()


def export_still(
    source,
    path: str,
    width: int = 80,
    preset: str = "classic",
    color: bool = False,
    invert: bool = False,
    dither: bool = False,
    crop: bool = False,
    aspect: float = 0.55,
) -> str:
    """Render the first frame of a source and write it to *path*."""
    from .images import load_image

    if width <= 0:
        import shutil as _shutil
        width = min(200, _shutil.get_terminal_size((80, 24)).columns or 80) or 80
    grid = image_to_grid(load_image(source), width, preset, invert=invert, dither=dither, crop=crop, aspect=aspect)
    return save_grid(grid, path)


def export_image(
    source,
    path: str,
    width: int = 80,
    preset: str = "classic",
    invert: bool = False,
    dither: bool = False,
    crop: bool = False,
    aspect: float = 0.55,
    export_format: str = "gif",
    fps: int = 24,
    duration: float = 2.0,
) -> str:
    from .exporter import ASCIIExporter

    if width <= 0:
        import shutil as _shutil
        width = min(200, _shutil.get_terminal_size((80, 24)).columns or 80) or 80
    frames = load_frames(source)
    exporter = ASCIIExporter(width, fps)

    if len(frames) == 1:
        grid = image_to_grid(frames[0][0], width, preset, invert=invert, dither=dither, crop=crop, aspect=aspect)
        plain = grid_lines(grid, color=True)
        total = max(1, int(fps * max(0.5, duration)))
        for index in range(total):
            exporter.add_frame(plain, index)
    else:
        for index, (frame, _duration) in enumerate(frames):
            grid = image_to_grid(frame, width, preset, invert=invert, dither=dither, crop=crop, aspect=aspect)
            exporter.add_frame(grid_lines(grid, color=True), index)

    if export_format == "mp4" or str(path).lower().endswith(".mp4"):
        exporter.export_mp4(path)
    else:
        exporter.export_gif(path)
    return path


__all__ = ["play_image", "export_still", "export_image", "ANIMATIONS", "IMAGE_EXT"]
