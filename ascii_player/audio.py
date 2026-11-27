"""Audio playback functionality using ffmpeg."""

import os
import shutil
import subprocess
import tempfile

from loguru import logger


def extract_audio(video_path):
    """Extract audio from video file to temporary WAV file.

    Args:
        video_path: Path to video file

    Returns:
        Path to extracted WAV file, or None if extraction fails
    """
    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, "audio.wav")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            audio_path
        ]

        logger.debug("Extracting audio: {cmd}", cmd=" ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.warning("Audio extraction failed: {err}", err=result.stderr[:200])
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        if os.path.exists(audio_path):
            logger.debug("Audio extracted to {path}", path=audio_path)
            return audio_path

        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    except FileNotFoundError:
        logger.warning("ffmpeg not found - audio playback disabled")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Audio extraction timed out")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None
    except Exception as e:
        logger.warning("Audio extraction error: {err}", err=str(e))
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def play_audio(audio_path, volume=100, start_time=0.0):
    """Play audio file using ffplay (non-blocking).

    Args:
        audio_path: Path to WAV file
        volume: Volume percentage (0-200)
        start_time: Seek offset in seconds before starting playback

    Returns:
        subprocess.Popen process or None
    """
    if not audio_path or not os.path.exists(audio_path):
        return None

    try:
        offset = f"{max(0.0, float(start_time)):.3f}"
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            "-volume", str(int(volume)),
            "-ss", offset,
            audio_path
        ]

        logger.debug(
            "Playing audio: {path} at {vol}% from {offset}s",
            path=audio_path,
            vol=volume,
            offset=offset,
        )
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return process

    except FileNotFoundError:
        logger.warning("ffplay not found - audio playback disabled")
        return None
    except Exception as e:
        logger.warning("Audio playback error: {err}", err=str(e))
        return None


def restart_audio(audio_process, audio_path, volume=100, start_time=0.0):
    """Restart audio with a new volume/offset, cleaning up the old process.

    Callers passing only the original three arguments keep the old behaviour
    (restart from the beginning of the file).

    Args:
        audio_process: Existing subprocess.Popen or None
        audio_path: Path to WAV file
        volume: New volume percentage (0-200)
        start_time: Offset in seconds at which the new process should start

    Returns:
        New subprocess.Popen process or None
    """
    stop_audio(audio_process)
    return play_audio(audio_path, volume, start_time=start_time)


def stop_audio(process):
    """Stop audio playback.

    Args:
        process: subprocess.Popen process to terminate
    """
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def cleanup_audio(audio_path):
    """Remove temporary audio file.

    Args:
        audio_path: Path to audio file
    """
    if audio_path and os.path.exists(audio_path):
        try:
            temp_dir = os.path.dirname(audio_path)
            os.remove(audio_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
        except OSError:
            pass
