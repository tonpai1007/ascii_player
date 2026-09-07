"""Tests for ascii_player.core - ASCII frame conversion."""

import numpy as np
from ascii_player.core import frame_to_ascii, _grayscale_ascii, _color_ascii
from ascii_player.config import ASCII_PRESETS


class TestFrameToAscii:
    def test_returns_list_of_strings(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=40)
        assert isinstance(result, list)
        assert all(isinstance(row, str) for row in result)

    def test_width_controls_output_columns(self, sample_frame):
        result_20 = frame_to_ascii(sample_frame, width=20)
        result_60 = frame_to_ascii(sample_frame, width=60)
        assert len(result_20[0]) <= 25
        assert len(result_60[0]) >= len(result_20[0])

    def test_default_preset_is_classic(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=20)
        chars_used = set("".join(result))
        classic_chars = set(ASCII_PRESETS["classic"])
        assert chars_used.issubset(classic_chars)

    def test_blocks_preset(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=20, preset="blocks")
        chars_used = set("".join(result))
        block_chars = set(ASCII_PRESETS["blocks"])
        assert chars_used.issubset(block_chars)

    def test_all_presets_produce_output(self, sample_frame):
        for preset in ASCII_PRESETS:
            result = frame_to_ascii(sample_frame, width=20, preset=preset)
            assert len(result) > 0, f"Preset '{preset}' produced no output"

    def test_color_mode_returns_ansi_codes(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=20, color=True)
        assert len(result) > 0
        assert "\033[38;2;" in result[0]

    def test_grayscale_mode_no_ansi(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=20, color=False)
        for row in result:
            assert "\033" not in row

    def test_zero_width_returns_empty(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=0)
        assert result == []

    def test_negative_width_returns_empty(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=-5)
        assert result == []

    def test_unknown_preset_falls_back_to_classic(self, sample_frame):
        result = frame_to_ascii(sample_frame, width=20, preset="nonexistent")
        chars_used = set("".join(result))
        classic_chars = set(ASCII_PRESETS["classic"])
        assert chars_used.issubset(classic_chars)

    def test_black_frame_uses_dark_chars(self, black_frame):
        result = frame_to_ascii(black_frame, width=10, preset="simple")
        assert len(result) > 0
        assert len(result[0]) > 0


class TestGrayscaleAscii:
    def test_output_dimensions(self):
        gray = np.zeros((11, 20), dtype=np.uint8)
        result = _grayscale_ascii(gray, ".,-~:;=!*#$@")
        assert len(result) == 11
        assert all(len(row) == 20 for row in result)

    def test_empty_gray_returns_empty(self):
        result = _grayscale_ascii(np.zeros((0, 20), dtype=np.uint8), ".,-~")
        assert result == []


class TestColorAscii:
    def test_output_has_ansi(self):
        resized = np.random.randint(0, 255, (11, 20, 3), dtype=np.uint8)
        gray = np.random.randint(0, 255, (11, 20), dtype=np.uint8)
        result = _color_ascii(resized, gray, ".,-~:;=!*#$@")
        assert len(result) == 11
        for row in result:
            assert "\033[38;2;" in row

    def test_empty_resized_returns_empty(self):
        resized = np.zeros((0, 20, 3), dtype=np.uint8)
        gray = np.zeros((0, 20), dtype=np.uint8)
        result = _color_ascii(resized, gray, ".,-~")
        assert result == []


class TestFrameToAsciiEdgeCases:
    def test_none_frame_returns_empty(self):
        assert frame_to_ascii(None, width=20) == []

    def test_zero_height_frame_returns_empty(self):
        frame = np.zeros((0, 40, 3), dtype=np.uint8)
        assert frame_to_ascii(frame, width=20) == []

    def test_zero_width_frame_returns_empty(self):
        frame = np.zeros((40, 0, 3), dtype=np.uint8)
        assert frame_to_ascii(frame, width=20) == []

    def test_extreme_wide_aspect_does_not_crash(self):
        # Very wide frame -> new_h would be tiny; must still return >= 1 row.
        frame = np.zeros((1, 2000, 3), dtype=np.uint8)
        result = frame_to_ascii(frame, width=80)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_extreme_tall_aspect_is_capped(self):
        # Very tall frame -> new_h capped to avoid pathological allocation.
        frame = np.zeros((10000, 8, 3), dtype=np.uint8)
        result = frame_to_ascii(frame, width=80)
        assert len(result) <= 1024

    def test_single_row_frame(self):
        frame = np.zeros((1, 50, 3), dtype=np.uint8)
        result = frame_to_ascii(frame, width=20)
        assert len(result) >= 1
        assert all(len(row) == 20 for row in result)
