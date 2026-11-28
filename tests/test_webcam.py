"""Tests for ascii_player.webcam - backend selection and timing."""

import pytest

from ascii_player import webcam
from ascii_player.webcam import WebcamCapture, _select_backends


@pytest.mark.parametrize(
    "platform_name,expected_names",
    [
        ("win32", ["CAP_DSHOW", "CAP_MSMF", "CAP_ANY"]),
        ("linux", ["CAP_V4L2", "CAP_ANY"]),
        ("darwin", ["CAP_ANY"]),
    ],
)
def test_backends_are_platform_appropriate(monkeypatch, platform_name, expected_names):
    constants = {"CAP_DSHOW": 700, "CAP_MSMF": 800, "CAP_ANY": 100, "CAP_V4L2": 200}
    monkeypatch.setattr(webcam.sys, "platform", platform_name)
    for name, value in constants.items():
        monkeypatch.setattr(webcam.cv2, name, value, raising=False)

    assert _select_backends() == [constants[name] for name in expected_names]


def test_backends_are_deduplicated(monkeypatch):
    monkeypatch.setattr(webcam.sys, "platform", "linux")
    monkeypatch.setattr(webcam.cv2, "CAP_V4L2", 100, raising=False)
    monkeypatch.setattr(webcam.cv2, "CAP_ANY", 100, raising=False)

    assert _select_backends() == [100]


def test_open_tries_selected_backends(monkeypatch):
    monkeypatch.setattr(webcam, "_select_backends", lambda: [11, 22])
    attempts = []

    class FakeCapture:
        def __init__(self, index, backend):
            attempts.append((index, backend))
            self.backend = backend

        def isOpened(self):
            return self.backend == 22

        def get(self, prop):
            return 640

        def release(self):
            pass

    monkeypatch.setattr(webcam.cv2, "VideoCapture", FakeCapture)
    capture = WebcamCapture(camera_index=3)

    assert capture.open() is True
    assert attempts == [(3, 11), (3, 22)]
    assert capture.cap is not None


def test_close_is_idempotent():
    released = []

    class FakeCapture:
        def release(self):
            released.append(1)

    capture = WebcamCapture()
    capture.cap = FakeCapture()

    capture.close()
    capture.close()

    assert released == [1]
    assert capture.cap is None


def test_run_webcam_uses_monotonic_clock(monkeypatch):
    class FakeTime:
        def __init__(self):
            self.calls = 0

        def monotonic(self):
            self.calls += 1
            return float(self.calls)

        def time(self):
            raise AssertionError("wall clock used for FPS/pacing")

        def sleep(self, _seconds):
            pass

    fake_time = FakeTime()
    monkeypatch.setattr(webcam, "time", fake_time)

    class FakeWebcam:
        def __init__(self, *args, **kwargs):
            pass

        def open(self):
            return True

        def read_frame(self):
            return object()

        def apply_filter(self, frame):
            return frame

        def close(self):
            pass

    monkeypatch.setattr(webcam, "WebcamCapture", FakeWebcam)
    monkeypatch.setattr(webcam, "frame_to_ascii", lambda *args, **kwargs: ["frame"])

    original_write = webcam.sys.stdout.write
    interrupted = False

    def fake_write(*args, **kwargs):
        nonlocal interrupted
        text = str(args[0]) if args else ""
        if not interrupted and "Webcam | Frame" in text:
            interrupted = True
            raise KeyboardInterrupt
        return original_write(*args, **kwargs)

    monkeypatch.setattr(webcam.sys.stdout, "write", fake_write)

    webcam.run_webcam(target_fps=30)
    assert interrupted is True
    assert fake_time.calls >= 4
