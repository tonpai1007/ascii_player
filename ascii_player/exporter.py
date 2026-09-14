"""Export ASCII frames to GIF or MP4."""

import os
import re
import shutil
import subprocess
import tempfile

from loguru import logger

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ASCIIExporter:
    """Export ASCII art video to GIF or MP4."""

    def __init__(self, width=80, fps=24):
        """Initialize exporter.

        Args:
            width: ASCII output width
            fps: Output frame rate
        """
        if not PIL_AVAILABLE:
            raise ImportError("Pillow is required for export. Install it: pip install Pillow")
        self.width = width
        self.fps = fps
        self.frames = []
        self.temp_dir = tempfile.mkdtemp()
        self.lyrics = None

    def set_lyrics(self, lyrics):
        """Set lyrics for burn-in during export.

        Args:
            lyrics: Lyrics object
        """
        self.lyrics = lyrics

    def add_frame(self, ascii_frame, frame_num, current_time=None, lyrics_context=None):
        """Add an ASCII frame for export.

        Args:
            ascii_frame: List of strings (ASCII rows)
            frame_num: Frame number
            current_time: Current playback time in seconds
            lyrics_context: Optional list of (LyricsLine, is_current) tuples
        """
        frame = list(ascii_frame)

        if lyrics_context:
            lyrics_width = self.width - 4
            for line, is_current in lyrics_context:
                text = line.text[:lyrics_width]
                prefix = ">> " if is_current else "   "
                frame.append(f"\033[90m{prefix}{text}\033[0m")

        img = self._ascii_to_image(frame)
        self.frames.append((frame_num, img))

    def _ascii_to_image(self, ascii_frame):
        """Convert ASCII frame to PIL Image.

        Renders same-brightness character runs in a single draw.text() call
        instead of one call per character, reducing draw overhead by ~10-30x.

        Args:
            ascii_frame: List of strings

        Returns:
            PIL Image
        """
        char_width = 8
        char_height = 14

        cleaned = [_ANSI_RE.sub("", row) for row in ascii_frame]
        width_px = len(cleaned[0]) * char_width if cleaned else 0
        height_px = len(cleaned) * char_height

        img = Image.new("RGB", (width_px, height_px), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except OSError:
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12
                )
            except OSError:
                font = ImageFont.load_default()

        for y, row in enumerate(cleaned):
            runs = []
            prev_color = None
            run_buf = []
            for char in row:
                brightness = ord(char) / 127 if char.strip() else 0
                color_val = int(brightness * 255)
                if color_val == prev_color:
                    run_buf.append(char)
                else:
                    if run_buf:
                        runs.append((prev_color, "".join(run_buf)))
                    run_buf = [char]
                    prev_color = color_val
            if run_buf:
                runs.append((prev_color, "".join(run_buf)))

            x_offset = 0
            for color_val, text in runs:
                draw.text(
                    (x_offset, y * char_height),
                    text,
                    fill=(color_val, color_val, color_val),
                    font=font,
                )
                x_offset += len(text) * char_width

        return img

    def export_gif(self, output_path, loop=0):
        """Export frames as animated GIF.

        Args:
            output_path: Output GIF file path
            loop: Number of loops (0 = infinite)
        """
        if not self.frames:
            logger.warning("No frames to export")
            return

        self.frames.sort(key=lambda x: x[0])
        images = [f[1] for f in self.frames]

        duration = int(1000 / self.fps)

        try:
            images[0].save(
                output_path,
                save_all=True,
                append_images=images[1:],
                duration=duration,
                loop=loop,
                optimize=True
            )

            logger.success("Exported GIF: {path} ({n} frames)", path=output_path, n=len(images))
        finally:
            self._cleanup_frames()

    def export_mp4(self, output_path):
        """Export frames as MP4 using ffmpeg.

        Args:
            output_path: Output MP4 file path
        """
        if not self.frames:
            logger.warning("No frames to export")
            return

        self.frames.sort(key=lambda x: x[0])

        for i, (frame_num, img) in enumerate(self.frames):
            frame_path = os.path.join(self.temp_dir, f"frame_{i:06d}.png")
            img.save(frame_path)

        try:
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(self.fps),
                "-i", os.path.join(self.temp_dir, "frame_%06d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                output_path
            ]

            logger.info("Encoding MP4: {cmd}", cmd=" ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error("MP4 export failed: {err}", err=result.stderr[:200])
                return

            logger.success(
                "Exported MP4: {path} ({n} frames)",
                path=output_path, n=len(self.frames)
            )

        except FileNotFoundError:
            logger.error("ffmpeg not found - cannot export MP4")
        except subprocess.TimeoutExpired:
            logger.error("MP4 export timed out")
        finally:
            self._cleanup_frames()

    def _cleanup_frames(self):
        """Remove temporary frame files."""
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except OSError:
            pass

    def cleanup(self):
        """Clean up all temporary files."""
        self._cleanup_frames()


def save_ascii_screenshot(ascii_frame, frameno, width, color=False):
    """Save the current ASCII frame to a text file and (if possible) a PNG.

    Files are written to the current directory as ascii_shot_N.txt / .png.

    Args:
        ascii_frame: List of strings (ASCII rows)
        frameno: Current frame number (used in filename)
        width: ASCII output width
        color: Whether the frame contains ANSI color codes (ignored for text)

    Returns:
        Path to the PNG file if written, else the text file path, or None
    """
    try:
        import time
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"ascii_shot_{frameno}_{stamp}"

        txt_path = f"{base}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            for line in ascii_frame:
                f.write(line + "\n")
        logger.success("Screenshot saved: {path}", path=txt_path)

        if not PIL_AVAILABLE:
            return txt_path

        png_path = f"{base}.png"
        exporter = ASCIIExporter(width)
        img = exporter._ascii_to_image(ascii_frame)
        img.save(png_path)
        exporter.cleanup()
        logger.success("Screenshot image saved: {path}", path=png_path)
        return png_path

    except Exception as e:
        logger.error("Could not save screenshot: {err}", err=str(e))
        return None


def save_ascii_gallery(frames, output_path, fmt="txt"):
    """Save a collection of ASCII frames as a gallery file.

    Args:
        frames: List of (frame_num, ascii_frame) tuples
        output_path: Output file path
        fmt: Format - "txt" for plain text, "npz" for compressed numpy

    Returns:
        Output path on success, None on failure
    """
    if not frames:
        logger.warning("No frames to save")
        return None

    try:
        if fmt == "npz":
            import numpy as np
            arrays = []
            meta = []
            for frame_num, ascii_frame in frames:
                max_len = max(len(row) for row in ascii_frame) if ascii_frame else 0
                arr = np.zeros((len(ascii_frame), max_len), dtype="<U1")
                for i, row in enumerate(ascii_frame):
                    arr[i, :len(row)] = list(row)
                arrays.append(arr)
                meta.append(frame_num)
            np.savez_compressed(output_path, frames=arrays, meta=meta)
            logger.success("Gallery saved: {path} ({n} frames)", path=output_path, n=len(frames))
            return output_path

        with open(output_path, "w", encoding="utf-8") as f:
            for frame_num, ascii_frame in frames:
                f.write(f"\n{'=' * 60}\n")
                f.write(f" Frame {frame_num}\n")
                f.write(f"{'=' * 60}\n")
                for line in ascii_frame:
                    f.write(line + "\n")
        logger.success("Gallery saved: {path} ({n} frames)", path=output_path, n=len(frames))
        return output_path

    except Exception as e:
        logger.error("Could not save gallery: {err}", err=str(e))
        return None
