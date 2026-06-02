"""Tests for strace_ui.render — text-content functions."""

from rich.text import Text

from strace_ui.render import (
    render_syscall_row_text,
    hexdump_lines_text,
    render_value_tree_text,
)
from strace_ui.themes import THEMES
from strace_ui.parser import parse_line
from strace_ui.value import parse as vparse

T = THEMES["Catppuccin_Mocha"]


def test_syscall_row_contains_name_and_result():
    p = parse_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3')
    txt = render_syscall_row_text(p, theme=T, width=60, short_id=1, pid_width=1, selected_pid=100)
    s = txt.plain
    assert "openat" in s
    assert "3" in s


def test_hexdump_lines_format():
    lines = hexdump_lines_text("ABC", theme=T, bytes_per_line=8)
    assert len(lines) == 1
    s = lines[0].plain
    assert s.startswith("0000 ")
    assert "41 42 43" in s
    assert "ABC" in s


def test_value_tree_text():
    lines = render_value_tree_text(vparse("{a=1, b=2}"), theme=T)
    plains = [l.plain for l in lines]
    assert plains == ["├─a = 1", "╰─b = 2"]
