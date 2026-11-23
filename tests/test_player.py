"""Tests for ascii_player.player - video playback engine."""

from unittest.mock import MagicMock

from ascii_player.player import _write_plain_frame, get_terminal_size


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

    def test_controls_false_does_not_start_controls(self, sample_video):
        from ascii_player.config import PlayerConfig
        from ascii_player.player import VideoPlayer

        cfg = PlayerConfig(width=20, fps=10, audio=False, controls=False)
        player = VideoPlayer(sample_video, cfg)
        player._setup_controls()
        assert player.controls is None


class TestSplitRendererAnsi:
    def test_preserves_ansi_on_color_frame(self):
        from ascii_player.lyrics import LyricsLine
        from ascii_player.renderer import SplitRenderer

        renderer = SplitRenderer(video_width=10, lyrics_width=10)
        colored_row = "\033[38;2;255;0;0m" + ("#" * 12) + "\033[0m"
        lines = renderer.render([colored_row], [(LyricsLine(0.0, "hello"), True)], 0.0)
        assert len(lines) == 1
        assert "\033[38;2;255;0;0m" in lines[0]
        assert "\033[0m" in lines[0]
