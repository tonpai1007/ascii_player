"""Tests for ascii_player.tui.canvas_engine (interactive drawing model)."""

import numpy as np

from ascii_player.images import AsciiGrid
from ascii_player.tui.canvas_engine import (
    ASCII_STENCILS,
    AsciiCanvasModel,
    box_cells,
    bresenham_line,
    ellipse_points,
    mirror_char,
    stencil_to_grid,
    symmetry_points,
)


def test_symmetry_points_deduped_and_bounded():
    pts_off = symmetry_points(2, 1, 10, 6, "off")
    assert pts_off == [(2, 1)]
    pts_xy = symmetry_points(2, 1, 10, 6, "xy")
    assert set(pts_xy) == {(2, 1), (7, 1), (2, 4), (7, 4)}
    pts_center = symmetry_points(2, 2, 5, 5, "xy")
    assert pts_center == [(2, 2)]


def test_bresenham_line_and_stroke_gap_free():
    pts = bresenham_line(0, 0, 5, 2)
    assert pts[0] == (0, 0) and pts[-1] == (5, 2)
    model = AsciiCanvasModel(width=16, height=10)
    model.draw_stroke(1, 1, 10, 5, "#", (255, 100, 0))
    assert model.glyphs[1, 1] == "#"
    assert model.glyphs[5, 10] == "#"
    assert int(model.drawn.sum()) >= 10


def test_brush_sizes_and_erase():
    model = AsciiCanvasModel(width=16, height=10)
    model.push_undo()
    model.stamp_brush(8, 5, "█", (0, 200, 255), size=2, symmetry="x")
    assert model.drawn[5, 8]
    assert model.drawn[5, 7]
    count_before_erase = int(model.drawn.sum())
    model.erase_brush(8, 5, size=2, symmetry="x")
    assert int(model.drawn.sum()) < count_before_erase


def test_box_and_ellipse_tools():
    cells = box_cells(1, 1, 5, 4, style="round")
    dict_cells = {(x, y): ch for x, y, ch in cells}
    assert dict_cells[(1, 1)] == "╭"
    assert dict_cells[(5, 4)] == "╯"

    model = AsciiCanvasModel(width=20, height=12)
    model.draw_box(2, 2, 8, 6, (255, 255, 255), style="double")
    assert model.glyphs[2, 2] == "╔"
    assert model.glyphs[6, 8] == "╝"

    pts_out = ellipse_points(2, 2, 10, 8, filled=False)
    pts_fill = ellipse_points(2, 2, 10, 8, filled=True)
    assert len(pts_fill) > len(pts_out)
    model.draw_ellipse(2, 2, 14, 10, "*", (100, 255, 100))
    assert "*" in model.glyphs


def test_flood_fill_text_picker_undo_redo_and_grid_roundtrip():
    model = AsciiCanvasModel(width=20, height=10)
    model.draw_box(1, 1, 6, 5, (200, 200, 200), style="single")
    model.push_undo()
    model.flood_fill(3, 3, ".", (50, 150, 255))
    assert model.glyphs[3, 3] == "."
    assert not model.drawn[0, 0]

    assert model.undo() is True
    assert model.glyphs[3, 3] == " "
    assert model.redo() is True
    assert model.glyphs[3, 3] == "."

    end_x = model.draw_text(8, 2, "HI!", (255, 0, 128))
    assert end_x == 11
    ch, rgb = model.pick_cell(8, 2)
    assert ch == "H" and rgb == (255, 0, 128)

    exported = model.to_ascii_grid()
    assert isinstance(exported, AsciiGrid)
    assert exported.width == 20 and exported.height == 10

    model2 = AsciiCanvasModel(width=16, height=8)
    model2.load_ascii_grid(exported)
    assert np.array_equal(model2.glyphs, exported.glyphs)

    model2.flip_horizontal()
    model2.flip_vertical()
    model2.resize(24, 12)
    assert model2.width == 24 and model2.height == 12
    model2.clear()
    assert not model2.drawn.any()


def test_mirror_char_and_pure_typing_model():
    assert mirror_char("(") == ")"
    assert mirror_char("/") == "\\"
    assert mirror_char("[") == "]"
    assert mirror_char("{") == "}"
    assert mirror_char("<") == ">"
    assert mirror_char("╭") == "╮"
    assert mirror_char("X") == "X"

    model = AsciiCanvasModel(width=20, height=8)
    model.type_char(2, 1, "(", (238, 238, 242), mirror=True)
    assert model.glyphs[1, 2] == "("
    assert model.glyphs[1, 17] == ")"
    assert len(model.stroke_log) == 2

    model.erase_at(2, 1, mirror=True)
    assert model.glyphs[1, 2] == " "
    assert model.glyphs[1, 17] == " "

    model.clear()
    assert model.stroke_log == []


def test_builtin_stencils_and_centering():
    for name in ("skull", "cat", "sword", "rose"):
        assert name in ASCII_STENCILS
        grid = stencil_to_grid(name, 60, 20)
        assert grid.shape == (20, 60)
        assert np.any(grid != " ")

