"""YouTube video download functionality."""

import os
import re
import shutil
import subprocess
import tempfile

from loguru import logger

from .config import YOUTUBE_MAX_HEIGHT, YOUTUBE_REGEX, YOUTUBE_TIMEOUT


def is_youtube_url(url):
    """Check if a URL is a YouTube link.

    Args:
        url: String to check

    Returns:
        True if URL matches YouTube pattern
    """
    return re.match(YOUTUBE_REGEX, url) is not None


def download_youtube_video(url):
    """Download a YouTube video using yt-dlp.

    Args:
        url: YouTube video URL

    Returns:
        Path to downloaded video file

    Raises:
        SystemExit: If download fails
    """
    logger.info("Downloading from YouTube: {url}", url=url)

    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "yt_video.mp4")

    try:
        cmd = [
            "yt-dlp",
            "-f", f"best[height<={YOUTUBE_MAX_HEIGHT}]",
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--no-playlist",
            url
        ]

        logger.debug("Running: {cmd}", cmd=" ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=YOUTUBE_TIMEOUT)

        if result.returncode != 0:
            logger.error("yt-dlp failed: {err}", err=result.stderr)
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise SystemExit(1)

        if not os.path.exists(output_path):
            for f in os.listdir(temp_dir):
                if f.endswith(('.mp4', '.webm', '.mkv')):
                    output_path = os.path.join(temp_dir, f)
                    break

        logger.success("Downloaded: {path}", path=output_path)
        return output_path

    except FileNotFoundError:
        logger.error("yt-dlp not found. Install it: pip install yt-dlp")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise SystemExit(1)
    except subprocess.TimeoutExpired:
        logger.error("Download timed out after {t}s", t=YOUTUBE_TIMEOUT)
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise SystemExit(1)


def cleanup_temp_file(file_path):
    """Remove temporary downloaded file and its directory.

    Args:
        file_path: Path to the temp file
    """
    if file_path and os.path.exists(file_path):
        temp_dir = os.path.dirname(file_path)
        try:
            os.remove(file_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info("Cleaned up temp files")
        except OSError:
            pass
