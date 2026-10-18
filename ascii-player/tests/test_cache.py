"""Tests for ascii_player.cache - JSON frame caching."""

import os
import json
from ascii_player.cache import FrameCache


class TestFrameCache:
    def test_init_creates_empty_cache(self):
        cache = FrameCache()
        assert cache.frames == {}
        assert cache.cache_file is None

    def test_custom_cache_dir(self, tmp_dir):
        cache_dir = os.path.join(tmp_dir, "my_cache")
        cache = FrameCache(cache_dir=cache_dir)
        assert cache.cache_dir == cache_dir

    def test_add_and_get_frame(self):
        cache = FrameCache()
        cache.add_frame(0, ["row1", "row2"])
        assert cache.has_frame(0)
        assert cache.get_frame(0) == ["row1", "row2"]

    def test_has_frame_false(self):
        cache = FrameCache()
        assert not cache.has_frame(99)

    def test_get_frame_missing_returns_none(self):
        cache = FrameCache()
        assert cache.get_frame(99) is None

    def test_clear(self):
        cache = FrameCache()
        cache.add_frame(0, ["data"])
        cache.clear()
        assert cache.frames == {}

    def test_is_complete_requires_every_frame(self):
        cache = FrameCache()
        cache.add_frame(0, ["a"])
        cache.add_frame(1, ["b"])
        assert cache.is_complete(2) is True
        assert cache.is_complete(3) is False

    def test_is_complete_false_without_frames(self):
        assert FrameCache().is_complete(0) is False
        assert FrameCache().is_complete(1) is False

    def test_set_cache_path_generates_key(self, tmp_dir):
        cache = FrameCache(cache_dir=tmp_dir)
        cache.set_cache_path("/video.mp4", 80, False, "classic")
        assert cache.cache_file is not None
        assert cache.cache_file.endswith(".cache")
        assert os.path.exists(tmp_dir)

    def test_save_and_load_roundtrip(self, tmp_dir):
        cache_dir = os.path.join(tmp_dir, "cache")
        cache = FrameCache(cache_dir=cache_dir)
        cache.set_cache_path("/test.mp4", 40, False, "simple")
        cache.add_frame(0, ["line_a", "line_b"])
        cache.add_frame(1, ["line_c", "line_d"])
        cache.save()

        assert os.path.exists(cache.cache_file)

        cache2 = FrameCache(cache_dir=cache_dir)
        loaded = cache2.load("/test.mp4", 40, False, "simple")
        assert loaded is not None
        assert loaded[0] == ["line_a", "line_b"]
        assert loaded[1] == ["line_c", "line_d"]

    def test_load_nonexistent_returns_none(self, tmp_dir):
        cache = FrameCache(cache_dir=tmp_dir)
        result = cache.load("/no_such_file.mp4", 80, False, "classic")
        assert result is None

    def test_load_corrupted_file_returns_none(self, tmp_dir):
        cache_dir = os.path.join(tmp_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache = FrameCache(cache_dir=cache_dir)
        cache.set_cache_path("/test.mp4", 80, False, "classic")
        with open(cache.cache_file, "w") as f:
            f.write("NOT VALID JSON {{{")

        cache2 = FrameCache(cache_dir=cache_dir)
        result = cache2.load("/test.mp4", 80, False, "classic")
        assert result is None

    def test_save_empty_cache_does_nothing(self, tmp_dir):
        cache = FrameCache(cache_dir=tmp_dir)
        cache.cache_file = os.path.join(tmp_dir, "test.json")
        cache.save()
        assert not os.path.exists(cache.cache_file)

    def test_load_json_format(self, tmp_dir):
        cache_dir = os.path.join(tmp_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache = FrameCache(cache_dir=cache_dir)
        cache.set_cache_path("/vid.mp4", 60, True, "blocks")

        raw_data = ["frame0", "frame1", "frame2"]
        with open(cache.cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f)

        loaded = cache.load("/vid.mp4", 60, True, "blocks")
        assert loaded is not None
        assert len(loaded) == 3
        assert loaded[0] == "frame0"

    def test_different_settings_different_keys(self, tmp_dir):
        cache_dir = os.path.join(tmp_dir, "cache")
        cache = FrameCache(cache_dir=cache_dir)
        cache.set_cache_path("/test.mp4", 80, False, "classic")
        path1 = cache.cache_file
        cache.set_cache_path("/test.mp4", 80, True, "classic")
        path2 = cache.cache_file
        assert path1 != path2
