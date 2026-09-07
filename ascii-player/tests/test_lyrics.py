"""Tests for ascii_player.lyrics - LRC/SRT/ASS parsers."""

from ascii_player.lyrics import (
    Lyrics, LyricsLine, parse_lrc, parse_srt, parse_ass, load_lyrics
)


class TestLyricsLine:
    def test_init(self):
        line = LyricsLine(5.5, "Hello")
        assert line.timestamp == 5.5
        assert line.text == "Hello"

    def test_repr(self):
        line = LyricsLine(10.0, "Test")
        assert "10.00" in repr(line)
        assert "Test" in repr(line)


class TestLyrics:
    def test_empty_lyrics(self):
        lyrics = Lyrics()
        assert lyrics.lines == []
        assert lyrics.metadata == {}

    def test_add_line_sorted(self):
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(10.0, "Second"))
        lyrics.add_line(LyricsLine(5.0, "First"))
        assert lyrics.lines[0].timestamp == 5.0
        assert lyrics.lines[1].timestamp == 10.0

    def test_get_line_at(self):
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(0.0, "Intro"))
        lyrics.add_line(LyricsLine(5.0, "Verse"))
        lyrics.add_line(LyricsLine(10.0, "Chorus"))

        cur, nxt, prog = lyrics.get_line_at(7.5)
        assert cur.text == "Verse"
        assert nxt.text == "Chorus"
        assert 0 < prog < 1

    def test_get_line_at_before_first(self):
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(5.0, "First"))
        cur, nxt, prog = lyrics.get_line_at(0.0)
        assert cur is None
        assert nxt.text == "First"

    def test_get_line_at_after_last(self):
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(5.0, "Last"))
        cur, nxt, prog = lyrics.get_line_at(100.0)
        assert cur.text == "Last"
        assert nxt is None

    def test_get_context_lines(self):
        lyrics = Lyrics()
        for i in range(10):
            lyrics.add_line(LyricsLine(float(i), f"Line {i}"))

        ctx = lyrics.get_context_lines(5.0, before=1, after=1)
        assert len(ctx) == 3
        assert ctx[0][0].text == "Line 4"
        assert ctx[1][0].text == "Line 5"
        assert ctx[1][1] is True
        assert ctx[2][0].text == "Line 6"

    def test_duration(self):
        lyrics = Lyrics()
        lyrics.add_line(LyricsLine(5.0, "A"))
        lyrics.add_line(LyricsLine(20.0, "B"))
        assert lyrics.duration == 20.0

    def test_duration_empty(self):
        lyrics = Lyrics()
        assert lyrics.duration == 0


class TestParseLRC:
    def test_basic_lrc(self, lrc_file):
        lyrics = parse_lrc(lrc_file)
        assert len(lyrics.lines) == 4
        assert lyrics.lines[0].text == "Intro"
        assert lyrics.lines[0].timestamp == 0.0
        assert lyrics.lines[1].text == "First line"
        assert lyrics.lines[1].timestamp == 5.0

    def test_lrc_metadata(self, lrc_file):
        lyrics = parse_lrc(lrc_file)
        assert lyrics.metadata.get("ti") == "Test Song"
        assert lyrics.metadata.get("ar") == "Test Artist"

    def test_lrc_nonexistent(self, tmp_dir):
        lyrics = parse_lrc(str(tmp_dir / "nope.lrc"))
        assert lyrics.lines == []

    def test_lrc_empty_file(self, tmp_dir):
        path = tmp_dir / "empty.lrc"
        path.write_text("", encoding="utf-8")
        lyrics = parse_lrc(str(path))
        assert lyrics.lines == []


class TestParseSRT:
    def test_basic_srt(self, srt_file):
        lyrics = parse_srt(srt_file)
        assert len(lyrics.lines) == 3
        assert lyrics.lines[0].text == "First subtitle"
        assert lyrics.lines[0].timestamp == 1.0
        assert lyrics.lines[1].text == "Second subtitle"

    def test_srt_nonexistent(self, tmp_dir):
        lyrics = parse_srt(str(tmp_dir / "nope.srt"))
        assert lyrics.lines == []


class TestParseASS:
    def test_basic_ass(self, ass_file):
        lyrics = parse_ass(ass_file)
        assert len(lyrics.lines) == 3
        assert lyrics.lines[0].text == "First line"
        assert lyrics.lines[0].timestamp == 1.0
        assert lyrics.lines[2].text == "Third line"

    def test_ass_nonexistent(self, tmp_dir):
        lyrics = parse_ass(str(tmp_dir / "nope.ass"))
        assert lyrics.lines == []


class TestLoadLyrics:
    def test_auto_detect_lrc(self, lrc_file):
        lyrics = load_lyrics(lrc_file)
        assert len(lyrics.lines) == 4

    def test_auto_detect_srt(self, srt_file):
        lyrics = load_lyrics(srt_file)
        assert len(lyrics.lines) == 3

    def test_auto_detect_ass(self, ass_file):
        lyrics = load_lyrics(ass_file)
        assert len(lyrics.lines) == 3

    def test_unknown_extension(self, tmp_dir):
        path = tmp_dir / "unknown.txt"
        path.write_text("hello", encoding="utf-8")
        lyrics = load_lyrics(str(path))
        assert lyrics.lines == []

    def test_nonexistent_file(self):
        lyrics = load_lyrics("/nonexistent/file.lrc")
        assert lyrics.lines == []


class TestEncodingFallback:
    def test_latin1_file(self, tmp_dir):
        path = tmp_dir / "latin1.lrc"
        lines = ["[00:01.00]Caf\xe9", "[00:05.00]R\xe9sum\xe9"]
        path.write_bytes(("\n".join(lines) + "\n").encode("latin-1"))
        lyrics = parse_lrc(str(path))
        assert len(lyrics.lines) == 2
        assert lyrics.lines[0].text == "Caf\xe9"
        assert lyrics.lines[1].text == "R\xe9sum\xe9"

    def test_utf8_bom_file(self, tmp_dir):
        path = tmp_dir / "bom.lrc"
        content = "[00:02.00]With BOM"
        path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        lyrics = parse_lrc(str(path))
        assert len(lyrics.lines) == 1
        assert lyrics.lines[0].text == "With BOM"
