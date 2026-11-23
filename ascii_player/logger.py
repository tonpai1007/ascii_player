"""Loguru logger setup for ASCII Video Player."""

import sys

from loguru import logger

from .config import LOG_FILE, LOG_FORMAT, LOG_RETENTION, LOG_ROTATION


def setup_logger(console=True):
    """Configure loguru with console and file handlers.

    Args:
        console: Enable the stderr console handler (INFO). Disable in TUI
            mode to keep loguru output from corrupting the terminal screen.
    """
    logger.remove()

    if console:
        logger.add(
            sys.stderr,
            level="INFO",
            format=LOG_FORMAT
        )

    logger.add(
        LOG_FILE,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        level="DEBUG"
    )

    return logger
