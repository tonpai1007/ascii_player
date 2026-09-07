"""Tests for ascii_player.settings - configuration management."""

import os
from ascii_player.settings import load_config, save_config, merge_args_with_config
from ascii_player.config import DEFAULT_CONFIG, DEFAULT_WIDTH


class TestLoadConfig:
    def test_default_config(self, tmp_dir):
        config = load_config(str(tmp_dir / "nonexistent.yaml"))
        assert config == DEFAULT_CONFIG

    def test_load_yaml_config(self, tmp_dir):
        path = tmp_dir / "test.yaml"
        path.write_text("width: 120\ncolor: true\n", encoding="utf-8")
        config = load_config(str(path))
        assert config["width"] == 120
        assert config["color"] is True

    def test_load_invalid_yaml(self, tmp_dir):
        path = tmp_dir / "bad.yaml"
        path.write_text("{{{{invalid yaml", encoding="utf-8")
        config = load_config(str(path))
        assert config == DEFAULT_CONFIG


class TestSaveConfig:
    def test_save_creates_file(self, tmp_dir):
        path = tmp_dir / "out.yaml"
        save_config({"width": 100}, str(path))
        assert path.exists()

    def test_save_and_load_roundtrip(self, tmp_dir):
        path = tmp_dir / "roundtrip.yaml"
        save_config({"width": 120, "preset": "blocks"}, str(path))
        loaded = load_config(str(path))
        assert loaded["width"] == 120
        assert loaded["preset"] == "blocks"

    def test_save_without_yaml(self, tmp_dir, monkeypatch):
        import ascii_player.settings as mod
        monkeypatch.setattr(mod, "YAML_AVAILABLE", False)
        path = tmp_dir / "no_yaml.yaml"
        save_config({"width": 100}, str(path))
        assert not path.exists()


class TestMergeArgs:
    def _make_args(self, **kwargs):
        defaults = {
            "width": DEFAULT_WIDTH,
            "fps": None,
            "color": False,
            "no_audio": False,
            "preset": None,
        }
        defaults.update(kwargs)

        class Args:
            pass

        args = Args()
        for k, v in defaults.items():
            setattr(args, k, v)
        return args

    def test_cli_width_overrides_default(self):
        args = self._make_args(width=120)
        merged = merge_args_with_config(args, DEFAULT_CONFIG.copy())
        assert merged["width"] == 120

    def test_default_width_not_overridden(self):
        args = self._make_args(width=DEFAULT_WIDTH)
        config = DEFAULT_CONFIG.copy()
        config["width"] = 999
        merged = merge_args_with_config(args, config)
        assert merged["width"] == 999

    def test_fps_overrides_when_set(self):
        args = self._make_args(fps=60.0)
        merged = merge_args_with_config(args, DEFAULT_CONFIG.copy())
        assert merged["fps"] == 60.0

    def test_fps_not_overridden_when_none(self):
        args = self._make_args(fps=None)
        config = DEFAULT_CONFIG.copy()
        config["fps"] = 24
        merged = merge_args_with_config(args, config)
        assert merged["fps"] == 24

    def test_color_flag(self):
        args = self._make_args(color=True)
        merged = merge_args_with_config(args, DEFAULT_CONFIG.copy())
        assert merged["color"] is True

    def test_preset_overrides(self):
        args = self._make_args(preset="blocks")
        merged = merge_args_with_config(args, DEFAULT_CONFIG.copy())
        assert merged["preset"] == "blocks"
