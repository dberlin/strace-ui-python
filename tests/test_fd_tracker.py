"""Tests for fd_tracker module — port of OCaml fd_tracker.ml"""

from strace_ui.parser import parse_line
from strace_ui.fd_tracker import FdTracker, FdId


def _line(idx, text):
    p = parse_line(idx, text)
    assert p is not None
    return p


def test_open_creates_fd_with_origin():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3'))
    fid = t.resolve_fd(pid=100, fd_number=3)
    assert fid == FdId(source_pid=100, fd_number=3, generation=0)
    origin = t.lookup_origin(fid)
    assert origin.syscall_name == "openat"
    assert '"/etc/passwd"' in origin.summary
    assert origin.syscall_index == 0


def test_close_bumps_generation():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 close(3) = 0'))
    assert t.resolve_fd(pid=100, fd_number=3) is None
    t = t.update(_line(2, '100 1.2 openat(AT_FDCWD, "/b", O_RDONLY) = 3'))
    assert t.resolve_fd(pid=100, fd_number=3) == FdId(100, 3, 1)


def test_dup2_implicit_close_bumps_generation():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 5'))
    t = t.update(_line(1, '100 1.1 dup2(4, 5) = 5'))
    assert t.resolve_fd(100, 5) == FdId(100, 5, 1)


def test_pipe_pair_records_both():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 pipe2([3, 4], O_CLOEXEC) = 0'))
    assert t.resolve_fd(100, 3) == FdId(100, 3, 0)
    assert t.resolve_fd(100, 4) == FdId(100, 4, 0)


def test_fork_inherits_fd_table():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 clone(child_stack=NULL) = 200'))
    assert t.resolve_fd(200, 3) == FdId(source_pid=100, fd_number=3, generation=0)
    assert t.parent_pid(pid=200) == 100


def test_resolve_or_default_pretrace_fd():
    t = FdTracker.empty()
    assert t.resolve_fd_or_default(pid=100, fd_number=7) == FdId(100, 7, 0)


def test_resolve_or_default_closed_is_none():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 close(3) = 0'))
    assert t.resolve_fd_or_default(pid=100, fd_number=3) is None
