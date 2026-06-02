from strace_ui.display_utils import split_top_level
from strace_ui.display_utils import (
    decode_strace_escapes, split_escaped_at_byte, strip_fd_annotations, wrap_string,
)
from strace_ui.display_utils import (
    extract_ip_addresses, resolve_ips_in_string, hexdump_bytes_per_line, compact_args_raw,
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


# Task 4: IP + hexdump-layout + compact helpers

def test_extract_ip_addresses_dedups_and_sorts():
    s = "5<UDP:[30.32.177.12:34003->30.10.253.70:0]> 30.32.177.12"
    assert extract_ip_addresses(s) == ["30.10.253.70", "30.32.177.12"]


def test_extract_ip_rejects_octet_over_255():
    assert extract_ip_addresses("999.1.1.1") == []


def test_resolve_ips_in_string():
    s = "3<TCP:[10.0.0.1:80->10.0.0.2:443]>"
    cache = {"10.0.0.1": "foo", "10.0.0.2": "bar"}
    assert resolve_ips_in_string(s, cache) == "3<TCP:[foo:80->bar:443]>"


def test_hexdump_bytes_per_line_multiple_of_8():
    n = hexdump_bytes_per_line(width=80, total_bytes=256)
    assert n % 8 == 0 and n >= 8


def test_hexdump_bytes_per_line_small_buffer_caps_to_need():
    assert hexdump_bytes_per_line(width=200, total_bytes=3) == 8


def test_compact_args_strips_fd_annotations():
    assert compact_args_raw('3</a/b>, "hi", 0x5') == '3, "hi", 0x5'
