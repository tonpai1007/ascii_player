"""ASCII frame conversion logic."""

import cv2
import numpy as np

from .config import ASCII_PRESETS, COLOR_RESET

_CHAR_ARRAY_CACHE = {}


def _char_array(chars):
    """Return a cached numpy array of single characters for vectorized lookup."""
    if chars not in _CHAR_ARRAY_CACHE:
        _CHAR_ARRAY_CACHE[chars] = np.array(list(chars), dtype="<U1")
    return _CHAR_ARRAY_CACHE[chars]


def row_to_ansi(chars, rgb_row=None, color=True):
    """Format a row of characters with run-length-encoded ANSI truecolor codes."""
    if not color or rgb_row is None:
        return "".join(chars)

    parts = []
    previous = None
    for char, rgb in zip(chars, rgb_row):
        cell = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if cell != previous:
            parts.append(f"\033[38;2;{cell[0]};{cell[1]};{cell[2]}m")
            previous = cell
        parts.append(char)
    if parts:
        parts.append(COLOR_RESET)
    return "".join(parts)


def frame_to_ascii(frame, width=80, color=False, preset="classic"):
    """Convert an OpenCV frame to ASCII art.

    Args:
        frame: OpenCV BGR or grayscale frame (numpy array)
        width: Output width in characters
        color: Enable ANSI truecolor output
        preset: ASCII character preset name

    Returns:
        List of strings, each representing an ASCII row
    """
    ascii_chars = ASCII_PRESETS.get(preset, ASCII_PRESETS["classic"])

    if frame is None or not hasattr(frame, "shape"):
        return []
    h, w = frame.shape[:2]
    if h <= 0 or w <= 0 or width <= 0:
        return []

    new_h = max(1, min(int((h / w) * width * 0.55), 1024))

    resized = cv2.resize(frame, (width, new_h))
    if resized.ndim == 2:
        gray = resized
        if color:
            resized = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    else:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    if color:
        return _color_ascii(resized, gray, ascii_chars)
    return _grayscale_ascii(gray, ascii_chars)


def _map_chars(gray, chars):
    """Vectorized brightness -> character mapping.

    Args:
        gray: 2D uint8 array (height, width)
        chars: ASCII preset string

    Returns:
        List[str] of joined rows
    """
    char_arr = _char_array(chars)
    n_levels = len(chars) - 1
    idx = np.minimum(gray.astype(np.uint16) * n_levels // 255, n_levels).astype(np.uint16)
    char_grid = char_arr[idx]
    return ["".join(row.tolist()) for row in char_grid]


def _grayscale_ascii(gray, chars):
    """Convert grayscale image to ASCII."""
    return _map_chars(gray, chars)


def _color_ascii(resized, gray, chars):
    """Convert color image to run-length-encoded ANSI truecolor ASCII."""
    h, w = gray.shape
    if h == 0 or w == 0:
        return []

    char_arr = _char_array(chars)
    n_levels = len(chars) - 1
    idx = np.minimum(gray.astype(np.uint16) * n_levels // 255, n_levels).astype(np.uint16)
    char_grid = char_arr[idx].tolist()
    rgb_rows = resized[..., ::-1].tolist()

    return [
        row_to_ansi(char_row, rgb_row, color=True)
        for char_row, rgb_row in zip(char_grid, rgb_rows)
    ]
