"""Tests for ascii_player.image_player."""

import tempfile

from PIL import Image

from ascii_player.image_player import export_still, play_image


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
