from strace_ui.themes import THEMES, get_theme, default_theme_name, Theme
import pytest


def test_default_is_mocha():
    assert default_theme_name() == "Catppuccin_Mocha"


def test_all_18_themes_present():
    assert len(THEMES) == 18


def test_each_theme_has_all_roles():
    roles = ["fg", "bg", "highlight", "accent", "green", "red", "yellow", "dim", "blue", "teal", "key_hint"]
    for name, t in THEMES.items():
        for r in roles:
            val = getattr(t, r)
            assert isinstance(val, str) and val.startswith("#") and len(val) == 7, f"{name}.{r}={val!r}"


def test_get_theme_case_insensitive_and_unknown():
    assert get_theme("catppuccin_mocha") is THEMES["Catppuccin_Mocha"]
    assert get_theme("Catppuccin_Mocha") is THEMES["Catppuccin_Mocha"]
    with pytest.raises(KeyError):
        get_theme("nope")


def test_theme_names_exact():
    expected = {
        "Catppuccin_Mocha", "Catppuccin_Macchiato", "Catppuccin_Frappe", "Catppuccin_Latte",
        "Vscode_dark", "Vscode_light", "Gruvbox_dark", "Gruvbox_light", "Dracula", "Kanagawa",
        "Tokyo_night_dark", "Tokyo_night_light", "Monokai", "Bluloco", "Solarized_dark",
        "Solarized_light", "Terminal_16", "Terminal_16_inverted",
    }
    assert set(THEMES) == expected
