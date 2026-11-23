"""Themes for the TUI.

Three themes plus custom themes from other projects:
- dark (default)
- light
- high_contrast
- retro (CRT theme from retro_sound)
- steins_gate (from SteinsGateShell)
"""

from textual.theme import Theme

# Theme cycle order: dark -> light -> high_contrast -> retro -> steins_gate
THEME_ORDER = ["dark", "light", "high_contrast", "retro", "steins_gate"]

DEFAULT_THEME = "dark"

THEME_STORE = "ascii_player_theme.txt"


def _build_themes():
    """Build the theme registry as Textual Theme objects."""
    themes = {
        "dark": Theme(
            name="dark",
            primary="#0f1117",
            accent="#7c9cff",
            background="#0f1117",
            foreground="#dbe0ea",
            surface="#171a21",
            panel="#171a21",
            warning="#ffb86c",
            error="#ff7b72",
            success="#5ff7b1",
            dark=True,
        ),
        "light": Theme(
            name="light",
            primary="#ffffff",
            accent="#2563eb",
            background="#ffffff",
            foreground="#1a1a2e",
            surface="#fafafa",
            panel="#fafafa",
            warning="#b45309",
            error="#b91c1c",
            success="#166534",
            dark=False,
        ),
        "high_contrast": Theme(
            name="high_contrast",
            primary="#000000",
            accent="#00ff00",
            background="#000000",
            foreground="#ffffff",
            surface="#000000",
            panel="#000000",
            warning="#ffaa00",
            error="#ff0000",
            success="#00ff00",
            dark=True,
        ),
        "retro": Theme(
            name="retro",
            primary="#FFB000",
            accent="#FFB000",
            background="#050505",
            foreground="#F5DEB3",
            surface="#0a0a0a",
            panel="#0a0500",
            warning="#ff8800",
            error="#ff3333",
            success="#33ff00",
            dark=True,
        ),
        "steins_gate": Theme(
            name="steins_gate",
            primary="#333333",
            accent="#2255aa",
            background="#1a1a2e",
            foreground="#ffffff",
            surface="#12121e",
            panel="#0f0f1a",
            warning="#cc8800",
            error="#cc3333",
            success="#33aa66",
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