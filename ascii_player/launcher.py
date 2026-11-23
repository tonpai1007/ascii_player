"""Unified terminal launcher for ASCII Video Player."""

import os
import shlex
import subprocess
import sys
from typing import List, Optional

PYTHON = sys.executable or "python"


def _win_quote(arg) -> str:
    """Quote an argument for the Windows cmd shell.

    Always wraps in double quotes so cmd metacharacters like ``&``, ``|``,
    ``<``, ``>`` and ``^`` are treated literally instead of as operators.
    cmd expands ``%VAR%`` even inside double quotes, so a literal ``%`` is
    doubled to ``%%``.
    """
    s = str(arg)
    if "%" in s:
        s = s.replace("%", "%%")
    return f'"{s}"'


def launch_new_terminal(args: List[str]) -> bool:
    """Launch a command list in a new terminal window across platforms."""
    try:
        if sys.platform == "win32":
            quoted = " ".join(_win_quote(a) for a in args)
            subprocess.Popen(
                f'start "ASCII Player" /D {_win_quote(os.getcwd())} cmd /k {quoted}',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if sys.platform == "darwin":
            cmd_str = " ".join(shlex.quote(str(a)) for a in args)
            escaped = cmd_str.replace("\\", "\\\\").replace('"', '\\"')
            script = f'tell application "Terminal" to do script "{escaped}"'
            subprocess.Popen(["osascript", "-e", script])
            return True
        for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
            try:
                subprocess.Popen([term, "-e", *[str(a) for a in args]])
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False


def launch_in_new_terminal(
    video_path: str,
    width: int = 80,
    color: bool = False,
    preset: str = "classic",
    audio: bool = True,
    lyrics: Optional[str] = None,
) -> bool:
    """Launch the ASCII player for *video_path* in a new terminal window."""
    args: List[str] = [PYTHON, "-m", "ascii_player", video_path, "-w", str(width)]
    if preset:
        args.extend(["-p", str(preset)])
    if color:
        args.append("-c")
    if not audio:
        args.append("--no-audio")
    if lyrics:
        args.extend(["-l", lyrics])
    return launch_new_terminal(args)
