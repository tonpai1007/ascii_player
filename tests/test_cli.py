"""Tests for ascii_player.cli - command-line interface."""

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import ascii_player.__main__ as entry
from ascii_player.cli import parse_args
from ascii_player.config import DEFAULT_CONFIG, DEFAULT_WIDTH
from ascii_player.url_loader import ResolvedURL


class TestParseArgs:
    def _parse(self, argv):
        with patch.object(sys, "argv", ["ascii-player"] + argv):
            return parse_args()

    def test_no_args(self):
        args = self._parse([])
        assert args.video is None
        assert args.width == DEFAULT_WIDTH
        assert args.fps is None
        assert args.color is False

    def test_video_path(self):
        args = self._parse(["video.mp4"])
        assert args.video == "video.mp4"

    def test_width(self):
        args = self._parse(["-w", "120"])
        assert args.width == 120

    def test_width_zero_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(["-w", "0"])

    def test_width_negative_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(["-w", "-10"])

    def test_width_non_integer_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(["-w", "abc"])

    def test_fps(self):
        args = self._parse(["-f", "60"])
        assert args.fps == 60.0

    def test_fps_min_01(self):
        args = self._parse(["-f", "0"])
        assert args.fps == 0.1

    def test_fps_negative_clamped(self):
        args = self._parse(["-f", "-5"])
        assert args.fps == 0.1

    def test_color_flag(self):
        args = self._parse(["-c"])
        assert args.color is True

    def test_preset(self):
        args = self._parse(["-p", "blocks"])
        assert args.preset == "blocks"

    def test_no_audio(self):
        args = self._parse(["--no-audio"])
        assert args.no_audio is True

    def test_no_controls(self):
        args = self._parse(["--no-controls"])
        assert args.no_controls is True

    def test_cache(self):
        args = self._parse(["--cache"])
        assert args.cache is True

    def test_export_gif(self):
        args = self._parse(["--export", "gif"])
        assert args.export == "gif"

    def test_export_mp4(self):
        args = self._parse(["--export", "mp4"])
        assert args.export == "mp4"

    def test_output_path(self):
        args = self._parse(["-o", "out.gif"])
        assert args.output == "out.gif"

    def test_lyrics(self):
        args = self._parse(["-l", "song.lrc"])
        assert args.lyrics == "song.lrc"

    def test_lyrics_mode(self):
        args = self._parse(["--lyrics-mode", "fullscreen"])
        assert args.lyrics_mode == "fullscreen"

    def test_webcam(self):
        args = self._parse(["--webcam"])
        assert args.webcam is True

    def test_camera_index(self):
        args = self._parse(["--camera", "2"])
        assert args.camera == 2

    def test_tui(self):
        args = self._parse(["-t"])
        assert args.tui is True

    def test_animate_flag(self):
        args = self._parse(["--animate", "rain"])
        assert args.animate == "rain"

    def test_dither_invert_loop_hold_clipboard(self):
        args = self._parse(["--dither", "--invert", "--loop", "--hold", "2.5", "--clipboard"])
        assert args.dither is True
        assert args.invert is True
        assert args.loop is True
        assert args.hold == 2.5
        assert args.clipboard is True

    def test_export_text_choices(self):
        for choice in ("txt", "ans", "html", "png"):
            args = self._parse(["--export", choice])
            assert args.export == choice

    def test_prompt_flags(self):
        args = self._parse(
            ["--prompt", "cyberpunk cat", "--prompt-engine", "procedural", "--font", "doom"]
        )
        assert args.prompt == "cyberpunk cat"
        assert args.prompt_engine == "procedural"
        assert args.font == "doom"

    def test_combined_args(self):
        args = self._parse(["video.mp4", "-w", "100", "-c", "-p", "blocks", "--no-audio"])
        assert args.video == "video.mp4"
        assert args.width == 100
        assert args.color is True
        assert args.preset == "blocks"
        assert args.no_audio is True


def _main_args(video="https://example.com/page", **overrides):
    values = dict(
        video=video,
        tui=False,
        webcam=False,
        clipboard=False,
        prompt=None,
        width=DEFAULT_WIDTH,
        fps=None,
        color=False,
        no_audio=False,
        preset=None,
        visualizer="none",
        export=None,
        output=None,
        lyrics=None,
        lyrics_mode="split",
        no_controls=False,
        camera=0,
        cache=False,
        animate="none",
        invert=False,
        dither=False,
        crop=False,
        aspect=0.55,
        loop=False,
        hold=0.0,
        prompt_engine="auto",
        font="slant",
        filter="none",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_main(monkeypatch, args, config=None):
    monkeypatch.setattr(entry, "parse_args", lambda: args)
    monkeypatch.setattr(entry, "setup_logger", lambda **kwargs: None)
    monkeypatch.setattr(
        entry, "load_config", lambda: {**DEFAULT_CONFIG, **(config or {})}
    )
    played = {}
    monkeypatch.setattr(entry, "play_video", lambda path, **kwargs: played.update(
        path=path, **kwargs
    ))
    return played


class TestMainUrlResolution:
    def test_resolve_exception_is_visible(self, monkeypatch, capsys):
        played = _patch_main(monkeypatch, _main_args())

        def boom(url):
            raise RuntimeError("DNS failed")

        monkeypatch.setattr("ascii_player.url_loader.resolve_url", boom)
        entry.main()
        assert "Warning: could not resolve URL: DNS failed" in capsys.readouterr().out
        assert played["path"] == "https://example.com/page"

    def test_resolved_video_is_used_and_config_visualizer_passed(
        self, monkeypatch, capsys, tmp_path
    ):
        args = _main_args(video="https://example.com/clip.mp4")
        played = _patch_main(monkeypatch, args, config={"visualizer": "bars"})
        saved = tmp_path / "clip.mp4"
        saved.write_bytes(b"video")
        resolved = ResolvedURL(
            url=args.video, kind="video", title="clip", saved_path=str(saved)
        )
        monkeypatch.setattr(
            "ascii_player.url_loader.resolve_url", lambda url: resolved
        )
        entry.main()
        assert played["path"] == str(saved)
        assert played["visualizer"] == "bars"

    def test_unusable_url_exits_with_error(self, monkeypatch, capsys):
        _patch_main(monkeypatch, _main_args(video="https://example.com/clip.mp4"))
        resolved = ResolvedURL(
            url="https://example.com/clip.mp4", kind="video", title="clip"
        )
        monkeypatch.setattr(
            "ascii_player.url_loader.resolve_url", lambda url: resolved
        )
        with pytest.raises(SystemExit) as exc:
            entry.main()
        assert exc.value.code == 1
        assert "did not resolve to a playable video or image" in capsys.readouterr().out


class TestMainImageExport:
    def test_gif_export_passes_color_flag(self, monkeypatch, capsys, tmp_path):
        args = _main_args(
            video=str(tmp_path / "pic.png"),
            export="gif",
            output=str(tmp_path / "out.gif"),
            color=True,
        )
        _patch_main(monkeypatch, args)
        calls = {}

        def fake_export(source, path, **kwargs):
            calls.update(source=source, path=path, **kwargs)
            return path

        monkeypatch.setattr("ascii_player.image_player.export_image", fake_export)
        entry.main()
        capsys.readouterr()
        assert calls["color"] is True
        assert calls["path"] == args.output

    def test_ans_export_passes_color_flag(self, monkeypatch, capsys, tmp_path):
        args = _main_args(
            video=str(tmp_path / "pic.png"),
            export="ans",
            output=str(tmp_path / "out.ans"),
            color=False,
        )
        _patch_main(monkeypatch, args)
        calls = {}

        def fake_export(source, path, **kwargs):
            calls.update(source=source, path=path, **kwargs)
            return path

        monkeypatch.setattr("ascii_player.image_player.export_still", fake_export)
        entry.main()
        capsys.readouterr()
        assert calls["color"] is False
        assert calls["path"] == args.output
