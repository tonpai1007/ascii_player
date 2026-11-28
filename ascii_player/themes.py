"""Themes for the TUI.

Seven themes:
- amber (default)
- sand
- dark
- retro (CRT theme from retro_sound)
- steins_gate (from SteinsGateShell)
- light
- high_contrast
"""

from textual.theme import Theme

# Theme cycle order: amber -> sand -> dark -> retro -> steins_gate -> light -> high_contrast
THEME_ORDER = [
    "amber",
    "sand",
    "dark",
    "retro",
    "steins_gate",
    "light",
    "high_contrast",
]

DEFAULT_THEME = "amber"

THEME_STORE = "ascii_player_theme.txt"


def _build_themes():
    """Build the theme registry as Textual Theme objects."""
    themes = {
        "amber": Theme(
            name="amber",
            primary="#27272f",
            accent="#f59e0b",
            background="#0a0a0c",
            foreground="#f4f4f5",
            surface="#111115",
            panel="#18181e",
            warning="#eab308",
            error="#ef4444",
            success="#22c55e",
            dark=True,
        ),
        "sand": Theme(
            name="sand",
            primary="#332d28",
            accent="#d97757",
            background="#141210",
            foreground="#f5f0eb",
            surface="#1c1917",
            panel="#25211e",
            warning="#f59e0b",
            error="#f87171",
            success="#4ade80",
            dark=True,
        ),
        "dark": Theme(
            name="dark",
            primary="#30363d",
            accent="#58a6ff",
            background="#0d1117",
            foreground="#e6edf3",
            surface="#161b22",
            panel="#1c2128",
            warning="#d29922",
            error="#f85149",
            success="#3fb950",
            dark=True,
        ),
        "light": Theme(
            name="light",
            primary="#cbd5e1",
            accent="#2563eb",
            background="#f8fafc",
            foreground="#0f172a",
            surface="#ffffff",
            panel="#f1f5f9",
            warning="#b45309",
            error="#b91c1c",
            success="#15803d",
            dark=False,
        ),
        "high_contrast": Theme(
            name="high_contrast",
            primary="#00ff66",
            accent="#00ff66",
            background="#000000",
            foreground="#ffffff",
            surface="#0a0a0a",
            panel="#111111",
            warning="#ffaa00",
            error="#ff3333",
            success="#00ff66",
            dark=True,
        ),
        "retro": Theme(
            name="retro",
            primary="#b37400",
            accent="#ffb000",
            background="#070500",
            foreground="#ffe4a3",
            surface="#120c00",
            panel="#1a1100",
            warning="#ff8800",
            error="#ff3333",
            success="#33ff00",
            dark=True,
        ),
        "steins_gate": Theme(
            name="steins_gate",
            primary="#3b4d80",
            accent="#ff8c24",
            background="#0c0e1a",
            foreground="#e8ecf8",
            surface="#14182b",
            panel="#1b2038",
            warning="#ffb020",
            error="#ef4444",
            success="#22c55e",
            dark=True,
        ),
    }
    return themes


THEMES = _build_themes()


def load_theme():
    """Load persisted theme from file."""
    try:
        with open(THEME_STORE, "r") as f:
            theme = f.read().strip()
        if theme in THEMES:
            return theme
    except Exception:
        pass
    return DEFAULT_THEME


def save_theme(theme):
    """Persist theme to file."""
    try:
        with open(THEME_STORE, "w") as f:
            f.write(theme)
    except Exception:
        pass


def cycle_theme(current):
    """Return next theme in cycle order."""
    if current not in THEME_ORDER:
        current = DEFAULT_THEME
    idx = THEME_ORDER.index(current)
    return THEME_ORDER[(idx + 1) % len(THEME_ORDER)]


def get_theme(name):
    """Get theme object by name."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def register_themes(app):
    """Register all themes with the app."""
    for name, theme in THEMES.items():
        try:
            app.register_theme(theme)
        except Exception:
            pass


def apply_theme(app, name):
    """Apply a theme to the app."""
    try:
        app.theme = name
    except Exception:
        pass
