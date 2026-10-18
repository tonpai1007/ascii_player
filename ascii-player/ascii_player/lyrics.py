"""Lyrics parser for LRC, SRT, and ASS subtitle formats."""

import os
import re

from loguru import logger

LYRICS_EXTENSIONS = (".lrc", ".srt", ".ass", ".ssa")


def find_lyrics_file(video_path):
    """Return a same-name sibling lyrics file for ``video_path``, if any.

    Args:
        video_path: Path to the video file

    Returns:
        Path to a matching .lrc/.srt/.ass/.ssa file, or None
    """
    if not video_path:
        return None
    base, _ = os.path.splitext(video_path)
    for ext in LYRICS_EXTENSIONS:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
        upper = base + ext.upper()
        if os.path.exists(upper):
            return upper
    return None


def _read_file_with_encoding(file_path):
    """Read file with encoding fallback for Windows compatibility.

    Tries utf-8, utf-8-sig (BOM), then latin-1 (never fails).

    Args:
        file_path: Path to file to read

    Returns:
        File content as string
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            content = content.lstrip("\ufeff")
            return content
        except UnicodeDecodeError:
            continue
    return ""


class LyricsLine:
    """A single line of lyrics with timing."""

    def __init__(self, timestamp, text):
        """Initialize lyrics line.

        Args:
            timestamp: Time in seconds
            text: Lyrics text
        """
        self.timestamp = timestamp
        self.text = text

    def __repr__(self):
        return f"LyricsLine({self.timestamp:.2f}s, '{self.text}')"


class Lyrics:
    """Parsed lyrics with timing information."""

    def __init__(self):
        self.lines = []
        self.metadata = {}

    def add_line(self, line):
        """Add a lyrics line."""
        self.lines.append(line)
        self.lines.sort(key=lambda x: x.timestamp)

    def get_line_at(self, current_time):
        """Get the lyrics line at a specific time.

        Args:
            current_time: Current playback time in seconds

        Returns:
            Tuple of (current_line, next_line, progress)
        """
        if not self.lines:
            return None, None, 0

        current_idx = -1
        for i, line in enumerate(self.lines):
            if line.timestamp <= current_time:
                current_idx = i
            else:
                break

        if current_idx == -1:
            return None, self.lines[0], 0

        current = self.lines[current_idx]
        next_line = self.lines[current_idx + 1] if current_idx + 1 < len(self.lines) else None

        if next_line:
            duration = next_line.timestamp - current.timestamp
            elapsed = current_time - current.timestamp
            progress = elapsed / duration if duration > 0 else 0
        else:
            progress = 0

        return current, next_line, progress

    def get_context_lines(self, current_time, before=2, after=2):
        """Get surrounding lyrics lines for display.

        Args:
            current_time: Current playback time
            before: Lines to show before current
            after: Lines to show after current

        Returns:
            List of (line, is_current) tuples
        """
        if not self.lines:
            return []

        current_idx = 0
        for i, line in enumerate(self.lines):
            if line.timestamp <= current_time:
                current_idx = i
            else:
                break

        start = max(0, current_idx - before)
        end = min(len(self.lines), current_idx + after + 1)

        result = []
        for i in range(start, end):
            result.append((self.lines[i], i == current_idx))

        return result

    @property
    def duration(self):
        """Get total lyrics duration."""
        if self.lines:
            return self.lines[-1].timestamp
        return 0


def parse_lrc(file_path):
    """Parse LRC lyrics file.

    Args:
        file_path: Path to .lrc file

    Returns:
        Lyrics object
    """
    lyrics = Lyrics()

    try:
        content = _read_file_with_encoding(file_path)
        if not content:
            return lyrics

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            match = re.match(r'\[(\d+):(\d+\.?\d*)\](.*)', line)
            if match:
                minutes = int(match.group(1))
                seconds = float(match.group(2))
                text = match.group(3).strip()
                timestamp = minutes * 60 + seconds

                if text:
                    lyrics.add_line(LyricsLine(timestamp, text))
            else:
                meta_match = re.match(r'\[(\w+):(.*)\]', line)
                if meta_match:
                    key = meta_match.group(1).lower()
                    value = meta_match.group(2).strip()
                    lyrics.metadata[key] = value

        logger.debug("Parsed LRC: {n} lines", n=len(lyrics.lines))
        return lyrics

    except Exception as e:
        logger.error("Failed to parse LRC: {err}", err=str(e))
        return lyrics


def parse_srt(file_path):
    """Parse SRT subtitle file.

    Args:
        file_path: Path to .srt file

    Returns:
        Lyrics object
    """
    lyrics = Lyrics()

    try:
        content = _read_file_with_encoding(file_path)
        if not content:
            return lyrics

        blocks = content.strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            time_match = re.match(
                r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)',
                lines[1]
            )
            if time_match:
                h, m, s, ms = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3)), int(time_match.group(4))
                timestamp = h * 3600 + m * 60 + s + ms / 1000

                text = " ".join(lines[2:])
                text = re.sub(r'<[^>]+>', '', text)
                text = text.strip()

                if text:
                    lyrics.add_line(LyricsLine(timestamp, text))

        logger.debug("Parsed SRT: {n} lines", n=len(lyrics.lines))
        return lyrics

    except Exception as e:
        logger.error("Failed to parse SRT: {err}", err=str(e))
        return lyrics


def parse_ass(file_path):
    """Parse ASS/SSA subtitle file.

    Args:
        file_path: Path to .ass or .ssa file

    Returns:
        Lyrics object
    """
    lyrics = Lyrics()

    try:
        content = _read_file_with_encoding(file_path)
        if not content:
            return lyrics

        in_events = False
        format_fields = []

        for line in content.split("\n"):
            line = line.strip()

            if line.lower() == "[events]":
                in_events = True
                continue

            if line.startswith("[") and line.endswith("]"):
                in_events = False
                continue

            if not in_events:
                continue

            if line.lower().startswith("format:"):
                format_fields = [f.strip().lower() for f in line[7:].split(",")]
                continue

            if line.lower().startswith("dialogue:"):
                parts = line[9:].split(",", len(format_fields) - 1)
                if len(parts) < len(format_fields):
                    continue

                field_dict = dict(zip(format_fields, parts))

                start_str = field_dict.get("start", "0:00:00.00")
                timestamp = _parse_ass_time(start_str)

                text = field_dict.get("text", "")
                text = re.sub(r'\\N', '\n', text)
                text = re.sub(r'\\n', '\n', text)
                text = re.sub(r'\{[^}]*\}', '', text)
                text = text.replace("\n", " ").strip()

                if text and not text.startswith("Comment"):
                    lyrics.add_line(LyricsLine(timestamp, text))

        logger.debug("Parsed ASS: {n} lines", n=len(lyrics.lines))
        return lyrics

    except Exception as e:
        logger.error("Failed to parse ASS: {err}", err=str(e))
        return lyrics


def _parse_ass_time(time_str):
    """Parse ASS timestamp format (H:MM:SS.CC)."""
    match = re.match(r'(\d+):(\d+):(\d+)\.(\d+)', time_str.strip())
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        cs = int(match.group(4))
        return h * 3600 + m * 60 + s + cs / 100
    return 0


def load_lyrics(file_path):
    """Load lyrics from file (auto-detect format).

    Args:
        file_path: Path to lyrics/subtitle file

    Returns:
        Lyrics object
    """
    if not os.path.exists(file_path):
        logger.error("Lyrics file not found: {path}", path=file_path)
        return Lyrics()

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".lrc":
        return parse_lrc(file_path)
    elif ext == ".srt":
        return parse_srt(file_path)
    elif ext in (".ass", ".ssa"):
        return parse_ass(file_path)
    else:
        logger.warning("Unknown lyrics format: {ext}", ext=ext)
        return Lyrics()
