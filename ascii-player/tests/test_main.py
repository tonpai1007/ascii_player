from types import SimpleNamespace

from ascii_player.__main__ import _resolve_export


class TestResolveExport:
    def _args(self, export=None, output=None):
        return SimpleNamespace(export=export, output=output)

    def test_cli_export_wins(self):
        args = self._args(export="gif", output="cli.gif")
        settings = {"export": "mp4", "output": "config.mp4"}
        assert _resolve_export(args, settings) == ("gif", "cli.gif")

    def test_config_export_used_when_cli_absent(self):
        args = self._args()
        settings = {"export": "mp4", "output": "config.mp4"}
        assert _resolve_export(args, settings) == ("mp4", "config.mp4")

    def test_none_export_disables_export(self):
        args = self._args()
        assert _resolve_export(args, {"export": "none", "output": ""}) == (None, None)

    def test_output_only_does_not_enable_export(self):
        args = self._args(output="out.gif")
        assert _resolve_export(args, {"output": ""}) == (None, None)
