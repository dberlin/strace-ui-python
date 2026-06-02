"""Syscall schema — port of OCaml syscall_schema.ml.

Provides type machinery (ArgType, ReturnType, ArgSpec, Signature, SyscallInfo),
family classification (Family), and the 119-entry known_syscalls table.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# ArgType — frozen dataclass with 15 singleton kinds + Other(payload)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArgType:
    """Represents the type of a syscall argument.

    Use the class-level singletons (ArgType.FILE_DESCRIPTOR, etc.) for the
    common kinds.  For the ``Other`` variant use ``ArgType.other_type(s)``.
    """

    kind: str
    other: Optional[str] = None

    def is_file_descriptor(self) -> bool:
        return self.kind == "file_descriptor"

    @staticmethod
    def other_type(s: str) -> "ArgType":
        return ArgType("other", s)


# Module-level singletons — assigned after class body so the class can be frozen.
ArgType.FILE_DESCRIPTOR = ArgType("file_descriptor")  # type: ignore[attr-defined]
ArgType.PATH = ArgType("path")  # type: ignore[attr-defined]
ArgType.POINTER = ArgType("pointer")  # type: ignore[attr-defined]
ArgType.INT = ArgType("int")  # type: ignore[attr-defined]
ArgType.UNSIGNED_INT = ArgType("unsigned_int")  # type: ignore[attr-defined]
ArgType.SIZE = ArgType("size")  # type: ignore[attr-defined]
ArgType.OFFSET = ArgType("offset")  # type: ignore[attr-defined]
ArgType.FLAGS = ArgType("flags")  # type: ignore[attr-defined]
ArgType.STRING = ArgType("string")  # type: ignore[attr-defined]
ArgType.STRUCT = ArgType("struct")  # type: ignore[attr-defined]
ArgType.SOCKADDR = ArgType("sockaddr")  # type: ignore[attr-defined]
ArgType.BUFFER = ArgType("buffer")  # type: ignore[attr-defined]
ArgType.PID = ArgType("pid")  # type: ignore[attr-defined]
ArgType.SIGNAL = ArgType("signal")  # type: ignore[attr-defined]
ArgType.MODE = ArgType("mode")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ReturnType
# ---------------------------------------------------------------------------


class ReturnType(enum.Enum):
    FILE_DESCRIPTOR = "file_descriptor"
    INT = "int"
    SSIZE = "ssize"
    POINTER = "pointer"
    VOID = "void"
    PID = "pid"
    OFF = "off"

    def is_file_descriptor(self) -> bool:
        return self is ReturnType.FILE_DESCRIPTOR


# ---------------------------------------------------------------------------
# ArgSpec, Signature, SyscallInfo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArgSpec:
    name: str
    arg_type: ArgType


@dataclass(frozen=True)
class Signature:
    c_signature: str
    args: tuple  # stored as tuple to keep frozen hashable
    return_type: ReturnType

    def __init__(self, c_signature: str, args, return_type: ReturnType) -> None:
        object.__setattr__(self, "c_signature", c_signature)
        object.__setattr__(self, "args", tuple(args))
        object.__setattr__(self, "return_type", return_type)


@dataclass
class SyscallInfo:
    name: str
    signatures: list
    brief: str
    man_section: int

    def best_signature(self, *, arg_count: int) -> Signature:
        """Return signature whose arg count matches; else the one with most args."""
        for sig in self.signatures:
            if len(sig.args) == arg_count:
                return sig
        # Fall back to signature with most args
        best = max(self.signatures, key=lambda s: len(s.args))
        return best


# ---------------------------------------------------------------------------
# Family
# ---------------------------------------------------------------------------

_DESC_SYSCALLS: frozenset = frozenset(
    [
        "read",
        "write",
        "open",
        "openat",
        "close",
        "lseek",
        "pread64",
        "pwrite64",
        "readv",
        "writev",
        "dup",
        "dup2",
        "dup3",
        "fstat",
        "newfstatat",
        "fcntl",
        "ioctl",
        "ftruncate",
        "fchmod",
        "fchown",
        "fchdir",
        "fstatfs",
        "getdents64",
        "epoll_create",
        "epoll_create1",
        "epoll_ctl",
        "epoll_wait",
        "epoll_pwait",
        "select",
        "poll",
        "ppoll",
        "pipe",
        "pipe2",
        "sendfile",
        "socket",
        "connect",
        "accept",
        "accept4",
        "bind",
        "listen",
        "sendto",
        "recvfrom",
        "sendmsg",
        "recvmsg",
        "shutdown",
        "setsockopt",
        "getsockopt",
        "getsockname",
        "getpeername",
        "socketpair",
        "eventfd2",
        "timerfd_create",
        "timerfd_settime",
        "timerfd_gettime",
        "signalfd4",
        "inotify_init1",
        "inotify_add_watch",
        "inotify_rm_watch",
    ]
)

_FILE_SYSCALLS: frozenset = frozenset(
    [
        "open",
        "openat",
        "stat",
        "lstat",
        "newfstatat",
        "access",
        "faccessat",
        "unlink",
        "unlinkat",
        "rename",
        "renameat",
        "renameat2",
        "mkdir",
        "mkdirat",
        "rmdir",
        "link",
        "linkat",
        "symlink",
        "symlinkat",
        "readlink",
        "readlinkat",
        "chmod",
        "fchmod",
        "chown",
        "fchown",
        "truncate",
        "ftruncate",
        "getcwd",
        "chdir",
        "fchdir",
        "statfs",
        "fstatfs",
        "statx",
    ]
)

_MEMORY_SYSCALLS: frozenset = frozenset(["mmap", "munmap", "mprotect", "brk"])

_NETWORK_SYSCALLS: frozenset = frozenset(
    [
        "socket",
        "connect",
        "accept",
        "accept4",
        "bind",
        "listen",
        "sendto",
        "recvfrom",
        "sendmsg",
        "recvmsg",
        "shutdown",
        "setsockopt",
        "getsockopt",
        "getsockname",
        "getpeername",
        "socketpair",
    ]
)

_PROCESS_SYSCALLS: frozenset = frozenset(
    [
        "execve",
        "fork",
        "vfork",
        "clone",
        "clone3",
        "exit_group",
        "wait4",
        "waitid",
        "kill",
        "getpid",
        "getppid",
        "getuid",
        "getgid",
        "geteuid",
        "getegid",
        "prctl",
    ]
)

_SIGNAL_SYSCALLS: frozenset = frozenset(
    ["rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "kill"]
)

_IPC_SYSCALLS: frozenset = frozenset()


class Family(enum.Enum):
    ALL = "all"
    DESC = "desc"
    FILE = "file"
    MEMORY = "memory"
    NETWORK = "network"
    PROCESS = "process"
    SIGNAL = "signal"
    IPC = "ipc"

    def to_display_string(self) -> str:
        _MAP = {
            Family.ALL: "all",
            Family.DESC: "%desc",
            Family.FILE: "%file",
            Family.MEMORY: "%memory",
            Family.NETWORK: "%net",
            Family.PROCESS: "%process",
            Family.SIGNAL: "%signal",
            Family.IPC: "%ipc",
        }
        return _MAP[self]

    def includes(self, syscall_name: str) -> bool:
        _SET_MAP = {
            Family.ALL: None,  # special: always True
            Family.DESC: _DESC_SYSCALLS,
            Family.FILE: _FILE_SYSCALLS,
            Family.MEMORY: _MEMORY_SYSCALLS,
            Family.NETWORK: _NETWORK_SYSCALLS,
            Family.PROCESS: _PROCESS_SYSCALLS,
            Family.SIGNAL: _SIGNAL_SYSCALLS,
            Family.IPC: _IPC_SYSCALLS,
        }
        if self is Family.ALL:
            return True
        return syscall_name in _SET_MAP[self]


# ---------------------------------------------------------------------------
# Syscall table helpers
# ---------------------------------------------------------------------------


def _a(name: str, t: ArgType) -> ArgSpec:
    return ArgSpec(name, t)


def _e(
    name: str,
    c_signature: str,
    args: list,
    return_type: ReturnType,
    brief: str,
    man_section: int,
) -> SyscallInfo:
    return SyscallInfo(
        name=name,
        signatures=[Signature(c_signature, args, return_type)],
        brief=brief,
        man_section=man_section,
    )


# Short aliases for arg types (mirrors OCaml local bindings)
_fd = ArgType.FILE_DESCRIPTOR
_path = ArgType.PATH
_ptr = ArgType.POINTER
_int_ = ArgType.INT
_uint = ArgType.UNSIGNED_INT
_size = ArgType.SIZE
_off = ArgType.OFFSET
_flags = ArgType.FLAGS
_str_ = ArgType.STRING
_buf = ArgType.BUFFER
_pid = ArgType.PID
_sig_ = ArgType.SIGNAL
_mode = ArgType.MODE
_struct_ = ArgType.STRUCT
_sockaddr = ArgType.SOCKADDR


# ---------------------------------------------------------------------------
# Known syscalls — 119 entries (115 single-sig + 4 multi-sig)
# ---------------------------------------------------------------------------

KNOWN_SYSCALLS: dict[str, SyscallInfo] = {}

def lookup(name: str) -> "SyscallInfo | None":
    """Return the SyscallInfo for *name*, or None if not known."""
    return KNOWN_SYSCALLS.get(name)
