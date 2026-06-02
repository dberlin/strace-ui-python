"""Theme registry for strace_ui.

Each Theme maps 11 semantic roles to hex color strings.
Role→palette mapping follows the OCaml bonsai_term_catppuccin convention:
  fg=Text, bg=Crust, highlight=Surface1, accent=Mauve, green=Green,
  red=Red, yellow=Yellow, dim=Overlay0, blue=Blue, teal=Teal, key_hint=Peach
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    fg: str
    bg: str
    highlight: str
    accent: str
    green: str
    red: str
    yellow: str
    dim: str
    blue: str
    teal: str
    key_hint: str


# ---------------------------------------------------------------------------
# Catppuccin — official palette values
# https://github.com/catppuccin/catppuccin
# Roles: fg=Text, bg=Crust, highlight=Surface1, accent=Mauve,
#        green=Green, red=Red, yellow=Yellow, dim=Overlay0,
#        blue=Blue, teal=Teal, key_hint=Peach
# ---------------------------------------------------------------------------

_catppuccin_mocha = Theme(
    fg="#cdd6f4",        # Text
    bg="#11111b",        # Crust
    highlight="#45475a", # Surface1
    accent="#cba6f7",    # Mauve
    green="#a6e3a1",     # Green
    red="#f38ba8",       # Red
    yellow="#f9e2af",    # Yellow
    dim="#6c7086",       # Overlay0
    blue="#89b4fa",      # Blue
    teal="#94e2d5",      # Teal
    key_hint="#fab387",  # Peach
)

_catppuccin_macchiato = Theme(
    fg="#cad3f5",        # Text
    bg="#181926",        # Crust
    highlight="#363a4f", # Surface1
    accent="#c6a0f6",    # Mauve
    green="#a6da95",     # Green
    red="#ed8796",       # Red
    yellow="#eed49f",    # Yellow
    dim="#6e738d",       # Overlay0
    blue="#8aadf4",      # Blue
    teal="#8bd5ca",      # Teal
    key_hint="#f5a97f",  # Peach
)

_catppuccin_frappe = Theme(
    fg="#c6d0f5",        # Text
    bg="#232634",        # Crust
    highlight="#414559", # Surface1
    accent="#ca9ee6",    # Mauve
    green="#a6d189",     # Green
    red="#e78284",       # Red
    yellow="#e5c890",    # Yellow
    dim="#737994",       # Overlay0
    blue="#8caaee",      # Blue
    teal="#81c8be",      # Teal
    key_hint="#ef9f76",  # Peach
)

_catppuccin_latte = Theme(
    fg="#4c4f69",        # Text (dark for light bg)
    bg="#dce0e8",        # Crust (lightest bg)
    highlight="#acb0be", # Surface1
    accent="#8839ef",    # Mauve
    green="#40a02b",     # Green
    red="#d20f39",       # Red
    yellow="#df8e1d",    # Yellow
    dim="#9ca0b0",       # Overlay0
    blue="#1e66f5",      # Blue
    teal="#179299",      # Teal
    key_hint="#fe640b",  # Peach
)

# ---------------------------------------------------------------------------
# VS Code Dark+ / Light+
# ---------------------------------------------------------------------------

_vscode_dark = Theme(
    fg="#d4d4d4",        # default text
    bg="#1e1e1e",        # editor background
    highlight="#2d2d2d", # selection/lighter bg
    accent="#c586c0",    # purple keyword accent
    green="#4ec9b0",     # green (teal-ish in vscode, use type color)
    red="#f44747",       # error red
    yellow="#dcdcaa",    # yellow (function names)
    dim="#6a9955",       # comment gray-green (dim muted)
    blue="#569cd6",      # keyword blue
    teal="#4ec9b0",      # type teal
    key_hint="#ce9178",  # string orange
)

_vscode_light = Theme(
    fg="#000000",        # main text
    bg="#ffffff",        # background
    highlight="#e8e8e8", # selection bg
    accent="#af00db",    # purple accent
    green="#008000",     # green
    red="#cd3131",       # red
    yellow="#795e26",    # yellow-brown
    dim="#008000",       # comment (green in light theme, muted)
    blue="#0000ff",      # blue keyword
    teal="#267f99",      # teal type color
    key_hint="#e07400",  # orange hint
)

# ---------------------------------------------------------------------------
# Gruvbox
# https://github.com/morhetz/gruvbox
# ---------------------------------------------------------------------------

_gruvbox_dark = Theme(
    fg="#ebdbb2",        # fg1
    bg="#1d2021",        # bg hard
    highlight="#504945", # bg3
    accent="#d3869b",    # purple
    green="#b8bb26",     # bright green
    red="#fb4934",       # bright red
    yellow="#fabd2f",    # bright yellow
    dim="#928374",       # gray
    blue="#83a598",      # bright blue (teal-blue)
    teal="#8ec07c",      # bright aqua
    key_hint="#fe8019",  # bright orange
)

_gruvbox_light = Theme(
    fg="#3c3836",        # fg1 dark
    bg="#f9f5d7",        # bg hard light
    highlight="#d5c4a1", # bg3 light
    accent="#8f3f71",    # purple dark
    green="#79740e",     # dark green
    red="#9d0006",       # dark red
    yellow="#b57614",    # dark yellow
    dim="#928374",       # gray (same)
    blue="#076678",      # dark blue
    teal="#427b58",      # dark aqua
    key_hint="#af3a03",  # dark orange
)

# ---------------------------------------------------------------------------
# Dracula
# https://draculatheme.com/
# ---------------------------------------------------------------------------

_dracula = Theme(
    fg="#f8f8f2",        # foreground
    bg="#21222c",        # darker bg (background-darker variant)
    highlight="#44475a", # selection
    accent="#ff79c6",    # pink/purple accent
    green="#50fa7b",     # green
    red="#ff5555",       # red
    yellow="#f1fa8c",    # yellow
    dim="#6272a4",       # comment
    blue="#8be9fd",      # cyan (used as blue)
    teal="#8be9fd",      # cyan
    key_hint="#ffb86c",  # orange
)

# ---------------------------------------------------------------------------
# Kanagawa
# https://github.com/rebelot/kanagawa.nvim
# ---------------------------------------------------------------------------

_kanagawa = Theme(
    fg="#dcd7ba",        # fujiWhite
    bg="#16161d",        # sumiInk0 (darkest)
    highlight="#2a2a37", # sumiInk3
    accent="#957fb8",    # oniViolet
    green="#76946a",     # springGreen
    red="#c34043",       # autumnRed
    yellow="#dca561",    # autumnYellow (carpYellow would be brighter)
    dim="#727169",       # fujiGray
    blue="#7e9cd8",      # crystalBlue
    teal="#6a9589",      # waveAqua1
    key_hint="#ffa066",  # surimiOrange
)

# ---------------------------------------------------------------------------
# Tokyo Night
# https://github.com/enkia/tokyo-night-vscode-theme
# ---------------------------------------------------------------------------

_tokyo_night_dark = Theme(
    fg="#a9b1d6",        # fg
    bg="#1a1b26",        # bg
    highlight="#24283b", # bg_highlight (actually bg_dark is darker; surface)
    accent="#bb9af7",    # purple
    green="#9ece6a",     # green
    red="#f7768e",       # red
    yellow="#e0af68",    # yellow
    dim="#565f89",       # comment
    blue="#7aa2f7",      # blue
    teal="#2ac3de",      # teal/cyan
    key_hint="#ff9e64",  # orange
)

_tokyo_night_light = Theme(
    fg="#343b58",        # fg dark for light bg
    bg="#d5d6db",        # bg light
    highlight="#c9cad4", # slightly darker surface
    accent="#7847bd",    # purple (darker for light)
    green="#485e30",     # dark green
    red="#8c4351",       # dark red
    yellow="#8f5e15",    # dark yellow
    dim="#9699a3",       # muted gray
    blue="#34548a",      # dark blue
    teal="#0f4b6e",      # dark teal
    key_hint="#965027",  # dark orange
)

# ---------------------------------------------------------------------------
# Monokai
# Classic Monokai (Sublime Text original)
# ---------------------------------------------------------------------------

_monokai = Theme(
    fg="#f8f8f2",        # foreground
    bg="#272822",        # background
    highlight="#3e3d32", # selection/lighter bg
    accent="#ae81ff",    # purple
    green="#a6e22e",     # green
    red="#f92672",       # red/pink
    yellow="#e6db74",    # yellow
    dim="#75715e",       # comment
    blue="#66d9e8",      # cyan (monokai's "blue")
    teal="#66d9e8",      # cyan/teal
    key_hint="#fd971f",  # orange
)

# ---------------------------------------------------------------------------
# Bluloco
# https://github.com/uloco/theme-bluloco-dark
# ---------------------------------------------------------------------------

_bluloco = Theme(
    fg="#abb2bf",        # foreground
    bg="#282c34",        # background (dark)
    highlight="#353b45", # slightly lighter bg
    accent="#d09eee",    # purple/violet
    green="#3fc56b",     # green
    red="#fc2f52",       # red
    yellow="#f9c859",    # yellow
    dim="#636d83",       # comment/dim
    blue="#10b1fe",      # blue
    teal="#5fb3b3",      # teal
    key_hint="#ff936a",  # orange
)

# ---------------------------------------------------------------------------
# Solarized
# https://ethanschoonover.com/solarized/
# ---------------------------------------------------------------------------

_solarized_dark = Theme(
    fg="#839496",        # base0 (primary fg on dark)
    bg="#002b36",        # base03 (darkest bg)
    highlight="#073642", # base02 (bg highlights)
    accent="#6c71c4",    # violet
    green="#859900",     # green
    red="#dc322f",       # red
    yellow="#b58900",    # yellow
    dim="#586e75",       # base01 (comments)
    blue="#268bd2",      # blue
    teal="#2aa198",      # cyan
    key_hint="#cb4b16",  # orange
)

_solarized_light = Theme(
    fg="#657b83",        # base00 (primary fg on light)
    bg="#fdf6e3",        # base3 (lightest bg)
    highlight="#eee8d5", # base2 (bg highlights)
    accent="#6c71c4",    # violet
    green="#859900",     # green
    red="#dc322f",       # red
    yellow="#b58900",    # yellow
    dim="#93a1a1",       # base1 (comments on light)
    blue="#268bd2",      # blue
    teal="#2aa198",      # cyan
    key_hint="#cb4b16",  # orange
)

# ---------------------------------------------------------------------------
# Terminal 16 — standard ANSI 16-color palette
# ---------------------------------------------------------------------------

_terminal_16 = Theme(
    fg="#ffffff",        # bright white
    bg="#000000",        # black
    highlight="#404040", # dark gray (selection)
    accent="#cd00cd",    # magenta
    green="#00cd00",     # green
    red="#cd0000",       # red
    yellow="#cdcd00",    # yellow
    dim="#7f7f7f",       # dark gray (dim/comments)
    blue="#0000cd",      # blue
    teal="#00cdcd",      # cyan
    key_hint="#cd5c00",  # dark orange (brown)
)

_terminal_16_inverted = Theme(
    fg="#000000",        # black text on white
    bg="#ffffff",        # white bg
    highlight="#d0d0d0", # light gray selection
    accent="#800080",    # darker magenta
    green="#006400",     # dark green
    red="#8b0000",       # dark red
    yellow="#808000",    # dark yellow/olive
    dim="#696969",       # dim gray
    blue="#00008b",      # dark blue
    teal="#008b8b",      # dark cyan
    key_hint="#8b4500",  # dark orange/brown
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THEMES: dict[str, Theme] = {
    "Catppuccin_Mocha": _catppuccin_mocha,
    "Catppuccin_Macchiato": _catppuccin_macchiato,
    "Catppuccin_Frappe": _catppuccin_frappe,
    "Catppuccin_Latte": _catppuccin_latte,
    "Vscode_dark": _vscode_dark,
    "Vscode_light": _vscode_light,
    "Gruvbox_dark": _gruvbox_dark,
    "Gruvbox_light": _gruvbox_light,
    "Dracula": _dracula,
    "Kanagawa": _kanagawa,
    "Tokyo_night_dark": _tokyo_night_dark,
    "Tokyo_night_light": _tokyo_night_light,
    "Monokai": _monokai,
    "Bluloco": _bluloco,
    "Solarized_dark": _solarized_dark,
    "Solarized_light": _solarized_light,
    "Terminal_16": _terminal_16,
    "Terminal_16_inverted": _terminal_16_inverted,
}

# Build a lowercase → canonical-key index for case-insensitive lookup
_LOWER_INDEX: dict[str, str] = {k.lower(): k for k in THEMES}


def default_theme_name() -> str:
    """Return the name of the default theme."""
    return "Catppuccin_Mocha"


def get_theme(name: str) -> Theme:
    """Return the Theme for *name*, case-insensitively.

    Raises KeyError if the name is not found.
    """
    canonical = _LOWER_INDEX.get(name.lower())
    if canonical is None:
        raise KeyError(name)
    return THEMES[canonical]
