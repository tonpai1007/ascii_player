"""Tests for ascii_player.tui - the Textual TUI."""

import asyncio
import os
import time

import numpy as np
import pytest
from PIL import Image
from textual.containers import Container, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    ListView,
    OptionList,
    Select,
    Static,
    TabbedContent,
)

from ascii_player.settings import load_config
from ascii_player.tui import (
    ASCIITuiApp,
    CommandPaletteScreen,
    DrawCanvas,
    DrawWorkspace,
    OmniboxBar,
    StudioTopBar,
    WelcomeHero,
    _strip_ansi,
    _win_quote,
    is_url,
)
from ascii_player.tui.screens import ExportScreen, HelpScreen
from ascii_player.url_loader import ResolvedURL


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

        monkeypatch.setattr(
            tui_mod, "clipboard_image", lambda: Image.open(img_path).convert("RGB")
        )
        monkeypatch.setattr(
            tui_mod, "save_clipboard_image", lambda image, directory=None: str(img_path)
        )

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
            # Studio paste targets the omnibox only; the URL field is left alone.
            assert app.query_one("#omnibox", Input).value == "https://example.com/x.png"
            assert app.query_one("#url-input", Input).value == ""
        _scenario(app, check)


class TestStudioLayoutAndDynamicSources:
    def test_opencode_clean_default_layout_120x36(self, app):
        async def check(app, pilot):
            topbar = app.query_one(StudioTopBar)
            hero = app.query_one("#welcome-hero", WelcomeHero)
            canvas = app.query_one("InlinePreview")
            omnibox_bar = app.query_one(OmniboxBar)
            omnibox = app.query_one("#omnibox", Input)
            sidebar = app.query_one("#sidebar", Container)
            inspector = app.query_one("#inspector", VerticalScroll)
            main = app.query_one("#main", Container)
            log_drawer = app.query_one("#log-drawer", Container)
            tabs = app.query_one("#source-tabs", TabbedContent)

            assert topbar.region.height == 1
            assert tabs is not None
            assert omnibox_bar.region.height >= 4
            assert app.focused is omnibox
            assert not sidebar.has_class("open")
            assert not inspector.has_class("open")
            assert main.region.width >= 116
            assert not hero.has_class("hidden")
            assert canvas.has_class("hidden")
            assert log_drawer.has_class("visible") is False

            # Toggle drawers open and dismiss with Escape
            app.action_toggle_sidebar()
            app.action_toggle_inspector()
            await pilot.pause()
            assert sidebar.has_class("open")
            assert inspector.has_class("open")
            app.action_dismiss_overlay()
            await pilot.pause()
            assert not sidebar.has_class("open")
            assert not inspector.has_class("open")
            assert app.focused is omnibox

        async def scenario():
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())

    def test_omnibox_prompt_slash_commands_and_history(self, app, tmp_path):
        async def check(app, pilot):
            app.query_one("#select-animate").value = "none"
            app.submit_omnibox("/engine procedural")
            app.submit_omnibox("mount fuji at sunset")
            await pilot.pause(0.25)

            hero = app.query_one("#welcome-hero", WelcomeHero)
            canvas = app.query_one("InlinePreview")
            assert hero.has_class("hidden")
            assert not canvas.has_class("hidden")
            assert canvas.region.width >= 100
            assert app._canvas_source_tag == "PROMPT"
            assert app._canvas_last_grid is not None
            body = str(app.query_one("#preview-body", Static).content)
            assert len(body.strip()) > 0

            # Slash commands mutate style dynamically
            app.submit_omnibox("/preset blocks")
            app.submit_omnibox("/color on")
            app.submit_omnibox("/width 90")
            app.submit_omnibox("/filter edge")
            app.submit_omnibox("/theme claude")
            await pilot.pause(0.1)
            settings = app.query_one("SettingsPanel").collect()
            assert settings["preset"] == "blocks"
            assert settings["color"] is True
            assert settings["width"] == "90"
            assert settings["auto_fit"] is False
            assert settings["filter"] == "edge"
            assert app._current_theme == "claude"

            # Second artwork + history prev/next
            app.submit_omnibox("/banner STUDIO")
            await pilot.pause(0.2)
            assert app._canvas_direct_grid is not None
            assert len(app._art_history) >= 2
            app.submit_omnibox("/prev")
            await pilot.pause(0.1)
            assert "mount fuji" in app._canvas_label
            app.submit_omnibox("/next")
            await pilot.pause(0.1)
            assert "STUDIO" in app._canvas_label

            # Export and clear back to welcome hero
            out_png = tmp_path / "omni.png"
            app.submit_omnibox(f"/export {out_png}")
            await pilot.pause(0.1)
            assert out_png.is_file()

            app.submit_omnibox("/clear")
            await pilot.pause()
            assert not hero.has_class("hidden")
            assert canvas.has_class("hidden")

        _scenario(app, check)

    def test_omnibox_autocomplete_and_command_palette(self, app):
        async def check(app, pilot):
            omnibox = app.query_one("#omnibox", Input)
            popup = app.query_one("#autocomplete-popup", OptionList)
            omnibox.value = "/pr"
            await pilot.pause(0.1)
            assert popup.has_class("visible")
            assert popup.option_count >= 2
            omnibox.value = ""
            await pilot.pause(0.1)
            assert not popup.has_class("visible")

            app.action_open_palette()
            await pilot.pause()
            assert isinstance(app.screen, CommandPaletteScreen)
            search = app.screen.query_one("#palette-search", Input)
            search.value = "Preset: braille"
            await pilot.pause()
            app.screen._run_index(0)
            await pilot.pause()
            assert app.query_one("#select-preset").value == "braille"

        _scenario(app, check)

    def test_prompt_generation_procedural_and_banner(self, app):
        async def check(app, pilot):
            app.query_one("#select-animate").value = "none"
            app.generate_prompt_art(prompt="mount fuji at sunset", engine="procedural")
            await pilot.pause(0.25)
            assert app._canvas_source_tag == "PROMPT"
            assert app._canvas_last_grid is not None
            assert app._canvas_last_grid.width >= 12
            body = str(app.query_one("#preview-body", Static).content)
            assert len(body.strip()) > 0

            app.query_one("#select-color", Checkbox).value = True
            app.query_one("#select-invert", Checkbox).value = True
            await pilot.pause(0.1)
            assert "RGB" in str(app.query_one("#canvas-meta", Static).content)

            app.generate_prompt_art(prompt="STUDIO", engine="banner")
            await pilot.pause(0.25)
            assert app._canvas_direct_grid is not None
            assert app._canvas_last_grid.height >= 2

        _scenario(app, check)

    def test_url_loader_populates_canvas(self, app, monkeypatch, tmp_path):
        img = Image.new("RGB", (32, 24), (40, 180, 220))
        saved = tmp_path / "resolved.png"
        img.save(saved)
        resolved = ResolvedURL(
            url="https://example.com/art",
            kind="image",
            title="Remote Art",
            image=img,
            saved_path=str(saved),
        )
        monkeypatch.setattr("ascii_player.tui.app.resolve_url", lambda url: resolved)

        async def check(app, pilot):
            app.query_one("#select-animate").value = "none"
            app.load_url_source("https://example.com/art")
            await pilot.pause(0.25)
            assert app._canvas_source_tag == "URL"
            assert app._canvas_last_grid is not None
            assert app.selected_file == str(saved)

        _scenario(app, check)

    def test_webcam_tick_and_freeze_snapshot(self, app, monkeypatch):
        class FakeCap:
            def isOpened(self):
                return True

            def read(self):
                return True, np.full((32, 48, 3), 180, dtype=np.uint8)

            def release(self):
                pass

        async def check(app, pilot):
            app._webcam_preview = FakeCap()
            app._tick_webcam_preview()
            await pilot.pause()
            assert app._last_cam_image is not None
            assert app._canvas_last_grid is not None
            app._freeze_webcam_snapshot()
            await pilot.pause()
            assert app._canvas_source_tag == "SNAP"
            assert app._canvas_image is not None
            assert app.selected_file and os.path.isfile(app.selected_file)

        _scenario(app, check)

    def test_copy_and_export_current_canvas(self, app, monkeypatch, tmp_path):
        copied = []
        monkeypatch.setattr(
            "ascii_player.tui.app.copy_text_to_clipboard",
            lambda text: copied.append(text) or True,
        )

        async def check(app, pilot):
            app.action_copy_ascii()
            await pilot.pause()
            assert copied and len(copied[0].strip()) > 0

            out_png = tmp_path / "shot.png"
            out_txt = tmp_path / "shot.txt"
            app.export_current_canvas(str(out_png), "png")
            app.export_current_canvas(str(out_txt), "txt")
            assert out_png.is_file()
            assert out_txt.is_file()

        _scenario(app, check)

    def test_zoom_fullscreen_and_inspector_toggles(self, app):
        async def check(app, pilot):
            app.action_zoom_in()
            await pilot.pause()
            assert app.query_one("#check-autofit", Checkbox).value is False
            w_after_in = int(app.query_one("#input-width", Input).value)
            app.action_zoom_out()
            await pilot.pause()
            w_after_out = int(app.query_one("#input-width", Input).value)
            assert w_after_out < w_after_in

            inspector = app.query_one("#inspector", VerticalScroll)
            sidebar = app.query_one("#sidebar", Container)
            assert not inspector.has_class("open")
            app.action_toggle_inspector()
            await pilot.pause()
            assert inspector.has_class("open")
            app.action_toggle_fullscreen()
            await pilot.pause()
            assert not sidebar.has_class("open")
            assert not inspector.has_class("open")

        _scenario(app, check)

    def test_draw_tab_painting_studio_roundtrip_and_centered_hero(self, app, tmp_path):
        from textual.css.query import NoMatches

        async def check(app, pilot):
            # Verify WelcomeHero is centered and Footer is hidden
            hero_logo = app.query_one("#welcome-logo", Static)
            footer = app.query_one("Footer")
            assert str(footer.styles.display) == "none"
            assert hero_logo.region.x >= 10

            # Switch to pure-typing terminal tab via slash command
            app.submit_omnibox("/draw")
            await pilot.pause()
            dw = app.query_one("#draw-workspace", DrawWorkspace)
            canvas = app.query_one("#draw-canvas", DrawCanvas)
            assert not dw.has_class("hidden")
            assert app._active_mode == "draw"
            assert app.focused is canvas

            # Verify old paint buttons are gone
            removed_paint_ids = (
                "#dt-brush",
                "#dt-line",
                "#dt-box",
                "#dt-ellipse",
                "#dt-fill",
                "#dt-eraser",
                "#dt-picker",
            )
            for old_id in removed_paint_ids:
                with pytest.raises(NoMatches):
                    app.query_one(old_id)

            # Pure keyboard typing (including single keys bound on App: q, s, -)
            canvas.mirror = True
            await pilot.press("(", "q", "s", "-", "enter", "x")
            await pilot.pause()
            assert app._active_mode == "draw"
            assert canvas.model.glyphs[0, 0] == "("
            assert canvas.model.glyphs[0, canvas.model.width - 1] == ")"
            assert canvas.model.glyphs[0, 1] == "q"
            assert canvas.model.glyphs[0, 2] == "s"
            assert canvas.model.glyphs[0, 3] == "-"
            assert canvas.model.glyphs[1, 0] == "x"

            # Export directly from Type tab
            out_png = tmp_path / "typed.png"
            app.export_current_canvas(str(out_png), "png")
            assert out_png.is_file()

            # Promote typed ASCII art back to Studio
            app.query_one("#select-animate").value = "none"
            app.send_draw_to_studio()
            await pilot.pause()
            assert app._active_mode == "studio"
            assert dw.has_class("hidden")
            assert app._canvas_source_tag == "TYPE"
            assert app._canvas_last_grid is not None

            # Load built-in terminal skull stencil via /type skull & test assist typing + replay
            app.submit_omnibox("/type skull")
            await pilot.pause()
            assert app._active_mode == "draw"
            assert canvas.stencil_name == "skull"
            assert canvas.stencil_grid is not None
            canvas.model.clear()
            canvas.typing_mode = "assist"
            dw.sync_toolbar()
            await pilot.press("a", "b", "c")
            await pilot.pause()
            assert int(canvas.model.drawn.sum()) == 3
            assert canvas.start_replay() is True
            canvas.stop_replay()

        async def scenario():
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())


class TestResponsiveAndHDUX:
    def test_80x24_narrow_welcome_and_hint_surfaces(self, app):
        from textual.css.query import NoMatches

        async def check(app, pilot):
            assert ASCIITuiApp.ENABLE_COMMAND_PALETTE is False
            assert app.screen.has_class("narrow")
            hero = app.query_one("#welcome-hero", WelcomeHero)
            guide = app.query_one("#welcome-guide")
            meta = app.query_one("#canvas-meta", Static)
            files_btn = app.query_one("#btn-toggle-files")
            style_btn = app.query_one("#btn-toggle-style")
            footer = app.query_one("Footer")

            assert hero._compact is True
            assert str(footer.styles.display) == "none"
            assert str(files_btn.styles.display) == "none"
            assert str(style_btn.styles.display) == "none"
            assert meta.region.width >= 20
            assert guide.region.x >= 0
            assert guide.region.right <= 80
            assert app.query_one(OmniboxBar).region.bottom <= 24
            assert app.query_one("#status-bar").region.bottom <= 24
            with pytest.raises(NoMatches):
                app.query_one("#omnibox-hints")

        async def scenario():
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())

    def test_mutual_drawers_and_canvas_refit_100x30(self, app, tmp_path):
        wide_png = tmp_path / "panorama.png"
        Image.new("RGB", (320, 80), (40, 120, 200)).save(wide_png)

        async def wait_for_refit(pilot, full_w, timeout=2.0):
            # Canvas refit runs on a short deferred timer; under load a fixed
            # pause can be too small. Poll until the expected state appears.
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if app._canvas_last_grid.width < full_w:
                    return True
                await pilot.pause(0.05)
            return False

        async def check(app, pilot):
            app.query_one("#select-animate").value = "none"
            app.submit_omnibox(str(wide_png))
            await pilot.pause(0.25)

            full_w = app._canvas_last_grid.width
            inspector = app.query_one("#inspector", VerticalScroll)
            sidebar = app.query_one("#sidebar", Container)

            app.action_toggle_inspector()
            await pilot.pause(0.18)
            assert inspector.has_class("open")
            assert not sidebar.has_class("open")
            assert inspector.region.width >= 32
            assert await wait_for_refit(pilot, full_w)

            app.action_toggle_sidebar()
            await pilot.pause(0.18)
            assert sidebar.has_class("open")
            assert not inspector.has_class("open")
            assert await wait_for_refit(pilot, full_w)

        async def scenario():
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())

    def test_palette_autocomplete_and_hd_fx_commands(self, app):
        async def check(app, pilot):
            app.query_one("#select-animate").value = "none"
            app.submit_omnibox("/engine procedural")
            app.submit_omnibox("neon skyline")
            await pilot.pause(0.25)

            # Autocomplete box + hint bar
            omni = app.query_one("#omnibox", Input)
            omni.value = "/"
            app._update_autocomplete("/")
            await pilot.pause()
            assert app.query_one("#autocomplete-box").has_class("visible")
            assert app.query_one("#autocomplete-hint", Static).region.height == 1
            app._hide_autocomplete()

            # Command palette labels
            app.action_open_palette()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, CommandPaletteScreen)
            labels = [label for label, _cmd, _arg in screen._all_entries]
            assert not any(lbl.startswith("Action: ") for lbl in labels)
            assert any("[fx]" in lbl for lbl in labels)
            assert any("halfblock" in lbl for lbl in labels)
            app.pop_screen()
            await pilot.pause()

            # HD presets and stackable /fx commands
            app.submit_omnibox("/preset halfblock")
            await pilot.pause(0.1)
            assert app._canvas_last_grid.bg_rgb is not None

            app.submit_omnibox("/preset braille_hd")
            await pilot.pause(0.1)
            assert app._canvas_last_grid.bg_rgb is None

            app.submit_omnibox("/preset edge_art")
            await pilot.pause(0.1)

            app.submit_omnibox("/fx scanlines bloom")
            await pilot.pause(0.1)
            assert app.query_one("#fx-scanlines", Checkbox).value is True
            assert app.query_one("#fx-bloom", Checkbox).value is True

            app.submit_omnibox("/fx clear")
            await pilot.pause(0.1)
            assert app.query_one("#fx-scanlines", Checkbox).value is False
            assert app.query_one("#fx-bloom", Checkbox).value is False

        async def scenario():
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())

    def test_draw_tab_at_80x24(self, app):
        async def check(app, pilot):
            app.submit_omnibox("/draw")
            await pilot.pause()
            dw = app.query_one("#draw-workspace", DrawWorkspace)
            assert not dw.has_class("hidden")
            assert dw.region.width == 80
            assert app.query_one("#draw-status").region.bottom <= 24

        async def scenario():
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await check(app, pilot)

        asyncio.run(scenario())


class TestKeyboardAndModalUXFixes:
    def test_slash_autocomplete_enter_uses_highlighted_command(self, app, monkeypatch):
        submitted = []
        monkeypatch.setattr(app, "submit_omnibox", lambda raw: submitted.append(raw))

        async def check(app, pilot):
            omni = app.query_one("#omnibox", Input)
            popup = app.query_one("#autocomplete-popup", OptionList)
            omni.focus()
            omni.value = "/cl"
            await pilot.pause()
            assert popup.has_class("visible")
            idx = next(
                i
                for i, (name, _usage) in enumerate(app._autocomplete_items)
                if name == "/clear"
            )
            popup.highlighted = idx
            await pilot.press("enter")
            await pilot.pause()
            assert submitted == ["/clear"]
            assert not popup.has_class("visible")

        _scenario(app, check)

    def test_ctrl_v_in_input_is_not_hijacked(self, app, monkeypatch):
        import ascii_player.tui as tui_mod

        monkeypatch.setattr(tui_mod, "clipboard_image", lambda: None)
        monkeypatch.setattr(tui_mod, "clipboard_text", lambda: "https://example.com/a.png")

        async def check(app, pilot):
            url = app.query_one("#url-input", Input)
            omni = app.query_one("#omnibox", Input)
            url.value = ""
            omni.value = "keep"
            url.focus()
            app.action_paste_clipboard()
            await pilot.pause()
            assert url.value == ""
            assert omni.value == "keep"
            assert app.focused is url

        _scenario(app, check)

    def test_ctrl_v_with_button_focus_pastes_into_omnibox_only(self, app, monkeypatch):
        import ascii_player.tui as tui_mod

        monkeypatch.setattr(tui_mod, "clipboard_image", lambda: None)
        monkeypatch.setattr(tui_mod, "clipboard_text", lambda: "https://example.com/a.png")

        async def check(app, pilot):
            url = app.query_one("#url-input", Input)
            omni = app.query_one("#omnibox", Input)
            url.value = ""
            omni.value = ""
            app.query_one("#btn-mode-studio", Button).focus()
            await pilot.press("ctrl+v")
            await pilot.pause()
            assert omni.value == "https://example.com/a.png"
            assert url.value == ""
            assert app.focused is omni

        _scenario(app, check)

    def test_ctrl_v_in_draw_mode_pastes_into_visible_canvas(self, app, monkeypatch):
        import ascii_player.tui as tui_mod

        monkeypatch.setattr(tui_mod, "clipboard_image", lambda: None)
        monkeypatch.setattr(tui_mod, "clipboard_text", lambda: "HI")

        async def check(app, pilot):
            app.action_switch_draw()
            await pilot.pause()
            canvas = app.query_one("#draw-canvas", DrawCanvas)
            app.query_one("#btn-mode-draw", Button).focus()
            await pilot.press("ctrl+v")
            await pilot.pause()
            assert app._active_mode == "draw"
            assert "".join(canvas.model.glyphs[0, :2]) == "HI"
            assert app.focused is canvas
            assert not app.query_one("#omnibox", Input).has_focus
            assert app.query_one("#url-input", Input).value == ""

        _scenario(app, check)

    def test_escape_in_draw_mode_focuses_canvas_not_hidden_omnibox(self, app):
        async def check(app, pilot):
            app.action_switch_draw()
            await pilot.pause()
            canvas = app.query_one("#draw-canvas", DrawCanvas)
            app.query_one("#btn-mode-draw", Button).focus()
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is canvas
            assert not app.query_one("#omnibox", Input).has_focus
            before = int(canvas.model.drawn.sum())
            await pilot.press("x")
            await pilot.pause()
            assert int(canvas.model.drawn.sum()) > before

        _scenario(app, check)

    def test_bare_q_does_not_quit_while_button_focused(self, app, monkeypatch):
        quit_calls = []
        monkeypatch.setattr(app, "action_quit", lambda: quit_calls.append(True))
        assert not any(binding.key == "q" for binding in ASCIITuiApp.BINDINGS)

        async def check(app, pilot):
            app.query_one("#btn-mode-studio", Button).focus()
            await pilot.press("q")
            await pilot.pause()
            assert quit_calls == []
            assert app.is_running

        _scenario(app, check)

    def test_help_dialog_scrolls_and_closes_at_80x24(self, app):
        async def scenario():
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                app.push_screen(HelpScreen())
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, HelpScreen)
                body = screen.query_one("#help-body-scroll", VerticalScroll)
                dialog = screen.query_one("#help-dialog")
                assert isinstance(body, VerticalScroll)
                assert body.region.height <= screen.size.height
                assert dialog.region.height <= screen.size.height
                assert body.max_scroll_y > 0
                body.scroll_to(y=5, animate=False, force=True)
                await pilot.pause()
                assert body.scroll_y > 0
                await pilot.press("escape")
                await pilot.pause()
                assert not isinstance(app.screen, HelpScreen)

        asyncio.run(scenario())

    def test_mp4_is_cli_only_and_export_dialog_announces_substitution(
        self, app, monkeypatch
    ):
        notices = []
        monkeypatch.setattr(
            ExportScreen,
            "notify",
            lambda self, message, **kwargs: notices.append(message),
        )

        async def check(app, pilot):
            select = app.query_one("#select-export", Select)
            labels = [label for label, _value in select._options]
            assert "MP4 (CLI / pop-out only)" in labels
            assert "MP4" not in labels
            select.value = "mp4"  # still legal for CLI/pop-out configurations
            app.action_save_ascii()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ExportScreen)
            assert screen.query_one("#export-modal-fmt", Select).value == "png"
            assert notices
            assert "mp4" in notices[0].lower()
            assert "png" in notices[0].lower()
            await pilot.press("escape")
            await pilot.pause()

        _scenario(app, check)
