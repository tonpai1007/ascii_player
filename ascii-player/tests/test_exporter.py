"""Tests for ascii_player.exporter - GIF/MP4 export."""

import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from ascii_player.exporter import ASCIIExporter, PIL_AVAILABLE, save_ascii_gallery


def requires_pil(func):
    return pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow not installed")(func)


class TestASCIIExporterInit:
    @requires_pil
    def test_init(self):
        exp = ASCIIExporter(width=80, fps=24)
        assert exp.width == 80
        assert exp.fps == 24
        assert exp.frames == []
        assert os.path.isdir(exp.temp_dir)

    @requires_pil
    def test_cleanup_removes_temp_dir(self):
        exp = ASCIIExporter()
        temp_dir = exp.temp_dir
        assert os.path.isdir(temp_dir)
        exp.cleanup()
        assert not os.path.isdir(temp_dir)


class TestAsciiToImage:
    @requires_pil
    def test_creates_image(self):
        exp = ASCIIExporter(width=10, fps=10)
        ascii_frame = ["abcde", "fghij"]
        img = exp._ascii_to_image(ascii_frame)
        assert img.size[0] > 0
        assert img.size[1] > 0

    @requires_pil
    def test_empty_frame(self):
        exp = ASCIIExporter()
        img = exp._ascii_to_image([])
        assert img.size == (0, 0)


class TestAddFrame:
    @requires_pil
    def test_add_frame(self):
        exp = ASCIIExporter(width=10, fps=10)
        exp.add_frame(["abc", "def"], frame_num=0)
        assert len(exp.frames) == 1
        assert exp.frames[0][0] == 0


class TestExportGif:
    @requires_pil
    def test_export_gif(self, tmp_dir):
        exp = ASCIIExporter(width=10, fps=10)
        for i in range(5):
            exp.add_frame(["abcde", "fghij"], frame_num=i)

        output = str(tmp_dir / "out.gif")
        exp.export_gif(output)
        assert os.path.exists(output)
        assert os.path.getsize(output) > 0

    @requires_pil
    def test_export_gif_empty(self, tmp_dir):
        exp = ASCIIExporter()
        output = str(tmp_dir / "empty.gif")
        exp.export_gif(output)
        assert not os.path.exists(output)

    @requires_pil
    def test_gif_cleanup_frames(self, tmp_dir):
        exp = ASCIIExporter(width=10, fps=10)
        for i in range(3):
            exp.add_frame(["abcde"], frame_num=i)
        temp_dir = exp.temp_dir
        exp.export_gif(str(tmp_dir / "out.gif"))
        assert not os.path.isdir(temp_dir)


class TestExportMp4:
    @requires_pil
    def test_export_mp4_creates_temp_frames(self):
        exp = ASCIIExporter(width=10, fps=10)
        exp.add_frame(["abcde", "fghij"], frame_num=0)
        exp.export_mp4(str(tempfile.mkdtemp()) + "/out.mp4")
        exp.cleanup()


class TestCleanupFrames:
    @requires_pil
    def test_cleanup_removes_dir(self):
        exp = ASCIIExporter()
        temp_dir = exp.temp_dir
        exp._cleanup_frames()
        assert not os.path.isdir(temp_dir)

    @requires_pil
    def test_double_cleanup_safe(self):
        exp = ASCIIExporter()
        exp._cleanup_frames()
        exp._cleanup_frames()


class TestSaveAsciiGallery:
    def test_saves_txt_gallery(self, tmp_dir):
        frames = [(0, ["hello", "world"]), (1, ["foo", "bar"])]
        output = str(tmp_dir / "gallery.txt")
        result = save_ascii_gallery(frames, output, fmt="txt")
        assert result == output
        assert os.path.exists(output)
        with open(output, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Frame 0" in content
        assert "Frame 1" in content
        assert "hello" in content

    def test_saves_npz_gallery(self, tmp_dir):
        frames = [(0, ["abc", "def"]), (1, ["ghi", "jkl"])]
        output = str(tmp_dir / "gallery.npz")
        result = save_ascii_gallery(frames, output, fmt="npz")
        assert result == output
        assert os.path.exists(output)

    def test_empty_frames_returns_none(self, tmp_dir):
        result = save_ascii_gallery([], str(tmp_dir / "gallery.txt"))
        assert result is None


class TestLyricsBurnIn:
    @requires_pil
    def test_add_frame_with_lyrics(self, tmp_dir):
        from ascii_player.lyrics import Lyrics, LyricsLine

        exp = ASCIIExporter(width=20, fps=10)
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(0.0, "Hello world"))
        lyrics.add_line(LyricsLine(1.0, "Next line"))
        exp.set_lyrics(lyrics)

        ctx = [(lyrics.lines[0], True), (lyrics.lines[1], False)]
        exp.add_frame(["abcde", "fghij"], frame_num=0, current_time=0.0, lyrics_context=ctx)
        assert len(exp.frames) == 1

    @requires_pil
    def test_add_frame_without_lyrics(self):
        exp = ASCIIExporter(width=10, fps=10)
        exp.add_frame(["abc", "def"], frame_num=0)
        assert len(exp.frames) == 1
