# ASCII Video Player

A feature-rich terminal application that converts videos into ASCII art playback. Supports local files, YouTube URLs, live webcam, lyrics sync, and multiple export formats.

## Features

- **8 ASCII presets**: classic, blocks, dots, binary, simple, detailed, unicode, braille
- **ANSI truecolor** support for colored ASCII output
- **YouTube integration** via yt-dlp
- **Audio playback** synchronized with video
- **Lyrics sync** with LRC, SRT, and ASS/SSA formats
- **TUI interface** with file browser, URL bar, and settings
- **Webcam mode** for live ASCII capture
- **Export** to GIF or MP4
- **Frame caching** for faster replay
- **Keyboard controls**: pause, seek, speed adjustment, quit

## Installation

```bash
pip install ascii-player
```

Or from source:

```bash
git clone https://github.com/tonpai1007/ascii_player.git
cd ascii_player/ascii-player
pip install -e ".[dev]"
```

### Dependencies

- Python 3.9+
- OpenCV (`opencv-python`)
- NumPy
- Pillow
- yt-dlp
- Loguru
- PyYAML
- Textual (for TUI)

Audio playback and MP4 export additionally require `ffmpeg`/`ffplay` on `PATH`.

## Usage

### Basic Playback

```bash
# Play local video
ascii-player video.mp4

# Play with color
ascii-player video.mp4 -c

# Wider output
ascii-player video.mp4 -w 160

# Disable color even if the config file enables it
ascii-player video.mp4 --no-color

# Use block characters preset
ascii-player video.mp4 -p blocks
```

### YouTube Videos

```bash
# Play YouTube video
ascii-player https://www.youtube.com/watch?v=VIDEO_ID

# YouTube with color and custom width
ascii-player https://youtu.be/VIDEO_ID -c -w 120
```

### TUI Interface

```bash
# Launch terminal user interface
ascii-player -t
```

The TUI provides:
- **Keyboard-navigable file browser** — arrow keys to move, Enter to open/select, Backspace to go up, Home/End to jump, PageUp/PageDown to page
- **Quick path bar** — type a folder or file path directly to jump there (press `G` to focus)
- **URL bar** for pasting YouTube links or local file paths
- **Recent files** list for one-click re-open of previously played items
- **Extended settings** — width, preset, color, audio, FPS, export format (GIF/MP4) + output filename, lyrics mode, and frame caching
- **Inline ASCII preview** — selecting a local video renders a representative frame through the same ASCII pipeline (respects preset/width/color) right in the TUI before you launch (requires OpenCV)
- **Auto-lyrics detection** — picks up a same-name `.lrc`/`.srt`/`.ass` next to a selected video
- **Live command preview** — shows the exact command that will run before you play
- **Settings persistence** — panel defaults are loaded from and saved back to `ascii_player.yaml` (shared with the CLI)
- Status bar with key-binding hints
- New terminal launch for playback (playback runs in a separate terminal; embedded in-TUI playback is intentionally not built)

TUI keyboard shortcuts:

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate file list |
| Enter | Open folder / select file |
| Backspace | Go up one directory |
| Home / End | Jump to top / bottom |
| P | Play selected file |
| W | Launch webcam |
| G | Focus path bar |
| R | Refresh file list |
| Q | Quit |

### Lyrics Sync

```bash
# Play with LRC lyrics
ascii-player video.mp4 -l lyrics.lrc

# Fullscreen lyrics mode
ascii-player video.mp4 -l lyrics.srt --lyrics-mode fullscreen
```

Supported formats:
- **LRC**: Standard lyrics format (`[MM:SS.xx] Line`)
- **SRT**: Subtitle format with timestamps
- **ASS/SSA**: Advanced SubStation Alpha

If `lyrics: auto` is set in `ascii_player.yaml` (the default) and no `-l`
argument is given, the player looks for a sibling `.lrc`/`.srt`/`.ass`/`.ssa`
file with the same basename as the video.

### Webcam Mode

```bash
# Live ASCII webcam
ascii-player --webcam

# Use specific camera
ascii-player --webcam --camera 1

# Apply a live filter
ascii-player --webcam --filter edge
```

Filters: `none`, `edge`, `invert`, `colorcycle`, `mirror`.

### Export

```bash
# Export to GIF
ascii-player video.mp4 --export gif

# Export to MP4
ascii-player video.mp4 --export mp4

# Custom output filename
ascii-player video.mp4 --export gif -o my_ascii.gif
```

### Frame Caching

```bash
# Cache frames for faster replay
ascii-player video.mp4 --cache
```

Cached frames are stored in `.cache/` directory.

### Keyboard Controls

| Key | Action |
|-----|--------|
| Space | Pause/Resume |
| Q | Quit |
| + / - | Increase / decrease speed |
| → / ← | Seek forward / backward 5s |
| [ / ] | Decrease / increase volume |
| A | Set A-B loop start point |
| B | Set A-B loop end point |
| L | Toggle A-B loop |
| S | Save ASCII screenshot |

## Configuration

Copy `ascii_player.example.yaml` to `ascii_player.yaml` in the directory you
run the player from:

```yaml
width: 120
color: true
preset: blocks
audio: true
fps: null          # null = use the video's frame rate
lyrics: auto       # auto-detect sibling lyrics/subtitle files
cache: false
export: none       # none, gif, mp4
```

Command-line flags always take precedence over the config file, including
explicitly passing a value equal to the built-in default (for example
`-w 80`). The TUI saves its settings back to this file on play.

Logs are written to `~/.ascii_player/ascii_player.log` (override with the
`ASCII_PLAYER_LOG` environment variable). Console output is limited to
warnings and errors so log lines do not corrupt the ASCII frame.

## ASCII Presets

| Preset | Characters | Description |
|--------|------------|-------------|
| classic | ` .:-=+*#%@` | Standard ASCII ramp |
| blocks | ` ░▒▓█` | Unicode block elements |
| dots | ` ·•●` | Dot characters |
| binary | ` 01` | Binary digits |
| simple | ` .oO0` | Simple ramp |
| detailed | ` .'`^",:;Il!i><~+_-?][}{1)(|\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$` | Full ASCII |
| unicode | ` ▁▂▃▄▅▆▇█` | Unicode block heights |
| braille | full 8-dot braille range | Braille patterns |

## Examples

```bash
# Play with all features
ascii-player video.mp4 -c -p blocks -w 120 -l lyrics.lrc --no-audio

# Quick ASCII preview
ascii-player video.mp4 -p simple -w 80

# Export lyrics-synced GIF
ascii-player video.mp4 -l lyrics.lrc --export gif -o lyrics_video.gif

# YouTube with custom settings
ascii-player https://youtu.be/abc123 -c -p unicode -w 160
```

## Development

```bash
cd ascii-player
pip install -e ".[dev]"
pytest -q
ruff check --select E9,F63,F7,F82 .
```

The test suite uses mocks for `ffmpeg`/`ffplay` and a tiny generated video
fixture, so it runs without a webcam, audio device, or terminal.

## License

MIT License. See [LICENSE](../LICENSE).