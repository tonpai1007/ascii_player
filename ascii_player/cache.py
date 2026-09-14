"""Frame caching for smooth replay."""

import collections
import hashlib
import json
import os

from loguru import logger

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

DEFAULT_MAX_FRAMES = 50000


class FrameCache:
    """Cache decoded ASCII frames for instant replay.

    Uses an OrderedDict for O(1) FIFO eviction when max_frames is reached,
    preventing unbounded memory growth on long videos.
    """

    def __init__(self, cache_dir=".cache", max_frames=DEFAULT_MAX_FRAMES):
        """Initialize frame cache.

        Args:
            cache_dir: Directory to store cache files
            max_frames: Maximum frames to keep in memory (oldest evicted first)
        """
        self.cache_dir = cache_dir
        self.max_frames = max_frames
        self.frames: collections.OrderedDict = collections.OrderedDict()
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
            self.frames = collections.OrderedDict(
                (i, frame) for i, frame in enumerate(data)
            )
            self._evict()
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
            payload = (
                json.dumps(data, ensure_ascii=False).encode("utf-8")
                if not MSGPACK_AVAILABLE
                else msgpack.packb(data, use_bin_type=True)
            )

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
        """Add a frame to cache, evicting oldest if over limit."""
        self.frames[frame_num] = ascii_frame
        self._evict()

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

    def _evict(self):
        """Evict oldest frames when over max_frames limit."""
        while len(self.frames) > self.max_frames:
            self.frames.popitem(last=False)
