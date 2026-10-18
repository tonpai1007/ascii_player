"""Tests for ascii_player.webcam - camera setup and option plumbing."""

from unittest.mock import patch

import pytest

from ascii_player import webcam


class TestRunWebcam:
    def test_passes_camera_index_and_filter(self):
        captured = {}

        class FakeWebcam:
            def __init__(self, camera_index=0, filter="none"):
                captured["camera_index"] = camera_index
                captured["filter"] = filter

            def open(self):
                return False

        with patch.object(webcam, "WebcamCapture", FakeWebcam):
            with pytest.raises(SystemExit):
                webcam.run_webcam(camera_index=2, filter="edge")

        assert captured == {"camera_index": 2, "filter": "edge"}

    def test_linux_backends_prefer_v4l2(self, monkeypatch):
        monkeypatch.setattr(webcam.sys, "platform", "linux")
        assert webcam.WebcamCapture._backends()[0] == webcam.cv2.CAP_V4L2

    def test_windows_backends_prefer_dshow(self, monkeypatch):
        monkeypatch.setattr(webcam.sys, "platform", "win32")
        assert webcam.WebcamCapture._backends()[0] == webcam.cv2.CAP_DSHOW
