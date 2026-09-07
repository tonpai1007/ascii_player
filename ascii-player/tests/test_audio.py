"""Tests for ascii_player.audio - audio extraction/playback."""

import os
from unittest.mock import patch, MagicMock
import subprocess

from ascii_player.audio import extract_audio, play_audio, stop_audio, cleanup_audio


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
