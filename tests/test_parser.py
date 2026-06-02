"""Tests for strace_ui.parser — Tasks 6 and 7."""

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


# ===== Task 7 imports =====
from strace_ui.parser import parse_line, merge_resumed


# ===== Task 7 tests =====

def test_parse_normal():
    line = "1234 1700000000.123456 read(3, \"abc\", 100) = 3 <0.000123>"
    p = parse_line(0, line)
    assert p.pid == 1234
    assert abs(p.timestamp - 1700000000.123456) < 1e-6
    assert p.syscall_name == "read"
    assert p.args_raw == '3, "abc", 100'
    assert p.result == ValueResult("3")
    assert abs(p.duration - 0.000123) < 1e-9


def test_parse_error():
    p = parse_line(1, '5 1.0 access(\"/x\", F_OK) = -1 ENOENT (No such file or directory)')
    assert p.result == ErrorResult("ENOENT", "No such file or directory")


def test_parse_unfinished():
    p = parse_line(2, '7 2.5 recvmsg(3, {msg_name=...} <unfinished ...>')
    assert isinstance(p.result, Unfinished)
    assert p.args_raw == "3, {msg_name=...}"


def test_parse_resumed():
    p = parse_line(3, '7 2.6 <... recvmsg resumed>, 0) = 64 <0.0001>')
    assert p.syscall_name == "recvmsg"
    assert isinstance(p.result, Resumed)
    assert p.result.inner == ValueResult("64")
    assert abs(p.duration - 0.0001) < 1e-9


def test_parse_signal():
    p = parse_line(4, "9 3.0 --- SIGCHLD {si_signo=SIGCHLD} ---")
    assert p.syscall_name == "<<signal>>"
    assert isinstance(p.result, Signal)


def test_parse_exit():
    p = parse_line(5, "9 3.1 +++ exited with 0 +++")
    assert p.syscall_name == "<<exit>>"
    assert isinstance(p.result, Exit)


def test_parse_unparseable_returns_none():
    assert parse_line(6, "not a strace line") is None


def test_parse_nested_parens_in_args():
    p = parse_line(7, '1 1.0 ioctl(3, TCGETS, {c_iflag=ICRNL (foo), c_oflag=0}) = 0')
    assert p.args_raw == "3, TCGETS, {c_iflag=ICRNL (foo), c_oflag=0}"
    assert p.result == ValueResult("0")


def test_merge_resumed():
    orig = parse_line(0, '7 2.5 recvmsg(3, {a=1}, <unfinished ...>')
    res = parse_line(1, '7 2.6 <... recvmsg resumed> 0) = 64 <0.0001>')
    merged = merge_resumed(orig, res)
    assert merged.args_raw == "3, {a=1}, 0"
    assert merged.result == ValueResult("64")
    assert abs(merged.duration - 0.0001) < 1e-9


def test_merge_resumed_empty_left():
    # unfinished with no captured args yet
    orig = parse_line(0, '7 2.5 read( <unfinished ...>')
    res = parse_line(1, '7 2.6 <... read resumed> 3, "x", 1) = 1 <0.0002>')
    merged = merge_resumed(orig, res)
    assert merged.args_raw == '3, "x", 1'
