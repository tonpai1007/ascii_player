"""Tests for ascii_player.image_player."""

import pickle
import tempfile

from PIL import Image

from ascii_player.image_player import export_image, export_still, play_image


def _make_png(tmp_path, size=(8, 4), color=(100, 50, 200)):
    p = tmp_path / "img.png"
    Image.new("RGB", size, color).save(p)
    return str(p)


def test_export_still_txt(tmp_path):
    src = _make_png(tmp_path)
    out = tmp_path / "out.txt"
    path = export_still(src, str(out), width=6, preset="classic")
    assert path == str(out)
    assert out.read_text(encoding="utf-8").strip() != ""


def test_export_still_html(tmp_path):
    src = _make_png(tmp_path)
    out = tmp_path / "out.html"
    export_still(src, str(out), width=6, dither=True, invert=True)
    text = out.read_text(encoding="utf-8")
    assert "<pre class=\"ascii\">" in text
    assert "<span" in text


def test_export_still_ans_respects_color(tmp_path):
    src = _make_png(tmp_path)
    colored = tmp_path / "color.ans"
    plain = tmp_path / "plain.ans"
    export_still(src, str(colored), width=6, color=True)
    export_still(src, str(plain), width=6, color=False)
    assert "\x1b[38;2;" in colored.read_text(encoding="utf-8")
    assert "\x1b[38;2;" not in plain.read_text(encoding="utf-8")


def test_export_image_color_reaches_grid_lines(tmp_path, monkeypatch):
    from ascii_player import exporter as exporter_module

    src = _make_png(tmp_path)
    captured = []

    class CaptureExporter:
        def __init__(self, width, fps):
            pass

        def add_frame(self, lines, index):
            captured.append(list(lines))

        def export_gif(self, path):
            pass

        def export_mp4(self, path):
            pass

    monkeypatch.setattr(exporter_module, "ASCIIExporter", CaptureExporter)
    out = str(tmp_path / "out.gif")
    export_image(src, out, width=6, color=True, export_format="gif")
    assert captured and any("\x1b[38;2;" in line for line in captured[0])

    captured.clear()
    export_image(src, out, width=6, color=False, export_format="gif")
    assert captured and not any("\x1b[" in line for line in captured[0])


def test_play_image_cache_key_includes_crop_and_aspect(tmp_path, monkeypatch, capsys):
    gradient = Image.new("RGB", (16, 8))
    gradient.putdata([(x * 16, y * 32, 128) for y in range(8) for x in range(16)])
    src = tmp_path / "gradient.png"
    gradient.save(src)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cache_dir = tmp_path / ".cache" / "ascii_player"

    for crop, aspect in ((False, 0.55), (True, 0.55), (False, 0.9)):
        play_image(
            str(src),
            width=6,
            crop=crop,
            aspect=aspect,
            cache=True,
            animation="none",
            controls=False,
            hold=0.0,
        )
        capsys.readouterr()

    files = sorted(cache_dir.glob("*.pkl"))
    assert len(files) == 3
    payloads = [pickle.loads(path.read_bytes()) for path in files]
    glyphs = {
        grid.glyphs.tobytes()
        for payload in payloads
        for grid, _duration in payload
    }
    assert len(glyphs) == 3


def test_play_image_static_no_controls(capsys):
    with tempfile.TemporaryDirectory() as d:
        src = _make_png(__import__("pathlib").Path(d))
        play_image(src, width=6, animation="none", controls=False, hold=0.0)
        captured = capsys.readouterr().out
        assert len(captured) > 0


def test_play_image_decode_animation(capsys):
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        src = _make_png(Path(d))
        play_image(src, width=6, animation="decode", controls=False, duration=0.01, hold=0.0)
        captured = capsys.readouterr().out
        assert len(captured) > 0


def test_play_image_gif(tmp_path, capsys):
    frames = [Image.new("RGB", (6, 4), (i * 60, 0, 0)) for i in range(2)]
    src = tmp_path / "anim.gif"
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=30, loop=0)
    play_image(str(src), width=6, animation="decode", controls=False, loop=False, hold=0.0)
    captured = capsys.readouterr().out
    assert len(captured) > 0


def test_play_image_type_rain(capsys, tmp_path):
    src = _make_png(tmp_path)
    for anim in ("type", "rain"):
        play_image(src, width=6, animation=anim, controls=False, duration=0.01, hold=0.0)
        capsys.readouterr()
