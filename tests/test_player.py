"""Tests for ascii_player.player - video playback engine."""

import os
from unittest.mock import patch, MagicMock

from ascii_player.player import get_terminal_size, _write_plain_frame


class TestGetTerminalSize:
    def test_returns_tuple(self):
        cols, rows = get_terminal_size()
        assert isinstance(cols, int)
        assert isinstance(rows, int)
        assert cols > 0
        assert rows > 0

    def test_default_fallback(self):
        cols, rows = get_terminal_size()
        assert cols >= 80
        assert rows >= 24


class TestWritePlainFrame:
    def test_renders_without_controls(self, capsys):
        ascii_frame = ["abc", "def", "ghi"]
        _write_plain_frame(ascii_frame, 60, 0, 100, 0.033, 3.3, controls=None)
        captured = capsys.readouterr()
        assert "abc" in captured.out
        assert "Frame 1/100" in captured.out

    def test_renders_with_controls(self, capsys):
        ascii_frame = ["abc"]
        mock_controls = MagicMock()
        mock_controls.render_controls.return_value = ("[controls]", "State: PLAYING")
        _write_plain_frame(ascii_frame, 60, 0, 100, 0.033, 3.3, controls=mock_controls)
        captured = capsys.readouterr()
        assert "[controls]" in captured.out
        assert "State: PLAYING" in captured.out


class TestPlayVideo:
    def test_nonexistent_file(self):
        from ascii_player.player import play_video
        try:
            play_video("/nonexistent/video.mp4", audio=False, controls=False)
        except SystemExit as e:
            assert e.code == 1

    def test_play_video_with_mock(self, sample_video):
        from ascii_player.player import play_video
        play_video(
            sample_video,
            width=20,
            fps=10,
            color=False,
            preset="simple",
            audio=False,
            controls=False,
            cache=False,
        )
