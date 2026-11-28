"""Slash command registry, omnibox input parser, and @file matcher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..images import IMAGE_EXT
from .helpers import LYRICS_EXT, VIDEO_EXT, is_url


@dataclass(frozen=True)
class SlashCommand:
    """Definition of one slash command in the omnibox and command palette."""

    name: str
    usage: str
    description: str
    category: str
    aliases: Tuple[str, ...] = ()


SLASH_COMMANDS: List[SlashCommand] = [
    SlashCommand("/prompt", "/prompt <text>", "Generate ASCII art from a description", "create"),
    SlashCommand("/banner", "/banner <text>", "Generate FIGlet ASCII typography", "create"),
    SlashCommand("/url", "/url <link>", "Load image, webpage og:image, or YouTube URL", "create"),
    SlashCommand(
        "/open",
        "/open [path]",
        "Open a file path or toggle Files drawer (Ctrl+O)",
        "create",
        aliases=("/files",),
    ),
    SlashCommand(
        "/webcam",
        "/webcam [filter]",
        "Toggle live ASCII webcam (none|mirror|edge|invert|colorcycle)",
        "create",
        aliases=("/cam",),
    ),
    SlashCommand(
        "/snap",
        "/snap",
        "Freeze live webcam frame onto the canvas",
        "create",
        aliases=("/freeze",),
    ),
    SlashCommand("/paste", "/paste", "Render image or URL from clipboard", "create"),
    SlashCommand(
        "/preset",
        "/preset [name]",
        "Switch or cycle preset (classic, halfblock, braille_hd, edge_art, ...)",
        "style",
    ),
    SlashCommand("/color", "/color [on|off]", "Toggle or set 24-bit TrueColor", "style"),
    SlashCommand("/width", "/width <n|fit>", "Set output width or fit viewport", "style"),
    SlashCommand(
        "/filter", "/filter [mode]", "Apply or cycle FX filter (edge, emboss, ...)", "style"
    ),
    SlashCommand(
        "/fx",
        "/fx <effect|clear>",
        "Toggle stackable post-FX (scanlines, chromatic, vignette, bloom, halftone, glitch)",
        "style",
    ),
    SlashCommand("/dither", "/dither [on|off]", "Toggle ordered Bayer dithering", "style"),
    SlashCommand("/invert", "/invert [on|off]", "Toggle brightness inversion", "style"),
    SlashCommand("/crop", "/crop [on|off]", "Toggle aspect-ratio center crop", "style"),
    SlashCommand("/contrast", "/contrast <val>", "Set contrast multiplier (0.2 - 3.5)", "style"),
    SlashCommand(
        "/brightness", "/brightness <val>", "Set brightness multiplier (0.2 - 3.0)", "style"
    ),
    SlashCommand("/aspect", "/aspect <val>", "Set character aspect ratio (default 0.55)", "style"),
    SlashCommand("/charset", "/charset <chars|reset>", "Set custom ramp or reset", "style"),
    SlashCommand(
        "/animate", "/animate <mode>", "Set reveal animation (none|decode|type|rain)", "style"
    ),
    SlashCommand(
        "/engine",
        "/engine <name>",
        "Set prompt engine (auto|ai|web|ollama|banner|procedural)",
        "create",
    ),
    SlashCommand("/font", "/font <name>", "Set FIGlet banner font", "style"),
    SlashCommand(
        "/draw",
        "/draw [skull|cat|trace|edit]",
        "Open pure-typing terminal ASCII tab (/type skull)",
        "create",
        aliases=("/type", "/paint"),
    ),
    SlashCommand("/studio", "/studio", "Switch back to Studio omnibox tab", "view"),
    SlashCommand("/style", "/style", "Toggle right Style Inspector drawer (Ctrl+B)", "view"),
    SlashCommand("/palette", "/palette", "Open floating Command Palette (Ctrl+K)", "view"),
    SlashCommand("/copy", "/copy", "Copy current ASCII art to clipboard", "output"),
    SlashCommand(
        "/export",
        "/export [path]",
        "Export current art (.png, .html, .ans, .txt, .gif)",
        "output",
        aliases=("/save",),
    ),
    SlashCommand(
        "/popout",
        "/popout",
        "Play current media in external terminal with audio",
        "output",
        aliases=("/play",),
    ),
    SlashCommand("/prev", "/prev", "Previous artwork in session history", "view"),
    SlashCommand("/next", "/next", "Next artwork in session history", "view"),
    SlashCommand(
        "/theme",
        "/theme [name]",
        "Set or cycle theme (amber, sand, dark, retro, ...)",
        "view",
    ),
    SlashCommand("/log", "/log", "Toggle activity log drawer (Ctrl+L)", "view"),
    SlashCommand(
        "/clear",
        "/clear",
        "Return to clean welcome screen",
        "view",
        aliases=("/home",),
    ),
    SlashCommand("/help", "/help", "Show keyboard shortcuts & command reference", "view"),
    SlashCommand(
        "/quit",
        "/quit",
        "Quit ASCII Studio",
        "view",
        aliases=("/exit",),
    ),
]

_ALIAS_MAP: Dict[str, str] = {}
for _cmd in SLASH_COMMANDS:
    _ALIAS_MAP[_cmd.name] = _cmd.name
    for _alias in _cmd.aliases:
        _ALIAS_MAP[_alias] = _cmd.name


def canonical_command_name(token: str) -> str:
    """Resolve a slash command or alias to its canonical slash name."""
    lower = token.strip().lower()
    if not lower.startswith("/"):
        lower = "/" + lower
    return _ALIAS_MAP.get(lower, lower)


def filter_slash_commands(query: str, limit: int = 8) -> List[SlashCommand]:
    """Return slash commands matching *query*, ranking prefix matches first."""
    q = (query or "").strip().lower()
    if not q or q == "/":
        return SLASH_COMMANDS[:limit]
    if not q.startswith("/"):
        q_slash = "/" + q
    else:
        q_slash = q

    prefix_hits: List[SlashCommand] = []
    sub_hits: List[SlashCommand] = []
    q_bare = q_slash.lstrip("/")
    for cmd in SLASH_COMMANDS:
        names = (cmd.name, *cmd.aliases)
        if any(n.startswith(q_slash) for n in names):
            prefix_hits.append(cmd)
        elif any(q_bare in n for n in names) or q_bare in cmd.description.lower():
            sub_hits.append(cmd)
    return (prefix_hits + sub_hits)[:limit]


def _strip_matching_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1].strip()
    return text


def parse_omnibox_input(raw: str) -> Tuple[str, str, str]:
    """Classify omnibox input into (kind, value, arg)."""
    stripped = (raw or "").strip()
    if not stripped:
        return ("empty", "", "")

    if stripped.startswith("/"):
        parts = stripped.split(None, 1)
        cmd = canonical_command_name(parts[0])
        arg = parts[1].strip() if len(parts) > 1 else ""
        return ("command", cmd, arg)

    if stripped.startswith("@"):
        return ("at_file", stripped[1:].strip(), "")

    unquoted = _strip_matching_quotes(stripped)
    expanded = os.path.expanduser(unquoted)
    if os.path.isfile(expanded):
        return ("file", expanded, "")
    if os.path.isdir(expanded):
        return ("dir", expanded, "")

    if is_url(unquoted):
        return ("url", unquoted, "")

    return ("prompt", stripped, "")


def _classify_media_kind(name: str) -> str:
    lower = name.lower()
    if lower.endswith(IMAGE_EXT):
        return "image"
    if lower.endswith(VIDEO_EXT):
        return "video"
    if lower.endswith(LYRICS_EXT):
        return "lyrics"
    return ""


def find_matching_media_files(
    directory: str, query: str, limit: int = 8
) -> List[Tuple[str, str, str]]:
    """Find image/video/lyrics files in *directory* matching *query*."""
    base_dir = os.path.abspath(directory or ".")
    q = (query or "").strip().lower()
    candidates: List[Tuple[str, str, str]] = []
    scanned = 0

    try:
        entries = sorted(os.listdir(base_dir))
    except OSError:
        return []

    subdirs: List[str] = []
    for entry in entries:
        if scanned >= 400:
            break
        scanned += 1
        full = os.path.join(base_dir, entry)
        try:
            if os.path.isdir(full) and not entry.startswith("."):
                subdirs.append(entry)
                continue
            kind = _classify_media_kind(entry)
            if kind:
                candidates.append((entry, full, kind))
        except OSError:
            continue

    for sub in subdirs[:12]:
        if scanned >= 400:
            break
        sub_path = os.path.join(base_dir, sub)
        try:
            for entry in sorted(os.listdir(sub_path)):
                if scanned >= 400:
                    break
                scanned += 1
                full = os.path.join(sub_path, entry)
                if os.path.isfile(full):
                    kind = _classify_media_kind(entry)
                    if kind:
                        candidates.append((os.path.join(sub, entry), full, kind))
        except OSError:
            continue

    if not q:
        return candidates[:limit]

    prefix_hits: List[Tuple[str, str, str]] = []
    sub_hits: List[Tuple[str, str, str]] = []
    for rel, full, kind in candidates:
        low = rel.lower()
        base_low = os.path.basename(low)
        if base_low.startswith(q) or low.startswith(q):
            prefix_hits.append((rel, full, kind))
        elif q in low:
            sub_hits.append((rel, full, kind))
    return (prefix_hits + sub_hits)[:limit]
