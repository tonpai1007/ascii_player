"""Unified terminal launcher for ASCII Video Player."""

import os
import shlex
import subprocess
import sys
import tempfile
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
            cwd = os.getcwd()
            # cmd /c and /k strip the outer quotes from their command tail, so
            # joining individually quoted arguments corrupts the command (and
            # '=' in a URL is a cmd delimiter). A batch file gives cmd a single
            # parsing layer with the quotes exactly as written.
            fd, batch = tempfile.mkstemp(prefix="ascii_player_", suffix=".cmd")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("@echo off\r\n")
                f.write(f"cd /d {_win_quote(cwd)}\r\n")
                f.write(" ".join(_win_quote(a) for a in args) + "\r\n")
                # (goto) ends the batch without cmd trying to read another line
                # after the file is deleted. /k keeps the console open instead
                # of a pause, so the batch is safe to run non-interactively.
                f.write("echo.\r\n(goto) 2>nul & del \"%~f0\" >nul 2>&1\r\n")
            subprocess.Popen(
                [os.environ.get("COMSPEC", "cmd.exe"), "/k", batch],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=cwd,
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
