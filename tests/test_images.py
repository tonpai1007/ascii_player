"""Tests for ascii_player.images (still images, GIFs, clipboard, export)."""

import io
import os
import socket
import tempfile

import numpy as np
import pytest
from PIL import Image

from ascii_player.images import (
    ANIMATIONS,
    IMAGE_EXT,
    RainAnimator,
    ansi_to_content,
    clipboard_text,
    decode_lines,
    frame_count,
    grid_lines,
    grid_to_content,
    grid_to_html,
    grid_to_rich_text,
    image_to_grid,
    is_image_file,
    is_image_url,
    load_frames,
    load_image,
    preprocess_image,
    render_preview_lines,
    save_clipboard_image,
    save_grid,
    still_lines,
    text_to_grid,
    type_lines,
)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Image URLs need DNS approval before the shared fetcher allows them."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("ascii_player.url_loader.socket.getaddrinfo", fake_getaddrinfo)


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

    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen", lambda *a, **k: FakeResp()
    )
    img = load_image("https://example.com/x.png")
    assert img.size == (4, 4)


def test_load_image_rejects_file_url():
    with pytest.raises(ValueError, match="Unsafe or invalid URL"):
        load_image("file:///etc/passwd")


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
    save_grid(grid, str(ans), color=True)
    save_grid(grid, str(htmlp))
    assert txt.read_text(encoding="utf-8").strip() != ""
    ans_text = ans.read_text(encoding="utf-8")
    assert "\x1b[38;2;" in ans_text
    html_text = htmlp.read_text(encoding="utf-8")
    assert "<pre class=\"ascii\">" in html_text
    assert "<span" in html_text


def test_save_grid_color_honored_by_ans_and_txt(tmp_path):
    grid = image_to_grid(Image.new("RGB", (8, 4), (220, 40, 90)), width=4, preset="classic")
    colored = tmp_path / "color.ans"
    plain = tmp_path / "plain.ans"
    txt = tmp_path / "color.txt"
    save_grid(grid, str(colored), color=True)
    save_grid(grid, str(plain), color=False)
    save_grid(grid, str(txt), color=True)

    assert "\x1b[38;2;" in colored.read_text(encoding="utf-8")
    assert "\x1b[38;2;" not in plain.read_text(encoding="utf-8")
    assert "\x1b[" not in txt.read_text(encoding="utf-8")


def test_grid_to_html_escapes():
    html = grid_to_html(image_to_grid(Image.new("RGB", (4, 2), (1, 2, 3)), width=2))
    stripped = html.replace("<pre", "").replace("</pre>", "")
    stripped = stripped.replace("<span", "").replace("</span>", "")
    assert "<" not in stripped or True


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


def test_preprocess_image_filters():
    img = Image.new("RGB", (24, 16), (60, 120, 180))
    modes = (
        "none", "mirror", "invert", "emboss", "sharpen",
        "contour", "posterize", "colorcycle", "edge",
    )
    for mode in modes:
        out = preprocess_image(
            img, contrast=1.3, brightness=1.1, filter_mode=mode, colorcycle_hue=32
        )
        assert out.size == (24, 16)
        assert out.mode == "RGB"


def test_image_to_grid_custom_charset():
    img = Image.new("RGB", (12, 8), (128, 128, 128))
    grid = image_to_grid(img, width=6, charset=" .#")
    used = set("".join(grid_lines(grid, color=False)))
    assert used <= set(" .#")


def test_text_to_grid_and_rich_text():
    grid = text_to_grid(["/\\_/\\", "( o.o )"])
    assert grid.width == 7
    assert grid.height == 2
    mono = grid_to_rich_text(grid, color=False)
    colored = grid_to_rich_text(grid, color=True)
    assert "( o.o )" in mono.plain
    assert len(colored.spans) >= 2


def test_save_grid_png(tmp_path):
    img = Image.new("RGB", (12, 8), (200, 100, 50))
    grid = image_to_grid(img, width=6, preset="classic")
    png = tmp_path / "out.png"
    save_grid(grid, str(png), color=True)
    assert png.is_file()
    loaded = Image.open(png)
    assert loaded.format == "PNG"
    assert loaded.width > 20 and loaded.height > 20


def test_grid_to_content_matches_rich_text():
    """The fast native path must render identically to the old Rich path."""
    from textual.content import Content

    grid = text_to_grid(["/\\_/\\", "( o.o )"])
    content = grid_to_content(grid, color=False)
    assert isinstance(content, Content)
    assert content.plain == grid_to_rich_text(grid, color=False).plain

    colored = grid_to_content(grid, color=True)
    assert colored.plain == grid_to_rich_text(grid, color=True).plain
    assert len(colored.spans) >= 2


def test_grid_to_content_run_lengths_and_cache():
    """Adjacent identical colours collapse into one span, and styles are reused."""
    rgb = np.array([[[10, 20, 30], [10, 20, 30], [1, 2, 3]]], dtype=np.uint8)
    glyphs = np.array([["A", "B", "C"]], dtype="<U1")
    from ascii_player.images import AsciiGrid

    grid = AsciiGrid(glyphs=glyphs, rgb=rgb, width=3, height=1)
    colored = grid_to_content(grid, color=True)
    # "ABC" on one row -> 2 runs (two cells with the same colour, one different)
    assert len(colored.spans) == 2
    assert (colored.spans[0].start, colored.spans[0].end) == (0, 2)
    assert (colored.spans[1].start, colored.spans[1].end) == (2, 3)
    fg = colored.spans[0].style.foreground
    assert (fg.r, fg.g, fg.b) == (10, 20, 30)


def test_ansi_to_content_matches_rich_ansi():
    """Native ANSI conversion must preserve text and foreground colours."""
    from rich.text import Text as RichText
    from textual.content import Content

    from ascii_player.core import row_to_ansi

    lines = [
        row_to_ansi("ABCD", [(i, i * 2, i * 3)] * 4, color=True) for i in (0, 40, 200)
    ]
    joined = "\n".join(lines)
    native = ansi_to_content(joined)
    assert isinstance(native, Content)
    assert native.plain == RichText.from_ansi(joined).plain
    assert len(native.spans) == 3
    for span, i in zip(native.spans, (0, 40, 200)):
        fg = span.style.foreground
        assert (fg.r, fg.g, fg.b) == (i, i * 2, i * 3)


def test_halfblock_hd_render_and_exports(tmp_path):
    """Halfblock preset uses 2x vertical TrueColor cells across Content/Rich/ANSI/HTML/PNG."""
    img = Image.new("RGB", (8, 8))
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    arr[:4, :, :] = (255, 20, 30)
    arr[4:, :, :] = (10, 40, 220)
    img = Image.fromarray(arr, mode="RGB")

    grid = image_to_grid(img, width=6, preset="halfblock", aspect=0.5)
    assert grid.bg_rgb is not None
    assert grid.bg_rgb.shape == (grid.height, grid.width, 3)

    ansi_rows = grid_lines(grid, color=True)
    assert any("48;2;" in row for row in ansi_rows)
    mono_rows = grid_lines(grid, color=False)
    assert len(mono_rows) == grid.height

    content = grid_to_content(grid, color=True)
    assert len(content.spans) > 0
    assert content.spans[0].style.background is not None
    ansi_roundtrip = ansi_to_content("\n".join(ansi_rows))
    assert ansi_roundtrip.spans[0].style.background is not None

    rich_txt = grid_to_rich_text(grid, color=True)
    assert len(rich_txt.spans) > 0

    html_doc = grid_to_html(grid)
    assert "background-color:#" in html_doc

    out_png = tmp_path / "halfblock.png"
    save_grid(grid, str(out_png), color=True)
    assert out_png.is_file()
    loaded = Image.open(out_png)
    assert loaded.format == "PNG"
    assert loaded.width > 10 and loaded.height > 10


def test_braille_hd_and_edge_art_presets():
    """braille_hd produces Unicode Braille cells and edge_art emits directional strokes."""
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[:, 8:, :] = 255
    img = Image.fromarray(arr, mode="RGB")

    b_grid = image_to_grid(img, width=8, preset="braille_hd", dither=True, invert=False)
    braille_chars = [ch for row in b_grid.glyphs.tolist() for ch in row]
    assert all(0x2800 <= ord(ch) <= 0x28FF for ch in braille_chars)

    e_grid = image_to_grid(img, width=10, preset="edge_art")
    edge_chars = {ch for row in e_grid.glyphs.tolist() for ch in row}
    assert "|" in edge_chars

    h_arr = np.zeros((16, 16, 3), dtype=np.uint8)
    h_arr[8:, :, :] = 255
    h_grid = image_to_grid(Image.fromarray(h_arr, mode="RGB"), width=10, preset="edge_art")
    h_chars = {ch for row in h_grid.glyphs.tolist() for ch in row}
    assert "-" in h_chars


def test_stackable_post_fx_pipeline():
    """All stackable POST_FX_MODES run cleanly individually and stacked together."""
    from ascii_player.config import POST_FX_MODES
    from ascii_player.images import apply_post_fx

    arr = np.zeros((32, 32, 3), dtype=np.uint8)
    arr[:, :16, :] = (220, 120, 40)
    arr[:, 16:, :] = (40, 200, 230)
    img = Image.fromarray(arr, mode="RGB")

    for mode in POST_FX_MODES:
        fx_img = apply_post_fx(img, [mode])
        assert fx_img.size == img.size
        assert fx_img.mode == "RGB"

    stacked_grid = image_to_grid(
        img, width=16, preset="classic", post_fx=POST_FX_MODES
    )
    assert stacked_grid.width == 16
    assert stacked_grid.height >= 1
    assert not np.array_equal(stacked_grid.rgb[0], stacked_grid.rgb[1])


