"""Shared helpers and unified CLI argument construction for the TUI."""

import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from ..images import is_image_file, is_image_url
from ..launcher import PYTHON

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

VIDEO_EXT = (
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv",
    ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp",
)
LYRICS_EXT = (".lrc", ".srt", ".ass", ".ssa")

RECENT_STORE = "ascii_player_recent.txt"
RECENT_LIMIT = 10


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def is_url(text: str) -> bool:
    return bool(re.match(r"https?://|www\.", text))


def _load_recent() -> List[str]:
    if not os.path.exists(RECENT_STORE):
        return []
    try:
        with open(RECENT_STORE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []


def _save_recent(recent: List[str], max_items: int = RECENT_LIMIT) -> None:
    deduped = list(OrderedDict.fromkeys(recent))[:max_items]
    try:
        with open(RECENT_STORE, "w", encoding="utf-8") as f:
            f.write("\n".join(deduped))
    except Exception:
        pass


def _auto_lyrics(video_path: str) -> Optional[str]:
    """Look for a same-name sibling lyrics file next to the video."""
    base, _ = os.path.splitext(video_path)
    for ext in LYRICS_EXT:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def build_player_args(
    source: str,
    settings: Dict[str, Any],
    selected_kind: Optional[str] = None,
    lyrics_auto: Optional[str] = None,
    export_output: Optional[str] = None,
) -> List[str]:
    """Build the CLI argument vector for launching a video or image."""
    s = settings
    is_img = (
        selected_kind == "image"
        or is_image_file(source)
        or is_image_url(str(source))
    )

    args: List[str] = [PYTHON, "-m", "ascii_player", source, "-w", str(s["width"])]
    if s.get("preset"):
        args.extend(["-p", str(s["preset"])])
    if s.get("color"):
        args.append("-c")

    if is_img:
        args.extend(["--animate", str(s.get("animate", "decode"))])
        if s.get("dither"):
            args.append("--dither")
        if s.get("invert"):
            args.append("--invert")
        if s.get("crop"):
            args.append("--crop")
            args.extend(["--aspect", str(s.get("aspect", 0.55))])
        if s.get("loop"):
            args.append("--loop")
    else:
        if not s.get("audio", True):
            args.append("--no-audio")
        if s.get("fps"):
            args.extend(["-f", str(s["fps"])])
        if lyrics_auto:
            args.extend(["-l", lyrics_auto])
            if s.get("lyrics") == "fullscreen":
                args.extend(["--lyrics-mode", "fullscreen"])

    export_fmt = s.get("export", "none")
    if export_fmt and export_fmt != "none":
        args.extend(["--export", str(export_fmt)])
        out = export_output or (s.get("output") or "").strip()
        if out:
            args.extend(["-o", out])

    if s.get("cache"):
        args.append("--cache")

    return args


def format_command_preview(args: List[str]) -> str:
    """Format a launch argument vector as a concise display string."""
    if len(args) < 4:
        return "(nothing ready to play)"
    # args[:3] is [PYTHON, "-m", "ascii_player"], args[3] is source
    source = args[3]
    display_source = source if is_url(source) else (os.path.basename(source) or source)
    tail: List[str] = []
    i = 4
    while i < len(args):
        token = args[i]
        if token == "-l" and i + 1 < len(args):
            tail.extend(["-l", os.path.basename(args[i + 1]) or args[i + 1]])
            i += 2
            continue
        tail.append(token)
        i += 1
    return "ascii-player " + " ".join([display_source, *tail])
