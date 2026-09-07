"""Configuration file management."""

import os

from loguru import logger

from .config import CONFIG_FILE, DEFAULT_CONFIG, DEFAULT_WIDTH

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
            with open(path, "r") as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config.update(file_config)
            logger.debug("Loaded config from {path}", path=path)
        except Exception as e:
            logger.warning("Failed to load config: {err}", err=str(e))

    return config


def save_config(config, config_path=None):
    """Save configuration to YAML file.

    Args:
        config: dict with configuration values
        config_path: Path to config file (default: ascii_player.yaml)
    """
    if not YAML_AVAILABLE:
        logger.warning("PyYAML not installed - cannot save config")
        return

    path = config_path or CONFIG_FILE

    try:
        with open(path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.debug("Saved config to {path}", path=path)
    except Exception as e:
        logger.warning("Failed to save config: {err}", err=str(e))


def merge_args_with_config(args, config):
    """Merge CLI arguments with config file values.

    CLI args take precedence over config file values.

    Args:
        args: argparse.Namespace with CLI arguments
        config: dict with config file values

    Returns:
        dict with merged configuration
    """
    merged = config.copy()

    if args.width != DEFAULT_WIDTH:
        merged["width"] = args.width
    if args.fps is not None:
        merged["fps"] = args.fps
    if args.color:
        merged["color"] = args.color
    if hasattr(args, "audio") and args.no_audio:
        merged["audio"] = False
    if hasattr(args, "preset") and args.preset:
        merged["preset"] = args.preset
    if hasattr(args, "visualizer") and args.visualizer != "none":
        merged["visualizer"] = args.visualizer

    return merged
