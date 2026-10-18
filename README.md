# ASCII Video Player

A terminal application that converts videos into ASCII art, with local file
and YouTube playback, synchronized audio/lyrics, a Textual TUI, live webcam
mode, and GIF/MP4 export.

[![CI](https://github.com/tonpai1007/ascii_player/actions/workflows/ci.yml/badge.svg)](https://github.com/tonpai1007/ascii_player/actions/workflows/ci.yml)

## Quick start

```bash
git clone https://github.com/tonpai1007/ascii_player.git
cd ascii_player/ascii-player
pip install -e ".[dev]"

ascii-player video.mp4 -c -w 100
ascii-player -t                 # launch the TUI
ascii-player --webcam           # live ASCII webcam
```

Full documentation, presets, controls, and configuration options live in
[ascii-player/README.md](ascii-player/README.md).

## Project layout

```
ascii-player/
  ascii_player/     # package (CLI, player, TUI, renderers, audio, lyrics)
  tests/            # pytest suite (unit + mocked integration)
  pyproject.toml
ci/                 # GitHub Actions CI template (see ci/README.md)
LICENSE
```

## Development

```bash
cd ascii-player
pip install -e ".[dev]"
pytest -q
ruff check --select E9,F63,F7,F82 .
```

## License

MIT. See [LICENSE](LICENSE).
