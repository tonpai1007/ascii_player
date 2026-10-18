"""Tests for ascii_player.renderer - split/fullscreen layout."""

from ascii_player.renderer import (
    FullscreenRenderer,
    SplitRenderer,
    _fit,
    _visible_len,
)


class _Line:
    def __init__(self, text):
        self.text = text


class TestAnsiHelpers:
    def test_visible_len_ignores_ansi(self):
        assert _visible_len("\033[31mabc\033[0m") == 3

    def test_fit_pads_to_exact_visible_width(self):
        fitted = _fit("\033[31mab\033[0m", 5)
        assert _visible_len(fitted) == 5
        assert fitted.startswith("\033[31m")

    def test_fit_truncates_without_breaking_ansi(self):
        fitted = _fit("\033[31mabcdef\033[0m", 3)
        assert _visible_len(fitted) == 3
        assert "abc" in fitted


class TestSplitRenderer:
    def test_color_rows_stay_aligned(self):
        renderer = SplitRenderer(video_width=4, lyrics_width=6)
        frame = ["\033[31mabcdefgh\033[0m"]
        lyrics = [(_Line("hello"), True)]

        out = renderer.render(frame, lyrics, 0.0)

        assert len(out) == 1
        left, right = out[0].split(" │ ")
        assert _visible_len(left) == 4
        assert _visible_len(right) == 6
        assert out[0].startswith("\033[31m")

    def test_short_rows_are_padded(self):
        renderer = SplitRenderer(video_width=4, lyrics_width=6)
        out = renderer.render(["ab"], [], 0.0)
        left, right = out[0].split(" │ ")
        assert _visible_len(left) == 4
        assert _visible_len(right) == 6


class TestFullscreenRenderer:
    def test_current_line_does_not_embed_newline(self):
        renderer = FullscreenRenderer(width=30)
        out = renderer.render([(_Line("sing along"), True)], 0.0)
        assert all("\n" not in line for line in out)
        assert any("sing along" in line for line in out)

    def test_line_is_truncated_with_ellipsis(self):
        renderer = FullscreenRenderer(width=10)
        out = renderer.render([(_Line("a very long lyric line"), False)], 0.0)
        assert any("..." in line for line in out)
