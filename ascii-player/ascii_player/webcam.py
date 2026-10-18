"""Live webcam ASCII camera."""

import sys
import time

import cv2
from loguru import logger

from .core import frame_to_ascii


class WebcamCapture:
    """Capture and display live webcam feed as ASCII art."""

    _WINDOWS_BACKENDS = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    _MACOS_BACKENDS = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    _LINUX_BACKENDS = [cv2.CAP_V4L2, cv2.CAP_ANY]

    def __init__(self, camera_index=0, filter="none"):
        """Initialize webcam capture.

        Args:
            camera_index: Camera device index (0 = default)
            filter: Filter mode - "none", "edge", "invert", "colorcycle", "mirror"
        """
        self.camera_index = camera_index
        self.cap = None
        self.filter = filter
        self._colorcycle_hue = 0.0

    @classmethod
    def _backends(cls):
        """Return capture backends appropriate for the current platform."""
        if sys.platform == "win32":
            return cls._WINDOWS_BACKENDS
        if sys.platform == "darwin":
            return cls._MACOS_BACKENDS
        return cls._LINUX_BACKENDS

    def apply_filter(self, frame):
        """Apply the selected filter to a frame.

        Args:
            frame: OpenCV BGR frame

        Returns:
            Filtered frame
        """
        if self.filter == "edge":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return cv2.Canny(gray, 100, 200)
        elif self.filter == "invert":
            return cv2.bitwise_not(frame)
        elif self.filter == "mirror":
            return cv2.flip(frame, 1)
        elif self.filter == "colorcycle":
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hsv[:, :, 0] = (hsv[:, :, 0] + int(self._colorcycle_hue)) % 180
            self._colorcycle_hue = (self._colorcycle_hue + 2) % 180
            return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return frame

    def open(self):
        """Open webcam connection, trying multiple backends.

        Returns:
            True if successful
        """
        try:
            for backend in self._backends():
                cap = cv2.VideoCapture(self.camera_index, backend)
                if cap.isOpened():
                    self.cap = cap
                    break
                cap.release()
            else:
                logger.error("Cannot open webcam {idx} with any backend", idx=self.camera_index)
                return False

            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info("Webcam opened: {w}x{h}", w=width, h=height)
            return True

        except Exception as e:
            logger.error("Webcam error: {err}", err=str(e))
            return False

    def close(self):
        """Close webcam connection."""
        if self.cap:
            self.cap.release()
            self.cap = None
            logger.debug("Webcam closed")

    def read_frame(self):
        """Read a single frame from webcam.

        Returns:
            OpenCV frame or None
        """
        if not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        return frame if ret else None


def run_webcam(width=80, color=False, preset="classic", target_fps=30, filter="none",
               camera_index=0):
    """Run live ASCII webcam display.

    Args:
        width: ASCII output width
        color: Enable color output
        preset: ASCII character preset
        target_fps: Target frame rate
        filter: Filter mode - "none", "edge", "invert", "colorcycle", "mirror"
        camera_index: Camera device index (0 = default)
    """
    webcam = WebcamCapture(camera_index=camera_index, filter=filter)

    if not webcam.open():
        raise SystemExit(1)

    frame_interval = 1.0 / target_fps
    frame_count = 0
    start_time = time.time()

    print("\033[2J\033[H", end="", flush=True)
    logger.info(
        "Webcam running | Width: {w} | Preset: {p} | FPS: {f} | Filter: {fi}",
        w=width, p=preset, f=target_fps, fi=filter
    )
    logger.info("Press [Ctrl+C] to stop")

    try:
        consecutive_failures = 0
        while True:
            frame_start = time.time()

            frame = webcam.read_frame()
            if frame is None:
                consecutive_failures += 1
                if consecutive_failures == 1:
                    logger.warning(
                        "Not receiving frames from webcam - check that the camera is not in use"
                    )
                if consecutive_failures >= 30:
                    logger.error(
                        "Webcam is not delivering frames (tried {n} times). Exiting.",
                        n=consecutive_failures
                    )
                    break
                time.sleep(0.05)
                continue

            consecutive_failures = 0

            filtered = webcam.apply_filter(frame)
            ascii_frame = frame_to_ascii(filtered, width, color, preset)

            border = f"\033[1;36m{'═' * width}\033[0m"
            lines = [border]
            lines.extend(ascii_frame)
            lines.append(border)

            frame_count += 1
            elapsed = time.time() - start_time
            current_fps = frame_count / elapsed if elapsed > 0 else 0
            lines.append(
                f"\033[1;33mWebcam | Frame: {frame_count} | "
                f"FPS: {current_fps:.1f} | Filter: {filter}\033[0m"
            )

            sys.stdout.write("\033[H" + "\n".join(lines) + "\n")
            sys.stdout.flush()

            frame_elapsed = time.time() - frame_start
            sleep_time = frame_interval - frame_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Webcam stopped by user")
    finally:
        webcam.close()
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        logger.info(
            "Webcam stats: {f} frames in {e:.1f}s ({fps:.1f} FPS)",
            f=frame_count, e=elapsed, fps=fps
        )
        print(f"\n\033[1;32mStopped. {frame_count} frames captured\033[0m")
