# ascii-player

Play video as ASCII art, right in your terminal — local files, YouTube URLs, even your webcam — with synced audio, lyrics, and GIF/MP4 export.

```text
  ▐█████████████▌   just a video, but it's   ▐█████████████▌
  ▐██░▒▓████▓▒░██▌   your terminal now        ▐██░▒▓████▓▒░██▌
```

## Install

Currently installed from source (not on PyPI yet):

```bash
git clone https://github.com/tonpai1007/ascii-player.git
cd ascii-player
pip install -e .
```

Requirements: Python 3.8+, plus OpenCV, NumPy, Pillow, yt-dlp, Loguru, PyYAML, and Textual (pulled in automatically).

## Quick start

```bash
ascii-player video.mp4                 # play a local file
ascii-player video.mp4 -c -p blocks    # color + block-character preset
ascii-player https://youtu.be/VIDEO_ID # play a YouTube video
ascii-player -t                        # launch the TUI file browser
```

## Features

- 8 ASCII presets (classic, blocks, dots, binary, simple, detailed, unicode, braille) with ANSI truecolor
- YouTube playback via yt-dlp, audio synced to video
- Lyrics sync — LRC, SRT, and ASS/SSA
- TUI with keyboard file browser, URL bar, settings, and inline preview
- Webcam mode, GIF/MP4 export, frame caching, A-B loop, screenshots

## Usage

### Basic Playback

```bash
# Play local video
ascii-player video.mp4

# Play with color
ascii-player video.mp4 -c

# Wider output
ascii-player video.mp4 -w 160

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

### Webcam Mode

```bash
# Live ASCII webcam
ascii-player --webcam

# Use specific camera
ascii-player --webcam --camera 1
```

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

Create an `ascii_player.yaml` file in the current directory:

```yaml
width: 120
color: true
preset: blocks
audio: true
```

The TUI saves its settings (width, preset, color, audio, fps, export, output, lyrics, cache) back to this file on play.

## ASCII Presets

| Preset | Characters | Description |
|--------|------------|-------------|
| classic | ` .:-=+*#%@` | Standard ASCII ramp |
| blocks | ` ░▒▓█` | Unicode block elements |
| dots | ` ·•●` | Dot characters |
| binary | ` 01` | Binary digits |
| simple | ` .oO` | Simple ramp |
| detailed | ` .'`^",:;Il!i><~+_-?][}{1)(|\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$` | Full ASCII |
| unicode | ` ◐◑◒◓●` | Unicode circles |
| braille | ` ⠁⠃⠇⠏` | Braille patterns |

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

## License

MIT License