"""Tests for ascii_player.audio - audio extraction/playback."""

import os
import signal
from unittest.mock import patch, MagicMock
import subprocess

from ascii_player.audio import (
    cleanup_audio,
    extract_audio,
    pause_audio,
    play_audio,
    restart_audio,
    resume_audio,
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
        with patch("ascii_player.audio.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 60)):
            result = extract_audio(video)
            assert result is None


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

    def test_start_time_adds_seek_argument(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen", return_value=MagicMock()) as popen:
            play_audio(audio, volume=80, start_time=12.5)
        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("-ss") + 1] == "12.500"
        assert cmd[cmd.index("-volume") + 1] == "80"

    def test_no_seek_argument_at_zero(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen", return_value=MagicMock()) as popen:
            play_audio(audio, start_time=0)
        assert "-ss" not in popen.call_args[0][0]


class TestAudioControl:
    def test_pause_sends_sigstop(self):
        proc = MagicMock()
        proc.poll.return_value = None
        assert pause_audio(proc) is True
        proc.send_signal.assert_called_once_with(signal.SIGSTOP)

    def test_resume_sends_sigcont(self):
        proc = MagicMock()
        proc.poll.return_value = None
        assert resume_audio(proc) is True
        proc.send_signal.assert_called_once_with(signal.SIGCONT)

    def test_control_already_exited_process(self):
        proc = MagicMock()
        proc.poll.return_value = 0
        assert pause_audio(proc) is False
        proc.send_signal.assert_not_called()

    def test_restart_resumes_at_position(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        new_proc = MagicMock()
        with patch("ascii_player.audio.stop_audio") as stop, \
                patch("ascii_player.audio.play_audio", return_value=new_proc) as play:
            result = restart_audio(MagicMock(), audio, volume=70, start_time=9.0)
        stop.assert_called_once()
        play.assert_called_once_with(audio, 70, start_time=9.0, speed=1.0)
        assert result is new_proc

    def test_atempo_none_at_normal_speed(self):
        from ascii_player.audio import _atempo_filter

        assert _atempo_filter(1.0) is None

    def test_atempo_chains_for_fast_speed(self):
        from ascii_player.audio import _atempo_filter

        assert _atempo_filter(3.0) == "atempo=2.0,atempo=1.5000"

    def test_atempo_chains_for_slow_speed(self):
        from ascii_player.audio import _atempo_filter

        assert _atempo_filter(0.25) == "atempo=0.5,atempo=0.5000"

    def test_play_audio_adds_tempo_filter(self, tmp_dir):
        audio = str(tmp_dir / "audio.wav")
        with open(audio, "wb") as f:
            f.write(b"fake")
        with patch("ascii_player.audio.subprocess.Popen", return_value=MagicMock()) as popen:
            play_audio(audio, speed=2.0)
        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("-af") + 1] == "atempo=2.0000"


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
