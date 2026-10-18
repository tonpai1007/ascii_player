"""Tests for ascii_player.player - video playback engine."""

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


class TestPlayerAudioSync:
    def _player(self):
        from ascii_player.config import PlayerConfig
        from ascii_player.player import VideoPlayer

        player = VideoPlayer("video.mp4", PlayerConfig())
        player.audio_path = "audio.wav"
        player.audio_process = MagicMock()
        player.controls = MagicMock()
        player.controls.get_volume.return_value = 50
        player.controls.get_speed.return_value = 1.0
        player.video_fps = 10.0
        player.fps = 10.0
        player.total_frames = 100
        return player

    def test_seek_audio_restarts_at_media_position(self):
        player = self._player()
        old_process = player.audio_process
        with patch("ascii_player.player.restart_audio", return_value="new") as restart:
            player._seek_audio(3.5)
        restart.assert_called_once_with(
            old_process, "audio.wav", 50, start_time=3.5, paused=False, speed=1.0
        )
        assert player.audio_process == "new"

    def test_seek_handler_restarts_audio(self):
        player = self._player()
        player.frame_num = 20
        player.controls.get_seek.return_value = 5
        player.cap = MagicMock()
        with patch.object(player, "_seek_audio") as seek_audio, \
                patch("ascii_player.player.time.sleep"):
            assert player._handle_seek() is True
        seek_audio.assert_called_once_with(7.0)

    def test_pause_resume_tracks_state(self):
        player = self._player()
        with patch("ascii_player.player.pause_audio") as pause:
            player._set_audio_paused(True)
        pause.assert_called_once()
        assert player._audio_paused is True

        with patch("ascii_player.player.resume_audio") as resume:
            player._set_audio_paused(False)
        resume.assert_called_once()
        assert player._audio_paused is False

    def test_volume_change_restarts_at_current_time(self):
        player = self._player()
        old_process = player.audio_process
        player.last_volume = 100
        player.controls.get_volume.return_value = 90
        with patch("ascii_player.player.restart_audio", return_value="new") as restart:
            player._update_controls(7.5)
        restart.assert_called_once_with(
            old_process, "audio.wav", 90, start_time=7.5, paused=False, speed=1.0
        )

    def test_speed_change_restarts_audio_with_tempo(self):
        player = self._player()
        old_process = player.audio_process
        player.last_volume = 50
        player.controls.get_speed.return_value = 2.0
        with patch("ascii_player.player.restart_audio", return_value="new") as restart:
            player._update_controls(4.0)
        restart.assert_called_once_with(
            old_process, "audio.wav", 50, start_time=4.0, paused=False, speed=2.0
        )


class TestPlayerControls:
    def test_controls_can_be_disabled(self):
        from ascii_player.config import PlayerConfig
        from ascii_player.player import VideoPlayer

        player = VideoPlayer("video.mp4", PlayerConfig(controls=False))
        player._setup_controls()
        assert player.controls is None

    def test_play_video_passes_controls_flag(self):
        from ascii_player.config import PlayerConfig

        config = PlayerConfig(controls=False)
        assert config.controls is False
        assert config.to_dict()["controls"] is False
        assert PlayerConfig.from_dict(config.to_dict()).controls is False


class TestPlayerCache:
    def _player(self):
        from ascii_player.config import PlayerConfig
        from ascii_player.player import VideoPlayer

        player = VideoPlayer("video.mp4", PlayerConfig(cache=True))
        player.total_frames = 10
        return player

    def test_incomplete_cache_is_rebuilt(self):
        player = self._player()
        fake_cache = MagicMock()
        fake_cache.load.return_value = {0: ["only one frame"]}
        fake_cache.is_complete.return_value = False

        with patch("ascii_player.player.FrameCache", return_value=fake_cache):
            player._setup_cache()

        assert player._using_cache is False
        fake_cache.clear.assert_called_once()
        fake_cache.set_cache_path.assert_called_once()

    def test_complete_cache_is_used(self):
        player = self._player()
        fake_cache = MagicMock()
        fake_cache.load.return_value = {i: [f"frame {i}"] for i in range(10)}
        fake_cache.is_complete.return_value = True

        with patch("ascii_player.player.FrameCache", return_value=fake_cache):
            player._setup_cache()

        assert player._using_cache is True
        fake_cache.set_cache_path.assert_not_called()
