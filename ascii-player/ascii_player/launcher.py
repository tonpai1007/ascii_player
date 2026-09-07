"""Standalone player script for launching in new terminal."""

import base64
import json
import os
import subprocess
import sys
import tempfile


def launch_in_new_terminal(video_path, width=80, color=False, preset="classic", audio=True, lyrics=None):
    """Launch player in a new terminal window.

    Args:
        video_path: Path to video file
        width: ASCII width
        color: Enable color
        preset: ASCII preset
        audio: Enable audio
        lyrics: Path to lyrics file
    """
    params = {
        "video": video_path,
        "width": width,
        "color": color,
        "preset": preset,
        "audio": audio,
        "lyrics": lyrics
    }
    params_b64 = base64.b64encode(json.dumps(params).encode()).decode()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    player_script = f'''import sys
sys.path.insert(0, r"{base_dir}")
from ascii_player.player import play_video
import json, base64

params = json.loads(base64.b64decode("{params_b64}").decode())

play_video(
    params["video"],
    width=params["width"],
    color=params["color"],
    preset=params["preset"],
    audio=params["audio"],
    lyrics_path=params.get("lyrics")
)

input("\\nPress Enter to close...")
'''

    temp_script = None
    try:
        fd, temp_script = tempfile.mkstemp(suffix=".py", prefix="ascii_player_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(player_script)

        platform = sys.platform

        if platform == "win32":
            cmd = [
                "cmd", "/c", "start", "cmd", "/k",
                sys.executable, temp_script
            ]
        elif platform == "darwin":
            cmd = [
                "osascript", "-e",
                f'tell application "Terminal" to do script "{sys.executable} {temp_script}"'
            ]
        else:
            cmd = [
                "x-terminal-emulator", "-e",
                sys.executable, temp_script
            ]

        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE if platform == "win32" else 0)
        return True
    except Exception as e:
        print(f"Failed to open new terminal: {e}")
        return False
