"""Tests for ascii_player.youtube - YouTube download."""

from unittest.mock import patch, MagicMock
import subprocess

from ascii_player.youtube import is_youtube_url, download_youtube_video, cleanup_temp_file


class TestIsYoutubeUrl:
    def test_standard_url(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_short_url(self):
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")

    def test_mobile_url(self):
        assert is_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_non_youtube(self):
        assert not is_youtube_url("https://vimeo.com/12345")

    def test_empty_string(self):
        assert not is_youtube_url("")

    def test_non_youtube_lookalike_domain(self):
        assert not is_youtube_url("https://notyoutube.com/watch?v=x")
        assert not is_youtube_url("https://youtube.com.evil.example/watch?v=x")

    def test_plain_text(self):
        assert not is_youtube_url("hello world")


class TestDownloadYoutubeVideo:
    def test_returns_none_on_file_not_found(self):
        with patch("ascii_player.youtube.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit):
                download_youtube_video("https://youtube.com/watch?v=test")

    def test_returns_none_on_nonzero_exit(self):
        mock = MagicMock()
        mock.returncode = 1
        mock.stderr = "error"
        with patch("ascii_player.youtube.subprocess.run", return_value=mock):
            with pytest.raises(SystemExit):
                download_youtube_video("https://youtube.com/watch?v=test")

    def test_returns_none_on_timeout(self):
        with patch("ascii_player.youtube.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 300)):
            with pytest.raises(SystemExit):
                download_youtube_video("https://youtube.com/watch?v=test")


class TestCleanupTempFile:
    def test_removes_file(self, tmp_dir):
        f = tmp_dir / "temp.mp4"
        f.write_bytes(b"fake")
        cleanup_temp_file(str(f))
        assert not f.exists()

    def test_none_safe(self):
        cleanup_temp_file(None)

    def test_nonexistent_safe(self):
        cleanup_temp_file("/nonexistent/file.mp4")


import pytest
