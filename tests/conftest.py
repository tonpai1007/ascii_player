"""Shared test fixtures for ascii_player."""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import numpy as np
import pytest

try:
    import cv2
except ImportError:
    cv2 = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_frame():
    """Create a sample BGR frame (100x80, gradient pattern)."""
    frame = np.zeros((100, 80, 3), dtype=np.uint8)
    for y in range(100):
        for x in range(80):
            frame[y, x] = [int(x * 255 / 80), int(y * 255 / 100), 128]
    return frame


@pytest.fixture
def small_frame():
    """Create a small 10x10 frame."""
    return np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)


@pytest.fixture
def black_frame():
    """Create a black 50x50 frame."""
    return np.zeros((50, 50, 3), dtype=np.uint8)


@pytest.fixture
def white_frame():
    """Create a white 50x50 frame."""
    return np.full((50, 50, 3), 255, dtype=np.uint8)


@pytest.fixture
def tmp_dir():
    """Create a temporary directory as a Path, cleaned up after test."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_video(tmp_dir):
    """Create a minimal 3-second test video file. Skipped if OpenCV is missing."""
    if cv2 is None:
        pytest.skip("OpenCV (cv2) is not installed")
    path = str(tmp_dir / "test.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, 10.0, (64, 64))
    for _ in range(30):
        frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()
    return path


@pytest.fixture
def lrc_file(tmp_dir):
    """Create a sample LRC lyrics file."""
    path = tmp_dir / "test.lrc"
    content = """[ti:Test Song]
[ar:Test Artist]
[00:00.00]Intro
[00:05.00]First line
[00:10.00]Second line
[00:15.00]Third line
"""
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def srt_file(tmp_dir):
    """Create a sample SRT subtitle file."""
    path = tmp_dir / "test.srt"
    content = """1
00:00:01,000 --> 00:00:04,000
First subtitle

2
00:00:05,000 --> 00:00:08,000
Second subtitle

3
00:00:09,000 --> 00:00:12,000
Third subtitle
"""
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def ass_file(tmp_dir):
    """Create a sample ASS subtitle file."""
    path = tmp_dir / "test.ass"
    content = """[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,First line
Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Second line
Dialogue: 0,0:00:09.00,0:00:12.00,Default,,0,0,0,,Third line
"""
    path.write_text(content, encoding="utf-8")
    return str(path)
