"""Tests for strace_ui.filter — faithful port of OCaml syscall_filter.ml.

Split into two task groups:
  Task 12: Term union, tokenizer, parse, serializers
  Task 13: passes + relationship logic
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Task 12: Term union, tokenizer, parse, serializers
# ---------------------------------------------------------------------------

from strace_ui.filter import (
    parse,
    to_display_string,
    to_normalized_string,
    normalize,
    IncludeFamily,
    IncludeSyscall,
    ExcludeSyscall,
    FilterPid,
    ExcludePid,
    FilterFd,
    FilterRelatedPid,
    Regex,
)
from strace_ui.schema import Family


def test_parse_family():
    assert parse("%net") == [IncludeFamily(Family.NETWORK)]


def test_parse_include_exclude_syscall():
    assert parse("read -write !futex +open") == [
        IncludeSyscall("read"),
        ExcludeSyscall("write"),
        ExcludeSyscall("futex"),
        IncludeSyscall("open"),
    ]


def test_parse_pid_terms():
    assert parse("pid:5 !pid:9 rel:3") == [FilterPid(5), ExcludePid(9), FilterRelatedPid(3)]


def test_parse_fd_terms():
    assert parse("fd:3 fd:4.2") == [FilterFd(3, None), FilterFd(4, 2)]


def test_parse_regex():
    terms = parse("/foo.*bar/")
    assert len(terms) == 1 and isinstance(terms[0], Regex)
    assert terms[0].matches("xxfooZZbar")


def test_to_display_string_empty_is_all():
    assert to_display_string([]) == "all"


def test_normalize_roundtrip():
    assert normalize("  %net   read  -write ") == "%net read -write"


def test_empty_regex_dropped():
    assert parse("//") == []
