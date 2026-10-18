"""Loguru logger setup for ASCII Video Player."""

import os
import sys

from loguru import logger

from .config import LOG_FORMAT, LOG_RETENTION, LOG_ROTATION

LOG_DIR = os.path.join(os.path.expanduser("~"), ".ascii_player")
LOG_FILE = os.environ.get("ASCII_PLAYER_LOG", os.path.join(LOG_DIR, "ascii_player.log"))


def setup_logger(console=True):
    """Configure loguru with optional console and file handlers.

    Args:
        console: Enable the stderr console handler. The console handler only
            emits warnings and errors, because INFO lines would corrupt the
            ASCII frame output during playback. Use the log file for details.
    """
    logger.remove()

    if console:
        logger.add(
            sys.stderr,
            level="WARNING",
            format=LOG_FORMAT
        )

    try:
        os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
        logger.add(
            LOG_FILE,
            rotation=LOG_ROTATION,
            retention=LOG_RETENTION,
            level="DEBUG"
        )
    except OSError:
        # Read-only home directory: keep console logging but don't crash.
        pass

    return logger
