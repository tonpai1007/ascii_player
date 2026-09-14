"""ASCII frame conversion logic."""

import cv2
import numpy as np

from .config import ASCII_PRESETS

_CHAR_ARRAY_CACHE = {}


def _char_array(chars):
    """Return a cached numpy array of single characters for vectorized lookup."""
    if chars not in _CHAR_ARRAY_CACHE:
        _CHAR_ARRAY_CACHE[chars] = np.array(list(chars), dtype="<U1")
    return _CHAR_ARRAY_CACHE[chars]


def frame_to_ascii(frame, width=80, color=False, preset="classic"):
    """Convert an OpenCV frame to ASCII art.

    Args:
        frame: OpenCV BGR frame (numpy array)
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
    """Convert color image to ANSI truecolor ASCII."""
    char_arr = _char_array(chars)
    n_levels = len(chars) - 1
    idx = np.minimum(gray.astype(np.uint16) * n_levels // 255, n_levels).astype(np.uint16)
    char_grid = char_arr[idx]

    rgb = resized[..., ::-1]
    h, w = gray.shape

    rows = []
    for row_i in range(h):
        rgb_row = rgb[row_i]
        chars_row = char_grid[row_i]
        parts = []
        run_r, run_g, run_b = -1, -1, -1
        run_buf = []
        for col_i in range(w):
            r = int(rgb_row[col_i, 0])
            g = int(rgb_row[col_i, 1])
            b = int(rgb_row[col_i, 2])
            c = chars_row[col_i]
            if r == run_r and g == run_g and b == run_b:
                run_buf.append(c)
            else:
                if run_buf:
                    parts.append(
                        f"\033[38;2;{run_r};{run_g};{run_b}m{''.join(run_buf)}\033[0m"
                    )
                run_r, run_g, run_b = r, g, b
                run_buf = [c]
        if run_buf:
            parts.append(
                f"\033[38;2;{run_r};{run_g};{run_b}m{''.join(run_buf)}\033[0m"
            )
        rows.append(''.join(parts))
    return rows
