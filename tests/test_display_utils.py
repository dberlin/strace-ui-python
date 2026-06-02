from strace_ui.display_utils import split_top_level
from strace_ui.display_utils import (
    decode_strace_escapes, split_escaped_at_byte, strip_fd_annotations, wrap_string,
)


def test_split_top_level_plain():
    assert split_top_level("a, b, c", on=",") == ["a", " b", " c"]


def test_split_top_level_ignores_nested_brackets():
    assert split_top_level("a, [b, c], d", on=",") == ["a", " [b, c]", " d"]


def test_split_top_level_ignores_nested_braces_and_parens():
    assert split_top_level("{x=1, y=2}, htons(0, 1)", on=",") == ["{x=1, y=2}", " htons(0, 1)"]


def test_split_top_level_ignores_commas_in_quoted_strings():
    assert split_top_level('"a,b", c', on=",") == ['"a,b"', " c"]


def test_split_top_level_quote_with_escaped_quote():
    assert split_top_level(r'"a\",b", c', on=",") == [r'"a\",b"', " c"]


def test_split_top_level_empty():
    assert split_top_level("", on=",") == []


# Task 3: escape/byte/fd/wrap helpers

def test_decode_basic_escapes():
    assert decode_strace_escapes(r"a\nb\tc") == "a\nb\tc"


def test_decode_hex_escape():
    assert decode_strace_escapes(r"\x41\x42") == "AB"


def test_decode_null_and_backslash_and_quote():
    assert decode_strace_escapes(r"\0\\\"") == "\x00\\\""


def test_decode_dangling_backslash_kept():
    assert decode_strace_escapes("a\\") == "a\\"


def test_split_escaped_at_byte_counts_hex_as_one():
    meaningful, trailing = split_escaped_at_byte(r"\x41B\x43", byte_count=2)
    assert meaningful == r"\x41B"
    assert trailing == r"\x43"


def test_strip_fd_annotations_numeric():
    assert strip_fd_annotations("3</usr/lib/libc.so>") == "3"


def test_strip_fd_annotations_at_fdcwd():
    assert strip_fd_annotations("AT_FDCWD</home>") == "AT_FDCWD"


def test_strip_fd_annotations_non_numeric_unchanged():
    assert strip_fd_annotations("AF_INET<x>") == "AF_INET<x>"


def test_wrap_string():
    assert wrap_string("abcdef", width=2) == ["ab", "cd", "ef"]
    assert wrap_string("abc", width=10) == ["abc"]
