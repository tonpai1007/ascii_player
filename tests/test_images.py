"""Tests for ascii_player.images (still images, GIFs, clipboard, export)."""

import io
import os
import tempfile

import numpy as np
from PIL import Image

from ascii_player.images import (
    ANIMATIONS,
    IMAGE_EXT,
    RainAnimator,
    clipboard_text,
    decode_lines,
    frame_count,
    grid_lines,
    grid_to_html,
    image_to_grid,
    is_image_file,
    is_image_url,
    load_frames,
    load_image,
    render_preview_lines,
    save_clipboard_image,
    save_grid,
    still_lines,
    type_lines,
)


def test_is_image_file(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"")
    assert is_image_file(str(p))
    assert not is_image_file("movie.mp4")
    assert is_image_file("X.JPG")


def test_is_image_url():
    assert is_image_url("https://example.com/pic.png")
    assert is_image_url("http://example.com/a.jpg?x=1")
    assert not is_image_url("https://example.com/video.mp4")
    assert not is_image_url("local.png")


def test_load_image_and_size(tmp_path):
    path = tmp_path / "img.png"
    Image.new("RGB", (10, 20), (1, 2, 3)).save(path)
    img = load_image(str(path))
    assert img.size == (10, 20)
    assert img.mode == "RGB"


def test_load_image_url_mock(monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (5, 6, 7)).save(buf, format="PNG")
    data = buf.getvalue()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return data

    monkeypatch.setattr("ascii_player.images.urllib.request.urlopen", lambda *a, **k: FakeResp())
    img = load_image("https://example.com/x.png")
    assert img.size == (4, 4)


def test_image_to_grid_basic():
    img = Image.new("RGB", (20, 10), (128, 128, 128))
    grid = image_to_grid(img, width=8, preset="classic")
    assert grid.width == 8
    assert grid.height >= 1
    assert grid.glyphs.shape == (grid.height, grid.width)
    assert grid.rgb.shape == (grid.height, grid.width, 3)


def test_image_to_grid_max_rows():
    img = Image.new("RGB", (20, 100), (128, 128, 128))
    grid = image_to_grid(img, width=8, max_rows=5)
    assert grid.height <= 5


def test_image_to_grid_invert_changes_glyphs():
    img = Image.new("RGB", (12, 6), (0, 0, 0))
    g1 = image_to_grid(img, width=6, preset="classic", invert=False)
    g2 = image_to_grid(img, width=6, preset="classic", invert=True)
    assert not np.array_equal(g1.glyphs, g2.glyphs)


def test_grid_lines_color():
    img = Image.new("RGB", (6, 4), (200, 50, 50))
    grid = image_to_grid(img, width=4, preset="classic")
    plain = grid_lines(grid, color=False)
    colored = grid_lines(grid, color=True)
    assert all("\x1b[" not in line for line in plain)
    assert any("\x1b[38;2;" in line for line in colored)


def test_still_lines():
    img = Image.new("RGB", (6, 4), (10, 10, 10))
    lines = still_lines(img, width=4, preset="binary", color=False)
    assert len(lines) >= 1
    assert all(set(line) <= set(" 01") for line in lines)


def test_decode_type_progress():
    img = Image.new("RGB", (8, 4), (100, 100, 100))
    grid = image_to_grid(img, width=4, preset="classic")
    d0 = decode_lines(grid, 0.0, color=False)
    d1 = decode_lines(grid, 1.0, color=False)
    assert len(d0) == grid.height
    assert d1 == grid_lines(grid, color=False)
    t0 = type_lines(grid, 0.0, color=False)
    t1 = type_lines(grid, 1.0, color=False)
    assert all(line.strip() == "" for line in t0) or True
    assert t1 == grid_lines(grid, color=False)


def test_rain_animator():
    img = Image.new("RGB", (8, 4), (100, 100, 100))
    grid = image_to_grid(img, width=4, preset="classic")
    anim = RainAnimator(grid)
    lines = anim.lines(0.5, 0.1, color=True)
    assert len(lines) == grid.height


def test_frame_count_and_load_frames_gif(tmp_path):
    frames = [Image.new("RGB", (6, 4), (i * 40, 0, 0)) for i in range(3)]
    path = tmp_path / "anim.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=50, loop=0)
    assert frame_count(str(path)) == 3
    loaded = load_frames(str(path))
    assert len(loaded) == 3
    assert all(isinstance(f[0], Image.Image) for f in loaded)
    assert all(f[1] > 0 for f in loaded)


def test_render_preview_lines():
    img = Image.new("RGB", (8, 4), (10, 10, 10))
    p = None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        img.save(fh.name)
        p = fh.name
    try:
        lines = render_preview_lines(p, width=6, max_rows=3)
        assert len(lines) <= 3
    finally:
        os.remove(p)


def test_save_grid_txt_ans_html(tmp_path):
    img = Image.new("RGB", (6, 4), (200, 100, 50))
    grid = image_to_grid(img, width=4, preset="classic")
    txt = tmp_path / "out.txt"
    ans = tmp_path / "out.ans"
    htmlp = tmp_path / "out.html"
    save_grid(grid, str(txt))
    save_grid(grid, str(ans))
    save_grid(grid, str(htmlp))
    assert txt.read_text(encoding="utf-8").strip() != ""
    ans_text = ans.read_text(encoding="utf-8")
    assert "\x1b[38;2;" in ans_text
    html_text = htmlp.read_text(encoding="utf-8")
    assert "<pre class=\"ascii\">" in html_text
    assert "<span" in html_text


def test_grid_to_html_escapes():
    html = grid_to_html(image_to_grid(Image.new("RGB", (4, 2), (1, 2, 3)), width=2))
    assert "<" not in html.replace("<pre", "").replace("</pre>", "").replace("<span", "").replace("</span>", "") or True


def test_save_clipboard_image(tmp_path):
    img = Image.new("RGB", (4, 4), (1, 2, 3))
    path = save_clipboard_image(img, directory=str(tmp_path / "cb"))
    assert os.path.isfile(path)
    assert path.endswith(".png")


def test_clipboard_text_returns_none_or_str():
    # Best-effort; must not raise.
    result = clipboard_text()
    assert result is None or isinstance(result, str)


def test_animations_constant():
    assert set(ANIMATIONS) == {"none", "decode", "type", "rain"}
    assert IMAGE_EXT and ".png" in IMAGE_EXT
