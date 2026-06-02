"""Tests for strace_ui.schema — Task 8 (types) and Task 9 (syscall table)."""

# ---------------------------------------------------------------------------
# Task 8: type machinery + Family + best_signature
# ---------------------------------------------------------------------------
from strace_ui.schema import (
    ArgType,
    ReturnType,
    ArgSpec,
    Signature,
    SyscallInfo,
    Family,
    lookup,
)


def test_argtype_is_fd():
    assert ArgType.FILE_DESCRIPTOR.is_file_descriptor()
    assert not ArgType.PATH.is_file_descriptor()


def test_returntype_is_fd():
    assert ReturnType.FILE_DESCRIPTOR.is_file_descriptor()
    assert not ReturnType.INT.is_file_descriptor()


def test_best_signature_exact_match():
    info = SyscallInfo(
        name="x",
        brief="",
        man_section=2,
        signatures=[
            Signature("a", [ArgSpec("p", ArgType.INT)], ReturnType.INT),
            Signature(
                "b",
                [ArgSpec("p", ArgType.INT), ArgSpec("q", ArgType.INT)],
                ReturnType.INT,
            ),
        ],
    )
    assert info.best_signature(arg_count=2).c_signature == "b"


def test_best_signature_fallback_to_most_args():
    info = SyscallInfo(
        name="x",
        brief="",
        man_section=2,
        signatures=[
            Signature("a", [ArgSpec("p", ArgType.INT)], ReturnType.INT),
            Signature(
                "b",
                [ArgSpec("p", ArgType.INT), ArgSpec("q", ArgType.INT)],
                ReturnType.INT,
            ),
        ],
    )
    assert info.best_signature(arg_count=5).c_signature == "b"


def test_family_display_strings():
    assert Family.NETWORK.to_display_string() == "%net"
    assert Family.ALL.to_display_string() == "all"
    assert Family.DESC.to_display_string() == "%desc"


def test_family_net_includes():
    assert Family.NETWORK.includes("socket")
    assert not Family.NETWORK.includes("read")


def test_family_all_includes_everything():
    assert Family.ALL.includes("anything")


# ---------------------------------------------------------------------------
# Task 9: 119-entry syscall table
# ---------------------------------------------------------------------------
from strace_ui.schema import lookup, ArgType, ReturnType, KNOWN_SYSCALLS  # noqa: E402


def test_read_entry():
    info = lookup("read")
    assert info is not None
    sig = info.signatures[0]
    assert sig.c_signature == "ssize_t read(int fd , void * buf , size_t count )"
    assert [a.name for a in sig.args] == ["fd", "buf", "count"]
    assert sig.args[0].arg_type is ArgType.FILE_DESCRIPTOR
    assert sig.args[1].arg_type is ArgType.BUFFER
    assert sig.return_type is ReturnType.SSIZE
    assert info.brief == "Read from a file descriptor"
    assert info.man_section == 2


def test_table_size():
    assert len(KNOWN_SYSCALLS) == 119


def test_openat_is_fd_return():
    assert lookup("openat").signatures[0].return_type is ReturnType.FILE_DESCRIPTOR


def test_socket_lookup():
    assert lookup("socket") is not None


def test_poll_uses_other_argtype():
    nfds = lookup("poll").signatures[0].args[1].arg_type
    assert nfds.kind == "other" and nfds.other == "nfds_t"


def test_unknown_lookup_none():
    assert lookup("definitely_not_a_syscall") is None
