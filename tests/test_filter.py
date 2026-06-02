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


# ---------------------------------------------------------------------------
# Task 13: passes + relationship logic
# ---------------------------------------------------------------------------

from strace_ui.filter import passes, SyscallInfo as FInfo
from strace_ui.fd_tracker import FdTracker, FdId
from strace_ui.parser import parse_line


def _info(name, pid, fd_ids=(), raw=""):
    return FInfo(syscall_name=name, pid=pid, fd_ids=list(fd_ids), raw_line=raw or name)


def test_passes_empty_is_all():
    assert passes([], _info("read", 1), fd_tracker=FdTracker.empty())


def test_passes_inclusion_only_matches():
    f = parse("read")
    assert passes(f, _info("read", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("write", 1), fd_tracker=FdTracker.empty())


def test_passes_exclusion_only():
    f = parse("-write")
    assert passes(f, _info("read", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("write", 1), fd_tracker=FdTracker.empty())


def test_passes_family():
    f = parse("%net")
    assert passes(f, _info("socket", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 1), fd_tracker=FdTracker.empty())


def test_passes_pid_filter():
    f = parse("pid:5")
    assert passes(f, _info("read", 5), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 6), fd_tracker=FdTracker.empty())


def test_passes_fd_filter_with_generation():
    f = parse("fd:3.1")
    ok = _info("read", 1, fd_ids=[FdId(1, 3, 1)])
    no = _info("read", 1, fd_ids=[FdId(1, 3, 0)])
    assert passes(f, ok, fd_tracker=FdTracker.empty())
    assert not passes(f, no, fd_tracker=FdTracker.empty())


def test_passes_regex_on_raw_line():
    f = parse("/EAGAIN/")
    assert passes(f, _info("read", 1, raw="read(3) = -1 EAGAIN"), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 1, raw="read(3) = 5"), fd_tracker=FdTracker.empty())


def test_passes_related_pid_via_fork():
    t = FdTracker.empty()
    t = t.update(parse_line(0, "100 1.0 clone(child_stack=NULL) = 200"))
    f = parse("rel:100")
    assert passes(f, _info("read", 200), fd_tracker=t)
    assert passes(f, _info("read", 100), fd_tracker=t)
    assert not passes(f, _info("read", 999), fd_tracker=t)
