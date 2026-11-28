"""Tests for ascii_player.audio - audio extraction/playback."""

import os
import subprocess
from unittest.mock import MagicMock, patch

from ascii_player.audio import (
    cleanup_audio,
    extract_audio,
    play_audio,
    restart_audio,
    stop_audio,
)


class TestExtractAudio:
    def test_returns_none_when_ffmpeg_missing(self, tmp_dir):
        video = str(tmp_dir / "test.mp4")
        with patch("ascii_player.audio.subprocess.run", side_effect=FileNotFoundError):
            result = extract_audio(video)
            assert result is None

    def test_returns_none_on_nonzero_exit(self, tmp_dir):
        video = str(tmp_dir / "test.mp4")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error msg"
        with patch("ascii_player.audio.subprocess.run", return_value=mock_result):
            result = extract_audio(video)
            assert result is None

    def test_returns_path_on_success(self, tmp_dir):
        video = str(tmp_dir / "test.mp4")

        def fake_run(cmd, **kwargs):
            audio_path = cmd[-1]
            with open(audio_path, "wb") as f:
                f.write(b"RIFF....WAVEfmt ")
            mock = MagicMock()
            mock.returncode = 0
            return mock

        with patch("ascii_player.audio.subprocess.run", side_effect=fake_run):
            result = extract_audio(video)
            assert result is not None
            assert result.endswith("audio.wav")

    def test_returns_none_on_timeout(self, tmp_dir):
        video = str(tmp_dir / "test.mp4")
        with patch(
            "ascii_player.audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 60),
        ):
            result = extract_audio(video)
            assert result is None

    def test_default_timeout_is_300(self, tmp_dir):
        with patch("ascii_player.audio.subprocess.run") as run:
            extract_audio(str(tmp_dir / "test.mp4"))
        assert run.call_args.kwargs["timeout"] == 300

    def test_custom_timeout_is_used(self, tmp_dir):
        with patch("ascii_player.audio.subprocess.run") as run:
            extract_audio(str(tmp_dir / "test.mp4"), timeout=12)
        assert run.call_args.kwargs["timeout"] == 12

    def test_timeout_warning_names_timeout(self, tmp_dir):
        with patch(
            "ascii_player.audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 45),
        ):
            with patch("ascii_player.audio.logger") as log:
                result = extract_audio(str(tmp_dir / "test.mp4"), timeout=45)
        assert result is None
        assert any("45" in str(call) for call in log.warning.call_args_list)


class TestPlayAudio:
    def test_returns_none_for_none_path(self):
        assert play_audio(None) is None

    def test_returns_none_for_nonexistent(self):
        assert play_audio("/nonexistent/audio.wav") is None

    def test_returns_none_when_ffplay_missing(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen", side_effect=FileNotFoundError):
            result = play_audio(audio)
            assert result is None

    def test_returns_process_on_success(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        mock_proc = MagicMock()
        with patch("ascii_player.audio.subprocess.Popen", return_value=mock_proc):
            result = play_audio(audio)
            assert result is mock_proc

    def test_start_time_is_passed_to_ffplay(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen") as popen:
            play_audio(audio, volume=80, start_time=12.3456)

        cmd = popen.call_args.args[0]
        assert cmd[cmd.index("-volume") + 1] == "80"
        assert cmd[cmd.index("-ss") + 1] == "12.346"
        assert cmd.index("-ss") < cmd.index(audio)

    def test_default_start_time_is_zero(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen") as popen:
            play_audio(audio)

        cmd = popen.call_args.args[0]
        assert cmd[cmd.index("-ss") + 1] == "0.000"


class TestRestartAudio:
    def test_restart_passes_volume_and_offset(self):
        old = MagicMock()
        with patch("ascii_player.audio.stop_audio") as stop:
            with patch("ascii_player.audio.play_audio", return_value="new") as play:
                result = restart_audio(old, "audio.wav", 75, 4.5)

        stop.assert_called_once_with(old)
        play.assert_called_once_with("audio.wav", 75, start_time=4.5)
        assert result == "new"

    def test_three_argument_call_is_backward_compatible(self):
        with patch("ascii_player.audio.play_audio") as play:
            restart_audio(None, "audio.wav")
        play.assert_called_once_with("audio.wav", 100, start_time=0.0)


class TestStopAudio:
    def test_stop_none_safe(self):
        stop_audio(None)

    def test_stop_terminated_process(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        stop_audio(mock_proc)
        mock_proc.terminate.assert_called_once()

    def test_stop_already_exited(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        stop_audio(mock_proc)
        mock_proc.terminate.assert_not_called()


class TestCleanupAudio:
    def test_removes_file(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        cleanup_audio(audio)
        assert not os.path.exists(audio)

    def test_none_safe(self):
        cleanup_audio(None)

    def test_nonexistent_safe(self):
        cleanup_audio("/nonexistent/audio.wav")

    def test_retries_then_succeeds(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        remove = MagicMock(side_effect=[OSError("locked"), OSError("locked"), None])
        with patch("ascii_player.audio.os.remove", remove):
            with patch("ascii_player.audio.time.sleep") as sleep:
                with patch("ascii_player.audio.logger") as log:
                    cleanup_audio(audio)
        assert remove.call_count == 3
        assert sleep.call_count == 2
        log.warning.assert_not_called()

    def test_persistent_failure_is_logged(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.os.remove", side_effect=OSError("locked")) as remove:
            with patch("ascii_player.audio.time.sleep") as sleep:
                with patch("ascii_player.audio.logger") as log:
                    cleanup_audio(audio)
        assert remove.call_count == 3
        assert sleep.call_count <= 4
        assert any("Failed to remove" in str(call) for call in log.warning.call_args_list)

