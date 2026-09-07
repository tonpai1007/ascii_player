"""Frame caching for smooth replay."""

import hashlib
import json
import os

from loguru import logger

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False


class FrameCache:
    """Cache decoded ASCII frames for instant replay."""

    def __init__(self, cache_dir=".cache"):
        """Initialize frame cache.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = cache_dir
        self.frames = {}
        self.cache_file = None

    def _get_cache_key(self, video_path, width, color, preset):
        """Generate unique cache key for video settings.

        Includes file mtime + size so re-encoded videos invalidate stale frames.
        """
        try:
            st = os.stat(video_path)
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "missing"
        key_data = f"{os.path.abspath(video_path)}:{stamp}:{width}:{color}:{preset}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_cache_path(self, key):
        """Get cache file path."""
        os.makedirs(self.cache_dir, exist_ok=True)
        return os.path.join(self.cache_dir, f"{key}.cache")

    def load(self, video_path, width, color, preset):
        """Load cached frames if available."""
        key = self._get_cache_key(video_path, width, color, preset)
        cache_path = self._get_cache_path(key)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "rb") as f:
                if MSGPACK_AVAILABLE:
                    data = msgpack.unpack(f, raw=False)
                else:
                    data = json.loads(f.read().decode("utf-8"))
            self.frames = {i: frame for i, frame in enumerate(data)}
            logger.info("Loaded {n} cached frames", n=len(self.frames))
            return self.frames
        except Exception as e:
            logger.warning("Cache load failed: {err}", err=str(e))
            return None

    def save(self):
        """Save cached frames to disk."""
        if not self.frames:
            return
        if not self.cache_file:
            return

        try:
            data = [self.frames[i] for i in sorted(self.frames.keys())]
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8") if not MSGPACK_AVAILABLE else msgpack.packb(data, use_bin_type=True)

            tmp = self.cache_file + ".tmp"
            with open(tmp, "wb") as f:
                f.write(payload)
            os.replace(tmp, self.cache_file)
            logger.info("Saved {n} frames to cache", n=len(data))
        except Exception as e:
            logger.warning("Cache save failed: {err}", err=str(e))

    def set_cache_path(self, video_path, width, color, preset):
        """Set cache file path for saving."""
        key = self._get_cache_key(video_path, width, color, preset)
        self.cache_file = self._get_cache_path(key)

    def add_frame(self, frame_num, ascii_frame):
        """Add a frame to cache."""
        self.frames[frame_num] = ascii_frame

    def get_frame(self, frame_num):
        """Get a cached frame."""
        return self.frames.get(frame_num)

    def has_frame(self, frame_num):
        """Check if frame is cached."""
        return frame_num in self.frames

    def clear(self):
        """Clear all cached frames."""
        self.frames.clear()
        logger.debug("Cache cleared")
