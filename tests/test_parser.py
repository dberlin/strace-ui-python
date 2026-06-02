"""Tests for strace_ui.parser — Task 6."""

# ===== Task 6 imports =====
from strace_ui.parser import (
    ValueResult,
    ErrorResult,
    Unfinished,
    Resumed,
    Signal,
    Exit,
    split_args,
    extract_fd_number,
    extract_return_int,
)


# ===== Task 6 tests =====

def test_split_args_basic():
    assert split_args('3, "hi", {x=1, y=2}') == ['3', '"hi"', '{x=1, y=2}']


def test_split_args_empty():
    assert split_args("") == []


def test_extract_fd_number():
    assert extract_fd_number("3</a>") == 3
    assert extract_fd_number("3") == 3
    assert extract_fd_number("AT_FDCWD") is None
    assert extract_fd_number("foo") is None


def test_extract_return_int_plain():
    assert extract_return_int(ValueResult("0")) == 0


def test_extract_return_int_with_annotation():
    assert extract_return_int(ValueResult("3<socket:[123]>")) == 3


def test_extract_return_int_hex():
    assert extract_return_int(ValueResult("0x7f6")) == 0x7f6


def test_extract_return_int_with_trailing_text():
    assert extract_return_int(ValueResult("0 (Timeout)")) == 0


def test_extract_return_int_error_is_none():
    assert extract_return_int(ErrorResult("ENOENT", "No such file")) is None
