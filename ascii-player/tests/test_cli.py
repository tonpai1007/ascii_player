"""Tests for ascii_player.cli - command-line interface."""

import sys
from unittest.mock import patch
from ascii_player.cli import parse_args


class TestParseArgs:
    def _parse(self, argv):
        with patch.object(sys, "argv", ["ascii-player"] + argv):
            return parse_args()

    def test_no_args(self):
        args = self._parse([])
        assert args.video is None
        assert args.width is None
        assert args.fps is None
        assert args.color is None

    def test_video_path(self):
        args = self._parse(["video.mp4"])
        assert args.video == "video.mp4"

    def test_width(self):
        args = self._parse(["-w", "120"])
        assert args.width == 120

    def test_width_min_1(self):
        args = self._parse(["-w", "0"])
        assert args.width == 1

    def test_width_negative_clamped(self):
        args = self._parse(["-w", "-10"])
        assert args.width == 1

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

    def test_no_color_flag(self):
        args = self._parse(["--no-color"])
        assert args.color is False

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

    def test_lyrics_mode_default_is_none(self):
        assert self._parse([]).lyrics_mode is None

    def test_webcam(self):
        args = self._parse(["--webcam"])
        assert args.webcam is True

    def test_camera_index(self):
        args = self._parse(["--camera", "2"])
        assert args.camera == 2

    def test_tui(self):
        args = self._parse(["-t"])
        assert args.tui is True

    def test_visualizer(self):
        args = self._parse(["--visualizer", "bars"])
        assert args.visualizer == "bars"

    def test_visualizer_default_is_none(self):
        assert self._parse([]).visualizer is None

    def test_combined_args(self):
        args = self._parse(["video.mp4", "-w", "100", "-c", "-p", "blocks", "--no-audio"])
        assert args.video == "video.mp4"
        assert args.width == 100
        assert args.color is True
        assert args.preset == "blocks"
        assert args.no_audio is True
