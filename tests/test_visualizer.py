"""Tests for ascii_player.visualizer - audio visualization."""

import os
import wave

import numpy as np
import pytest

from ascii_player.visualizer import AudioVisualizer


@pytest.fixture
def wav_file(tmp_dir):
    """Create a synthetic WAV file with amplitude-modulated audio."""
    path = str(tmp_dir / "test.wav")
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t)
    data = (np.sin(2 * np.pi * 440 * t) * 32767 * envelope).astype(np.int16)

    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data.tobytes())

    return path


class TestAudioVisualizer:
    def test_loads_wav(self, wav_file):
        viz = AudioVisualizer(wav_file, fps=30, mode="bars")
        assert viz._data is not None
        assert viz._sample_rate == 44100

    def test_render_bars_returns_lines(self, wav_file):
        viz = AudioVisualizer(wav_file, fps=30, mode="bars")
        lines = viz.render(0.0, width=40)
        assert isinstance(lines, list)
        assert len(lines) > 0
        assert all(isinstance(line, str) for line in lines)

    def test_render_wave_returns_lines(self, wav_file):
        viz = AudioVisualizer(wav_file, fps=30, mode="wave")
        lines = viz.render(0.0, width=40)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_render_none_when_no_path(self):
        viz = AudioVisualizer("", fps=30, mode="bars")
        assert viz.render(0.0) == []

    def test_render_none_when_invalid_path(self):
        viz = AudioVisualizer("nonexistent.wav", fps=30, mode="bars")
        assert viz.render(0.0) == []

    def test_bars_width_clamped(self, wav_file):
        viz = AudioVisualizer(wav_file, fps=30, mode="bars")
        lines = viz.render(0.0, width=200)
        assert all(len(line) <= 64 for line in lines)

    def test_render_at_different_times(self, wav_file):
        viz = AudioVisualizer(wav_file, fps=30, mode="bars")
        lines_0 = viz.render(0.1, width=40)
        lines_1 = viz.render(0.9, width=40)
        assert isinstance(lines_0, list)
        assert isinstance(lines_1, list)
        assert len(lines_0) == len(lines_1)
