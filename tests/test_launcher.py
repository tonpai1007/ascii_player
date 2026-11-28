"""Tests for the cross-platform terminal launcher."""

import os
import subprocess
import sys

import pytest

from ascii_player import launcher

REAL_POPEN = subprocess.Popen


class FakePopen:
    instances = []

    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        FakePopen.instances.append(self)


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.subprocess, "Popen", FakePopen)
    FakePopen.instances = []
    yield
    FakePopen.instances = []


def test_windows_launcher_writes_unbroken_batch(windows, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = [
        "C:\\Program Files\\Python\\python.exe",
        "-m",
        "ascii_player",
        "https://www.youtube.com/watch?v=VIDEO_ID&t=10",
        "-w",
        "80",
    ]

    assert launcher.launch_new_terminal(args) is True

    popen = FakePopen.instances[0]
    assert popen.args[0] == os.environ.get("COMSPEC", "cmd.exe")
    assert popen.args[1] == "/k"
    assert popen.kwargs["creationflags"] == subprocess.CREATE_NEW_CONSOLE
    assert "shell" not in popen.kwargs

    batch = popen.args[2]
    try:
        with open(batch, encoding="utf-8") as f:
            content = f.read()
    finally:
        os.remove(batch)

    assert f"cd /d \"{tmp_path}\"" in content
    expected = '"-m" "ascii_player" "https://www.youtube.com/watch?v=VIDEO_ID&t=10" "-w" "80"'
    assert expected in content
    assert '(goto) 2>nul & del "%~f0"' in content


def test_windows_launcher_doubles_percent(windows, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = ["python.exe", "-m", "ascii_player", "C:\\my%music%\\song.mp4", "-w", "80"]

    assert launcher.launch_new_terminal(args) is True

    batch = FakePopen.instances[0].args[2]
    try:
        with open(batch, encoding="utf-8") as f:
            content = f.read()
    finally:
        os.remove(batch)
    assert '"C:\\my%%music%%\\song.mp4"' in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows cmd batch file")
def test_windows_batch_runs_command_and_self_deletes(windows, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "argv.txt"
    stub = tmp_path / "echo_args.py"
    stub.write_text(
        f"import sys\nopen({str(log)!r}, 'w').write(repr(sys.argv[1:]))\n", encoding="utf-8"
    )
    args = [sys.executable, str(stub), "https://www.youtube.com/watch?v=VIDEO_ID&t=10", "-w", "80"]

    assert launcher.launch_new_terminal(args) is True
    batch = FakePopen.instances[0].args[2]
    assert os.path.exists(batch)

    monkeypatch.setattr(launcher.subprocess, "Popen", REAL_POPEN)
    subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c", batch], check=False, timeout=30)

    expected = repr(["https://www.youtube.com/watch?v=VIDEO_ID&t=10", "-w", "80"])
    assert log.read_text(encoding="utf-8") == expected
    assert not os.path.exists(batch)
