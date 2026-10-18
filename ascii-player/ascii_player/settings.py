"""Configuration file management."""

import os
import tempfile

from loguru import logger

from .config import ASCII_PRESETS, CONFIG_FILE, DEFAULT_CONFIG, DEFAULT_PRESET, DEFAULT_WIDTH

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file (default: ascii_player.yaml)

    Returns:
        dict with configuration values
    """
    config = DEFAULT_CONFIG.copy()
    path = config_path or CONFIG_FILE

    if not YAML_AVAILABLE:
        logger.debug("PyYAML not installed - using default config")
        return config

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f)
                if isinstance(file_config, dict):
                    config.update(file_config)
                elif file_config is not None:
                    logger.warning("Ignoring config: expected a mapping")
            logger.debug("Loaded config from {path}", path=path)
        except Exception as e:
            logger.warning("Failed to load config: {err}", err=str(e))

    return config


def save_config(config, config_path=None):
    """Save configuration to YAML file atomically.

    Args:
        config: dict with configuration values
        config_path: Path to config file (default: ascii_player.yaml)
    """
    if not YAML_AVAILABLE:
        logger.warning("PyYAML not installed - cannot save config")
        return

    path = config_path or CONFIG_FILE
    directory = os.path.dirname(os.path.abspath(path))
    tmp_path = None

    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=".ascii_player_", suffix=".yaml.tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, path)
        logger.debug("Saved config to {path}", path=path)
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        logger.warning("Failed to save config: {err}", err=str(e))


def merge_args_with_config(args, config):
    """Merge CLI arguments with config file values.

    CLI arguments take precedence over config file values. Arguments that were
    not supplied on the command line default to ``None`` so that an explicit
    value (even one equal to the built-in default) still wins over the config
    file.

    Args:
        args: argparse.Namespace with CLI arguments
        config: dict with config file values

    Returns:
        dict with merged configuration
    """
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)

    for key in ("width", "fps", "color", "preset", "visualizer", "lyrics_mode"):
        value = getattr(args, key, None)
        if value is not None:
            merged[key] = value

    if getattr(args, "no_audio", False):
        merged["audio"] = False

    # Normalize values coming from hand-edited YAML so a bad config cannot
    # crash playback (e.g. width: "wide" or fps: 0).
    try:
        merged["width"] = max(1, int(merged.get("width", DEFAULT_WIDTH)))
    except (TypeError, ValueError):
        merged["width"] = DEFAULT_WIDTH

    fps = merged.get("fps")
    if fps in (None, ""):
        merged["fps"] = None
    else:
        try:
            merged["fps"] = max(0.1, float(fps))
        except (TypeError, ValueError):
            merged["fps"] = None

    if merged.get("preset") not in ASCII_PRESETS:
        merged["preset"] = DEFAULT_PRESET

    return merged
