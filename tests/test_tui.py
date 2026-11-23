"""Tests for ascii_player.tui - the Textual TUI."""

import asyncio
import os

import pytest
from textual.containers import Container
from textual.widgets import Input, ListView, Static

from ascii_player.settings import load_config
from ascii_player.tui import ASCIITuiApp, _strip_ansi, _win_quote, is_url


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Isolate CWD-relative artifacts (ascii_player.yaml, recent store).
    monkeypatch.chdir(tmp_path)
    return ASCIITuiApp()


def _scenario(app, check):
    async def scenario():
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            await check(app, pilot)
    asyncio.run(scenario())


class TestCompose:
    def test_widgets_exist(self, app):
        async def check(app, pilot):
            assert app.query_one("#sidebar", Container) is not None
            assert app.query_one("#main", Container) is not None
            assert app.query_one("#file-list", ListView) is not None
            assert app.query_one("#recent-list", ListView) is not None
            assert app.query_one("#dir-input", Input) is not None
            assert app.query_one("#url-input", Input) is not None
            assert app.query_one("#cmd-preview", Static) is not None
            assert app.query_one("#preview-body", Static) is not None
            assert app.query_one("#status-text", Static) is not None
            assert app.query_one("Footer") is not None

        _scenario(app, check)

    def test_default_settings_loaded(self, app):
        async def check(app, pilot):
            panel = app.query_one("SettingsPanel")
            settings = panel.collect()
            assert settings["width"] == "80"
            assert settings["preset"] == "classic"
            assert settings["color"] is False
            assert settings["audio"] is True
            assert settings["export"] == "none"
            assert settings["lyrics"] == "auto"

        _scenario(app, check)


class TestCommandBuilding:
    def test_build_player_args(self, app):
        async def check(app, pilot):
            video = os.path.join(app.query_one("FileBrowser").current_dir, "movie.mp4")
            app.select_file(video, "video")
            args = app._build_player_args(video)
            assert "-m" in args and "ascii_player" in args
            assert video in args
            assert "-w" in args and args[args.index("-w") + 1] == "80"

        _scenario(app, check)

    def test_build_player_args_export_output(self, app):
        async def check(app, pilot):
            video = os.path.join(app.query_one("FileBrowser").current_dir, "movie.mp4")
            app.select_file(video, "video")
            app.query_one("#input-width", Input).value = "100"
            app.query_one("#select-export").value = "mp4"
            app.query_one("#input-output", Input).value = "render.mp4"
            args = app._build_player_args(video)
            joined = " ".join(args)
            assert "-w 100" in joined
            assert "--export mp4" in joined
            assert "-o render.mp4" in joined

        _scenario(app, check)

    def test_command_preview_updates(self, app):
        async def check(app, pilot):
            app.select_file("C:\\videos\\song.mp4", "video")
            preview = app.query_one("#cmd-preview", Static)
            app._update_preview()
            assert "ascii-player " in str(preview.content)
            app.query_one("#input-width", Input).value = "120"
            app._update_preview()
            assert "-w 120" in str(preview.content)

        _scenario(app, check)

    def test_lyrics_mode_does_not_pass_mode_as_file_path(self, app):
        async def check(app, pilot):
            video = os.path.join(app.query_one("FileBrowser").current_dir, "movie.mp4")
            app.select_file(video, "video")
            app.query_one("#select-lyrics").value = "fullscreen"
            args = app._build_player_args(video)
            assert "-l" not in args

        _scenario(app, check)


class TestSettingsPersistence:
    def test_persist_roundtrip(self, app):
        async def check(app, pilot):
            panel = app.query_one("SettingsPanel")
            panel.load_from_config({
                "width": 100,
                "preset": "blocks",
                "color": True,
                "audio": False,
                "fps": 30,
                "export": "mp4",
                "output": "out.mp4",
                "lyrics": "split",
                "cache": True,
            })
            app._persist_settings()
            assert os.path.exists("ascii_player.yaml")
            loaded = load_config()
            assert loaded["width"] == 100
            assert loaded["preset"] == "blocks"
            assert loaded["color"] is True
            assert loaded["audio"] is False
            assert loaded["fps"] == 30.0
            assert loaded["export"] == "mp4"
            assert loaded["output"] == "out.mp4"
            assert loaded["lyrics"] == "split"
            assert loaded["cache"] is True

        _scenario(app, check)


class TestRecentFiles:
    def test_record_recent(self, app):
        async def check(app, pilot):
            app._record_recent("C:\\videos\\movie.mp4")
            assert os.path.exists("ascii_player_recent.txt")
            recent = [line.strip() for line in open("ascii_player_recent.txt", encoding="utf-8")]
            assert "C:\\videos\\movie.mp4" in recent

        _scenario(app, check)


class TestHelpers:
    def test_is_url(self):
        assert is_url("https://youtube.com/watch?v=x")
        assert is_url("http://example.com")
        assert is_url("www.youtube.com")
        assert not is_url("local/file.mp4")
        assert not is_url("")

    def test_win_quote(self):
        # Always double-quoted so cmd metacharacters cannot split the argument.
        assert _win_quote("plain") == '"plain"'
        assert _win_quote("has space") == '"has space"'
        assert _win_quote("a&b") == '"a&b"'
        assert _win_quote("a|b") == '"a|b"'
        assert _win_quote("a^b") == '"a^b"'
        assert _win_quote("a<b>c") == '"a<b>c"'
        assert _win_quote(80) == '"80"'

    def test_win_quote_escapes_percent(self):
        # cmd expands %VAR% even inside quotes, so % must be doubled.
        assert _win_quote("C:\\my%music%\\song.mp4") == '"C:\\my%%music%%\\song.mp4"'

    def test_strip_ansi(self):
        assert _strip_ansi("\x1b[1;32mgreen\x1b[0m") == "green"
        assert _strip_ansi("plain") == "plain"


class TestImageSelection:
    def test_select_image_sets_kind(self, app):
        async def check(app, pilot):
            path = "C:\\images\\shot.png"
            app.select_file(path, "image")
            assert app.selected_file == path
            assert app.selected_kind == "image"
            assert app._lyrics_auto is None
        _scenario(app, check)

    def test_build_player_args_image(self, app):
        async def check(app, pilot):
            image = os.path.join(app.query_one("FileBrowser").current_dir, "pic.png")
            app.select_file(image, "image")
            app.query_one("#select-animate").value = "rain"
            app.query_one("#select-dither").value = True
            app.query_one("#select-invert").value = True
            app.query_one("#select-loop").value = True
            args = app._build_player_args(image)
            joined = " ".join(args)
            assert image in args
            assert "--animate rain" in joined
            assert "--dither" in joined
            assert "--invert" in joined
            assert "--loop" in joined
            assert "--no-audio" not in joined
        _scenario(app, check)

    def test_command_preview_image(self, app):
        async def check(app, pilot):
            app.select_file("C:\\images\\shot.png", "image")
            app._update_preview()
            preview = app.query_one("#cmd-preview", Static)
            text = str(preview.content)
            assert "ascii-player " in text
            assert "--animate" in text
        _scenario(app, check)


class TestClipboard:
    def test_paste_clipboard_image(self, app, monkeypatch, tmp_path):
        from PIL import Image

        import ascii_player.tui as tui_mod

        img_path = tmp_path / "cb.png"
        Image.new("RGB", (4, 4), (1, 2, 3)).save(img_path)

        monkeypatch.setattr(tui_mod, "clipboard_image", lambda: Image.open(img_path).convert("RGB"))
        monkeypatch.setattr(tui_mod, "save_clipboard_image", lambda image, directory=None: str(img_path))
        async def check(app, pilot):
            app.paste_clipboard()
            await pilot.pause()
            assert app.selected_kind == "image"
            assert app.selected_file == str(img_path)
        _scenario(app, check)

    def test_paste_clipboard_text(self, app, monkeypatch):
        import ascii_player.tui as tui_mod
        monkeypatch.setattr(tui_mod, "clipboard_image", lambda: None)
        monkeypatch.setattr(tui_mod, "clipboard_text", lambda: "https://example.com/x.png")
        async def check(app, pilot):
            app.paste_clipboard()
            await pilot.pause()
            assert app.query_one("#url-input").value == "https://example.com/x.png"
        _scenario(app, check)
