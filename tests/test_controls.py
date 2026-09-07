"""Tests for ascii_player.controls - keyboard controls."""

import time
from unittest.mock import patch
from ascii_player.controls import PlaybackControls


class TestPlaybackControls:
    def test_init_defaults(self):
        pc = PlaybackControls()
        assert pc.paused is False
        assert pc.speed == 1.0
        assert pc.seek_amount == 0
        assert pc.quit is False

    def test_pause_toggle(self):
        pc = PlaybackControls()
        assert not pc.is_paused()
        pc._process_key(b" ")
        assert pc.is_paused()
        pc._process_key(b" ")
        assert not pc.is_paused()

    def test_quit(self):
        pc = PlaybackControls()
        assert not pc.should_quit()
        pc._process_key(b"q")
        assert pc.should_quit()

    def test_speed_increase(self):
        pc = PlaybackControls()
        assert pc.get_speed() == 1.0
        pc._process_key(b"+")
        assert pc.get_speed() == 1.25
        pc._process_key(b"=")
        assert pc.get_speed() == 1.50

    def test_speed_decrease(self):
        pc = PlaybackControls()
        pc._process_key(b"-")
        assert pc.get_speed() == 0.75

    def test_speed_max_cap(self):
        pc = PlaybackControls()
        for _ in range(20):
            pc._process_key(b"+")
        assert pc.get_speed() == 3.0

    def test_speed_min_cap(self):
        pc = PlaybackControls()
        for _ in range(20):
            pc._process_key(b"-")
        assert pc.get_speed() == 0.25

    def test_seek_right(self):
        pc = PlaybackControls()
        assert pc.get_seek() == 0
        with patch("ascii_player.controls.sys.stdin") as mock_stdin:
            mock_stdin.readable.return_value = True
            mock_stdin.read.return_value = "[C"
            pc._process_key(b"\x1b")
        assert pc.get_seek() == 5

    def test_seek_left(self):
        pc = PlaybackControls()
        with patch("ascii_player.controls.sys.stdin") as mock_stdin:
            mock_stdin.readable.return_value = True
            mock_stdin.read.return_value = "[D"
            pc._process_key(b"\x1b")
        assert pc.get_seek() == -5

    def test_get_seek_resets(self):
        pc = PlaybackControls()
        with patch("ascii_player.controls.sys.stdin") as mock_stdin:
            mock_stdin.readable.return_value = True
            mock_stdin.read.return_value = "[C"
            pc._process_key(b"\x1b")
        assert pc.get_seek() == 5
        assert pc.get_seek() == 0

    def test_stop_sets_quit(self):
        pc = PlaybackControls()
        pc.start()
        time.sleep(0.05)
        pc.stop()
        assert pc.should_quit()

    def test_render_controls_returns_strings(self):
        pc = PlaybackControls()
        bar, status = pc.render_controls(80)
        assert isinstance(bar, str)
        assert isinstance(status, str)
        assert "PLAYING" in status

    def test_render_controls_paused(self):
        pc = PlaybackControls()
        pc._process_key(b" ")
        _, status = pc.render_controls(80)
        assert "PAUSED" in status

    def test_render_controls_speed(self):
        pc = PlaybackControls()
        pc._process_key(b"+")
        _, status = pc.render_controls(80)
        assert "1.25x" in status

    def test_unknown_key_ignored(self):
        pc = PlaybackControls()
        old_speed = pc.get_speed()
        pc._process_key(b"x")
        assert pc.get_speed() == old_speed
        assert not pc.is_paused()

    def test_volume_down(self):
        pc = PlaybackControls()
        assert pc.get_volume() == 100
        pc._process_key(b"[")
        assert pc.get_volume() == 90

    def test_volume_up(self):
        pc = PlaybackControls()
        pc._process_key(b"]")
        assert pc.get_volume() == 110

    def test_volume_floor(self):
        pc = PlaybackControls()
        for _ in range(20):
            pc._process_key(b"[")
        assert pc.get_volume() == 0

    def test_volume_cap(self):
        pc = PlaybackControls()
        for _ in range(20):
            pc._process_key(b"]")
        assert pc.get_volume() == 200

    def test_volume_render_in_status(self):
        pc = PlaybackControls()
        pc._process_key(b"]")
        _, status = pc.render_controls(80)
        assert "110%" in status

    def test_ab_points(self):
        pc = PlaybackControls()
        pc.set_current_time(10.0)
        pc._process_key(b"a")
        pc.set_current_time(20.0)
        pc._process_key(b"b")
        assert pc.ab_bounds() == (10.0, 20.0)

    def test_ab_loop_toggle(self):
        pc = PlaybackControls()
        assert not pc.is_ab_loop_enabled()
        pc._process_key(b"l")
        assert pc.is_ab_loop_enabled()
        pc._process_key(b"l")
        assert not pc.is_ab_loop_enabled()

    def test_ab_unsorted_bounds(self):
        pc = PlaybackControls()
        pc.set_current_time(20.0)
        pc._process_key(b"a")
        pc.set_current_time(10.0)
        pc._process_key(b"b")
        assert pc.ab_bounds() == (10.0, 20.0)

    def test_ab_same_point_none(self):
        pc = PlaybackControls()
        pc.set_current_time(5.0)
        pc._process_key(b"a")
        pc.set_current_time(5.0)
        pc._process_key(b"b")
        assert pc.ab_bounds() == (None, None)

    def test_screenshot_request(self):
        pc = PlaybackControls()
        assert not pc.pop_screenshot_request()
        pc._process_key(b"s")
        assert pc.pop_screenshot_request()
        assert not pc.pop_screenshot_request()

    def test_concurrent_access(self):
        pc = PlaybackControls()
        import threading

        def toggle_pause():
            for _ in range(100):
                pc._process_key(b" ")

        threads = [threading.Thread(target=toggle_pause) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        assert pc.paused in (True, False)
