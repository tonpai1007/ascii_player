"""Audio playback functionality using ffmpeg."""

import os
import shutil
import signal
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


def _atempo_filter(speed):
    """Build an ffmpeg ``atempo`` filter chain for a speed multiplier.

    ``atempo`` only accepts 0.5-2.0 per instance, so extreme speeds are split
    across multiple chained filters.

    Returns:
        Filter string, or None when no tempo change is needed
    """
    if speed is None or abs(speed - 1.0) < 1e-3:
        return None

    filters = []
    remaining = max(0.25, min(3.0, float(speed)))
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def play_audio(audio_path, volume=100, start_time=0.0, speed=1.0):
    """Play audio file using ffplay (non-blocking).

    Args:
        audio_path: Path to WAV file
        volume: Volume percentage (0-200)
        start_time: Position in seconds to start playback from
        speed: Playback speed multiplier (1.0 = normal)

    Returns:
        subprocess.Popen process or None
    """
    if not audio_path or not os.path.exists(audio_path):
        return None

    try:
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            "-volume", str(int(volume)),
        ]
        if start_time > 0:
            cmd.extend(["-ss", f"{start_time:.3f}"])
        tempo = _atempo_filter(speed)
        if tempo:
            cmd.extend(["-af", tempo])
        cmd.append(audio_path)

        logger.debug(
            "Playing audio: {path} at {vol}% from {pos:.1f}s ({speed}x)",
            path=audio_path, vol=volume, pos=start_time, speed=speed,
        )
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return process

    except FileNotFoundError:
        logger.warning("ffplay not found - audio playback disabled")
        return None
    except Exception as e:
        logger.warning("Audio playback error: {err}", err=str(e))
        return None


def restart_audio(audio_process, audio_path, volume=100, start_time=0.0,
                  paused=False, speed=1.0):
    """Restart audio at a new position/volume, cleaning up the old process.

    Args:
        audio_process: Existing subprocess.Popen or None
        audio_path: Path to WAV file
        volume: New volume percentage (0-200)
        start_time: Position in seconds to resume from
        paused: Immediately pause the new process
        speed: Playback speed multiplier

    Returns:
        New subprocess.Popen process or None
    """
    stop_audio(audio_process)
    process = play_audio(audio_path, volume, start_time=start_time, speed=speed)
    if process and paused:
        pause_audio(process)
    return process


def pause_audio(process):
    """Pause an audio process without losing its position.

    Returns:
        True if the process was paused
    """
    return _signal_audio(process, "SIGSTOP", "suspend")


def resume_audio(process):
    """Resume a previously paused audio process.

    Returns:
        True if the process was resumed
    """
    return _signal_audio(process, "SIGCONT", "resume")


def _signal_audio(process, posix_signal, windows_method):
    """Send a pause/resume control to an ffplay process if supported."""
    if not process or process.poll() is not None:
        return False

    try:
        if os.name == "nt":
            getattr(process, windows_method)()
        else:
            sig = getattr(signal, posix_signal, None)
            if sig is None:
                return False
            process.send_signal(sig)
        return True
    except Exception as e:
        logger.debug("Could not control audio process: {err}", err=str(e))
        return False


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
