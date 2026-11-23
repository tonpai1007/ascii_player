"""Modal screens for the ASCII Video Player TUI."""

from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DirectoryTree, Static

from ..images import is_image_file, is_image_url
from .helpers import LYRICS_EXT


class FilePickerScreen(Screen):
    """Modal file picker built on DirectoryTree."""

    def __init__(self, start_dir=".", **kwargs):
        super().__init__(**kwargs)
        self.start_dir = start_dir

    def compose(self):
        with Vertical(id="picker-container"):
            yield Static("Pick a file (Enter), Esc to cancel", id="picker-title")
            yield DirectoryTree(self.start_dir, id="picker-tree")

    def on_directory_tree_file_selected(self, event):
        path = str(event.path)
        if is_image_file(path) or is_image_url(path):
            kind = "image"
        elif path.lower().endswith(tuple(LYRICS_EXT)):
            kind = "lyrics"
        else:
            kind = "video"
        self.app.select_file(path, kind)
        self.app.pop_screen()

    def on_key(self, event):
        if event.key == "escape":
            self.app.pop_screen()
            event.stop()


class HelpScreen(ModalScreen):
    """Help overlay with keybindings."""

    def compose(self):
        with Vertical(id="help-dialog"):
            yield Static("KEYBINDINGS", id="help-title")
            yield Static(
                "Up/Down          Navigate file list\n"
                "Enter            Open directory / select file\n"
                "Space            Add/remove from playlist\n"
                "P                Play selected file\n"
                "W                Start webcam\n"
                "G                Go to path\n"
                "R                Refresh file list\n"
                "T                Cycle theme\n"
                "V                Toggle audio visualizer\n"
                "Ctrl+V           Paste from clipboard\n"
                "F                Toggle fullscreen (hide sidebar)\n"
                "Ctrl+Left/Right  Playlist prev/next\n"
                "Ctrl+P           Show this help\n"
                "Esc              Close dialog / cancel\n"
                "Q                Quit",
                id="help-body",
            )

    def on_key(self, event):
        if event.key in ("escape", "ctrl+p"):
            self.app.pop_screen()
            event.stop()
