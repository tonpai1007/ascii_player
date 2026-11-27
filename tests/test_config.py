"""Tests for ascii_player.config validation helpers."""

import math

import pytest

from ascii_player.config import EXPORT_FORMATS, PlayerConfig, is_safe_youtube_url


class TestPlayerConfigValidate:
    def test_default_config_is_valid(self):
        PlayerConfig().validate()

    @pytest.mark.parametrize("bad", [0, -1, 1.5, "80", True, None])
    def test_width_rejects_non_positive_and_non_integer(self, bad):
        cfg = PlayerConfig(width=bad)
        with pytest.raises(ValueError) as exc:
            cfg.validate()
        assert repr(bad) in str(exc.value)

    def test_width_accepts_one(self):
        PlayerConfig(width=1).validate()

    @pytest.mark.parametrize("bad", [0, -1.0, math.inf, math.nan, "24", True])
    def test_fps_rejects_non_positive_non_finite_and_non_numeric(self, bad):
        cfg = PlayerConfig(fps=bad)
        with pytest.raises(ValueError) as exc:
            cfg.validate()
        assert repr(bad) in str(exc.value)

    @pytest.mark.parametrize("good", [None, 0.5, 1, 24.0])
    def test_fps_accepts_positive_finite_values(self, good):
        cfg = PlayerConfig(fps=good)
        cfg.validate()
        assert cfg.fps == good

    def test_unknown_preset_rejected_with_value(self):
        with pytest.raises(ValueError, match="nope"):
            PlayerConfig(preset="nope").validate()

    @pytest.mark.parametrize("bad", ["sideways", "", None, True])
    def test_invalid_lyrics_mode_rejected(self, bad):
        with pytest.raises(ValueError) as exc:
            PlayerConfig(lyrics_mode=bad).validate()
        assert repr(bad) in str(exc.value)

    @pytest.mark.parametrize("bad", ["spectrum", "BARS", None, 1])
    def test_invalid_visualizer_rejected(self, bad):
        with pytest.raises(ValueError) as exc:
            PlayerConfig(visualizer=bad).validate()
        assert repr(bad) in str(exc.value)

    @pytest.mark.parametrize("fmt", EXPORT_FORMATS)
    def test_all_documented_export_formats_accepted(self, fmt):
        cfg = PlayerConfig(export=fmt)
        cfg.validate()
        assert cfg.export == fmt

    def test_export_none_accepted(self):
        PlayerConfig(export=None).validate()

    @pytest.mark.parametrize("bad", ["avi", "GIF", 1])
    def test_unsupported_export_rejected(self, bad):
        with pytest.raises(ValueError) as exc:
            PlayerConfig(export=bad).validate()
        assert repr(bad) in str(exc.value)

    @pytest.mark.parametrize("bad", [-1, 1.5, "0", True, None])
    def test_camera_index_rejected(self, bad):
        with pytest.raises(ValueError) as exc:
            PlayerConfig(camera_index=bad).validate()
        assert repr(bad) in str(exc.value)

    @pytest.mark.parametrize(
        "field", ["audio", "color", "cache", "controls", "webcam"]
    )
    @pytest.mark.parametrize("bad", [0, 1, "yes", None])
    def test_boolean_fields_reject_non_bool(self, field, bad):
        cfg = PlayerConfig(**{field: bad})
        with pytest.raises(ValueError) as exc:
            cfg.validate()
        assert repr(bad) in str(exc.value)
        assert field.capitalize() in str(exc.value)


class TestIsSafeYoutubeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://youtube.com/watch?v=abcdefghijk",
            "https://www.youtube.com/watch?v=abcdefghijk",
            "http://m.youtube.com/watch?v=abcdefghijk",
            "https://youtu.be/abcdefghijk",
            "https://www.youtu.be/abcdefghijk",
        ],
    )
    def test_accepts_exact_hosts(self, url):
        assert is_safe_youtube_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://youtube.com.evil.com/watch?v=abcdefghijk",
            "https://evilyoutube.com/watch?v=abcdefghijk",
            "https://youtube.com@evil.com/watch?v=abcdefghijk",
            "https://notyoutube.com/",
            "file:///etc/passwd",
            "youtube.com/watch?v=abcdefghijk",
            "",
            None,
        ],
    )
    def test_rejects_lookalikes_and_other_schemes(self, url):
        assert is_safe_youtube_url(url) is False
