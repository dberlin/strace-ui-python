"""Tests for cli.build_strace_args — TDD as specified."""
import pytest
from strace_ui.cli import build_strace_args


def test_build_args_program():
    args = build_strace_args(write_fd=7, trace_expr=None, attach_pid=None, program=["ping", "localhost"])
    assert args[:10] == ["-ttt", "-T", "-f", "-x", "-yy", "-v", "-s", "1024", "-o", "/dev/fd/7"]
    assert args[-3:] == ["--", "ping", "localhost"]


def test_build_args_pid_and_expr():
    args = build_strace_args(write_fd=7, trace_expr="trace=%net", attach_pid=12345, program=[])
    assert "-e" in args and "trace=%net" in args
    assert "-p" in args and "12345" in args


def test_build_args_requires_target():
    with pytest.raises(SystemExit):
        build_strace_args(write_fd=7, trace_expr=None, attach_pid=None, program=[])
