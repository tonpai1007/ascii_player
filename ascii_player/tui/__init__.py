"""Terminal User Interface package for ASCII Video Player."""

from ..images import clipboard_image, clipboard_text, save_clipboard_image
from ..launcher import _win_quote, launch_new_terminal
from .app import ASCIITuiApp, run_tui
from .helpers import (
    LYRICS_EXT,
    RECENT_LIMIT,
    RECENT_STORE,
    VIDEO_EXT,
    _auto_lyrics,
    _load_recent,
    _save_recent,
    _strip_ansi,
    build_player_args,
    format_command_preview,
    is_url,
)
from .screens import FilePickerScreen, HelpScreen
from .widgets import (
    CommandPreview,
    FileBrowser,
    InlinePreview,
    PlaylistPanel,
    RecentList,
    SettingsPanel,
    StatusBar,
)

__all__ = [
    "ASCIITuiApp",
    "CommandPreview",
    "FileBrowser",
    "FilePickerScreen",
    "HelpScreen",
    "InlinePreview",
    "LYRICS_EXT",
    "PlaylistPanel",
    "RECENT_LIMIT",
    "RECENT_STORE",
    "RecentList",
    "SettingsPanel",
    "StatusBar",
    "VIDEO_EXT",
    "_auto_lyrics",
    "_load_recent",
    "_save_recent",
    "_strip_ansi",
    "_win_quote",
    "build_player_args",
    "clipboard_image",
    "clipboard_text",
    "format_command_preview",
    "is_url",
    "launch_new_terminal",
    "run_tui",
    "save_clipboard_image",
]
