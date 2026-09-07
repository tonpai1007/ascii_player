"""Audio visualizer for ASCII playback."""

import wave
from typing import List, Optional

import numpy as np
from loguru import logger


class AudioVisualizer:
    """Real-time audio waveform/frequency visualizer."""

    def __init__(self, audio_path: str, fps: float = 30.0, mode: str = "bars"):
        self.audio_path = audio_path
        self.fps = fps
        self.mode = mode
        self._data: Optional[np.ndarray] = None
        self._sample_rate: int = 44100
        self._frames: int = 0
        self._load_audio()

    def _load_audio(self) -> None:
        """Load audio data from WAV file and precompute visualization data."""
        if not self.audio_path:
            return

        try:
            with wave.open(self.audio_path, "rb") as w:
                self._sample_rate = w.getframerate()
                self._frames = w.getnframes()
                raw = w.readframes(self._frames)
                data = np.frombuffer(raw, dtype=np.int16)

                if w.getnchannels() == 2:
                    data = data.reshape(-1, 2).mean(axis=1).astype(np.int16)

                self._data = data
        except Exception as e:
            logger.warning("Failed to load audio for visualizer: {err}", err=str(e))
            self._data = None

    def _get_frame_index(self, current_time: float) -> int:
        """Convert playback time to audio sample index."""
        if self._data is None:
            return 0
        return int(current_time * self._sample_rate)

    def _compute_rms(self, start_idx: int, window_size: int) -> float:
        """Compute RMS amplitude for a window of audio samples."""
        if self._data is None or start_idx >= len(self._data):
            return 0.0

        end_idx = min(start_idx + window_size, len(self._data))
        window = self._data[start_idx:end_idx]
        if len(window) == 0:
            return 0.0

        rms = np.sqrt(np.mean(window.astype(np.float32) ** 2))
        return min(1.0, rms / 32768.0)

    def render(self, current_time: float, width: int = 80) -> List[str]:
        """Render visualization for the current playback time.

        Args:
            current_time: Current playback time in seconds
            width: Output width in characters

        Returns:
            List of strings representing the visualization
        """
        if self._data is None:
            return []

        if self.mode == "wave":
            return self._render_wave(current_time, width)
        return self._render_bars(current_time, width)

    def _render_bars(self, current_time: float, width: int) -> List[str]:
        """Render frequency-bar style visualization."""
        frame_idx = self._get_frame_index(current_time)
        window_size = max(1, int(self._sample_rate / self.fps))
        num_bars = min(width, 64)

        bars: List[int] = []
        for i in range(num_bars):
            offset = int(i * window_size / num_bars)
            chunk = max(1, window_size // num_bars)
            rms = self._compute_rms(frame_idx + offset, chunk)
            bars.append(int(rms * 12))

        lines: List[str] = []
        for row in range(12, 0, -1):
            line = "".join("█" if h >= row else " " for h in bars)
            lines.append(line)

        return lines

    def _render_wave(self, current_time: float, width: int) -> List[str]:
        """Render waveform-style visualization."""
        frame_idx = self._get_frame_index(current_time)
        window_size = max(1, int(self._sample_rate / self.fps))
        samples = np.linspace(0, window_size, width, dtype=int)

        lines: List[str] = []
        for i in range(8, -9, -1):
            line = ""
            for s in samples:
                idx = frame_idx + s
                if idx < len(self._data):
                    val = self._data[idx] / 32768.0
                    if i == 0:
                        line += "█" if abs(val) < 0.3 else "▓"
                    elif i > 0:
                        line += "▓" if val > i * 0.125 else " "
                    else:
                        line += "▓" if val < i * 0.125 else " "
                else:
                    line += " "
            lines.append(line)

        return lines
