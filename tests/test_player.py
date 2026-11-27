"""Tests for ascii_player.player - video playback engine."""

import time
from unittest.mock import MagicMock, patch

import pytest

from ascii_player.config import PlayerConfig
from ascii_player.player import VideoPlayer, _write_plain_frame, get_terminal_size


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


class TestP0PlaybackFixes:
    def test_play_validates_config_before_setup(self, capsys):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=0, audio=False, controls=False))
        with patch.object(player, "_setup_video") as setup:
            with pytest.raises(SystemExit) as exc:
                player.play()

        assert exc.value.code == 1
        setup.assert_not_called()
        assert "Configuration error" in capsys.readouterr().out

    def test_play_setup_failure_still_cleans_up(self, capsys):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        with patch.object(player, "_validate_video"):
            with patch.object(player, "_setup_video"):
                with patch.object(player, "_setup_components", side_effect=RuntimeError("boom")):
                    with patch.object(player, "_cleanup", wraps=player._cleanup) as cleanup:
                        with pytest.raises(RuntimeError, match="boom"):
                            player.play()

        cleanup.assert_called_once()
        assert "Done." not in capsys.readouterr().out

    def test_cleanup_is_idempotent_after_partial_setup(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.controls = MagicMock()
        player.cap = MagicMock()
        player.audio_process = MagicMock()
        player.audio_path = "audio.wav"
        player.frame_cache = MagicMock()
        player.exporter = MagicMock()
        player.start_time = time.monotonic()
        controls, cap = player.controls, player.cap
        frame_cache, exporter = player.frame_cache, player.exporter

        with patch("ascii_player.player.stop_audio"):
            with patch("ascii_player.player.cleanup_audio"):
                with patch.object(player, "_log_final_stats"):
                    player._cleanup()
                    player._cleanup()

        controls.stop.assert_called_once()
        cap.release.assert_called_once()
        frame_cache.save.assert_called_once()
        exporter.cleanup.assert_called_once()
        assert player.cap is None
        assert player.audio_process is None
        assert player.audio_path is None
        assert player.frame_cache is None
        assert player.exporter is None

    def test_setup_video_failure_releases_cap(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        with patch("ascii_player.player.cv2.VideoCapture") as capture:
            capture.return_value.isOpened.return_value = False
            with pytest.raises(SystemExit):
                player._setup_video()
            capture.return_value.release.assert_called_once()
        assert player.cap is None

    def test_seek_uses_video_fps_and_is_bounded(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.video_fps = 30
        player.fps = 60
        player.total_frames = 3000
        player.frame_num = 0
        controls = MagicMock()
        controls.get_seek.return_value = 5
        player.controls = controls

        with patch.object(player, "_reanchor_clock"):
            with patch.object(player, "_resync_audio"):
                assert player._handle_seek() is True
                assert player.frame_num == 150

                player.frame_num = 2998
                assert player._handle_seek() is True
                assert player.frame_num == 2999

                controls.get_seek.return_value = -5
                player.frame_num = 0
                assert player._handle_seek() is True
                assert player.frame_num == 0

    def test_volume_change_resyncs_audio_at_current_time(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        old = MagicMock()
        new = MagicMock()
        player.audio_process = old
        player.audio_path = "audio.wav"
        player.video_fps = 30
        player.frame_num = 3600
        controls = MagicMock()
        controls.get_volume.return_value = 80
        player.controls = controls

        with patch("ascii_player.player.restart_audio", return_value=new) as restart:
            player._update_controls(120.0)

        restart.assert_called_once_with(old, "audio.wav", 80, pytest.approx(120.0))
        assert player.audio_process is new

    def test_audio_resync_at_most_once_per_iteration(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.audio_path = "audio.wav"
        player.frame_num = 30
        player.video_fps = 30
        with patch("ascii_player.player.restart_audio") as restart:
            player._resync_audio()
            player._resync_audio()
        restart.assert_called_once()

    def test_ab_loop_jump_resyncs_audio(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.video_fps = 30
        player.total_frames = 1000
        player.frame_num = 400
        controls = MagicMock()
        controls.ab_bounds.return_value = (10.0, 12.0)
        controls.is_ab_loop_enabled.return_value = True
        player.controls = controls

        with patch.object(player, "_reanchor_clock"):
            with patch.object(player, "_resync_audio") as resync:
                player._handle_ab_loop(13.3)

        assert player.frame_num == 300
        resync.assert_called_once()

    def test_pause_and_resume_stop_and_restart_audio(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.total_frames = 2
        player.video_fps = 10
        player.fps = 10
        player.audio_path = "audio.wav"
        old = MagicMock()
        player.audio_process = old
        player.config.export = "gif"  # skip rendering/timing in this unit test

        controls = MagicMock()
        controls.should_quit.return_value = False
        controls.get_volume.return_value = 100
        controls.get_seek.return_value = 0
        controls.get_speed.return_value = 1.0
        controls.ab_bounds.return_value = (None, None)
        controls.is_ab_loop_enabled.return_value = False
        controls.pop_screenshot_request.return_value = False
        states = iter([True, False])
        controls.is_paused.side_effect = lambda: next(states, False)
        player.controls = controls
        player._get_frame = MagicMock(return_value=["row"])

        new = MagicMock()
        with patch("ascii_player.player.time.sleep"):
            with patch("ascii_player.player.stop_audio") as stop:
                with patch("ascii_player.player.restart_audio", return_value=new) as restart:
                    player._playback_loop()

        stop.assert_called_once_with(old)
        restart.assert_called_once_with(None, "audio.wav", 100, pytest.approx(0.0))
        assert player.audio_process is new

    def test_decode_failure_sets_premature_eof(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.cap = MagicMock()
        player.cap.read.return_value = (False, None)
        player.total_frames = 10
        player.frame_num = 3

        with patch("ascii_player.player.logger.warning") as warn:
            assert player._get_frame() is None

        assert player.premature_eof is True
        warn.assert_called_once()

    def test_final_stats_use_wall_start_not_reanchored_clock(self, capsys):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=20, audio=False, controls=False))
        player.start_time = time.monotonic() - 100  # rewound by a backward seek
        player.wall_start = time.monotonic() - 5
        player.frame_num = 100
        player.total_frames = 200

        with patch("ascii_player.player.logger.info") as info:
            player._log_final_stats()

        elapsed = info.call_args.kwargs["e"]
        assert 0 <= elapsed < 10
        assert "Done. Played 100/200" in capsys.readouterr().out

    def test_split_renderer_widths_are_positive(self):
        player = VideoPlayer("fake.mp4", PlayerConfig(width=80, lyrics_mode="split"))
        player.lyrics = MagicMock()
        with patch("ascii_player.player.get_terminal_size", return_value=(10, 24)):
            with patch("ascii_player.player.SplitRenderer") as renderer:
                player._setup_renderer()

        video_width, lyrics_width = renderer.call_args.args
        assert video_width >= 1
        assert lyrics_width >= 1
