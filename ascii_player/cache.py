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

    def __init__(self, cache_dir=".cache", max_frames=3600):
        """Initialize frame cache.

        Args:
            cache_dir: Directory to store cache files
            max_frames: Maximum number of frames kept in memory. Once the cap
                is reached the earlier contiguous prefix is kept for replay and
                no further frames are accepted.
        """
        self.cache_dir = cache_dir
        self.max_frames = max(0, int(max_frames))
        self._cap_warned = False
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
                raw = f.read()

            data = None
            if MSGPACK_AVAILABLE:
                try:
                    data = msgpack.unpackb(raw, raw=False)
                except Exception:
                    data = None

            if data is None:
                data = json.loads(raw.decode("utf-8"))

            if isinstance(data, dict):
                # v2 format: {"version": 2, "frames": [[index, frame], ...]}
                pairs = data.get("frames")
                if data.get("version") != 2 or not isinstance(pairs, list):
                    raise ValueError("Unsupported cached frame payload")
                frames = {}
                for pair in pairs:
                    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                        raise ValueError("Invalid cached frame entry")
                    index, ascii_frame = pair
                    frames[int(index)] = ascii_frame
            elif isinstance(data, list):
                # Legacy format: a dense list starting at frame index 0.
                frames = {i: frame for i, frame in enumerate(data)}
            else:
                raise ValueError("Cached frame payload has an unknown type")

            # An old/oversized cache must not defeat the in-memory cap.
            over_cap = len(frames) > self.max_frames
            if over_cap:
                logger.warning(
                    "Cache holds {n} frames but the limit is {cap}; keeping the first {cap}",
                    n=len(frames),
                    cap=self.max_frames,
                )
                frames = {index: frames[index] for index in sorted(frames)[:self.max_frames]}

            self.frames = frames
            self._cap_warned = over_cap
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
            # Store (index, frame) pairs so sparse caches reload correctly.
            # A list of pairs works with both JSON and msgpack.
            data = {
                "version": 2,
                "frames": [[index, self.frames[index]] for index in sorted(self.frames)],
            }
            if MSGPACK_AVAILABLE:
                payload = msgpack.packb(data, use_bin_type=True)
            else:
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")

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
        """Add a frame to cache, respecting the in-memory frame cap."""
        if frame_num not in self.frames and len(self.frames) >= self.max_frames:
            if not self._cap_warned:
                logger.warning(
                    "Frame cache limit reached ({n} frames); further frames will not be cached",
                    n=self.max_frames,
                )
                self._cap_warned = True
            return
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
        self._cap_warned = False
        logger.debug("Cache cleared")
