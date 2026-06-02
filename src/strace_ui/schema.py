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

KNOWN_SYSCALLS: dict[str, SyscallInfo] = {
    "read": _e(
        "read",
        "ssize_t read(int fd , void * buf , size_t count )",
        [_a("fd", _fd), _a("buf", _buf), _a("count", _size)],
        ReturnType.SSIZE,
        "Read from a file descriptor",
        2,
    ),
    "write": _e(
        "write",
        "ssize_t write(int fd , const void * buf , size_t count )",
        [_a("fd", _fd), _a("buf", _buf), _a("count", _size)],
        ReturnType.SSIZE,
        "Write to a file descriptor",
        2,
    ),
    "open": SyscallInfo(
        name="open",
        signatures=[
            Signature(
                "int open(const char * pathname , int flags )",
                [_a("pathname", _path), _a("flags", _flags)],
                ReturnType.FILE_DESCRIPTOR,
            ),
            Signature(
                "int open(const char * pathname , int flags , mode_t mode )",
                [_a("pathname", _path), _a("flags", _flags), _a("mode", _mode)],
                ReturnType.FILE_DESCRIPTOR,
            ),
        ],
        brief="Open and possibly create a file",
        man_section=2,
    ),
    "openat": SyscallInfo(
        name="openat",
        signatures=[
            Signature(
                "int openat(int dirfd , const char * pathname , int flags )",
                [_a("dirfd", _fd), _a("pathname", _path), _a("flags", _flags)],
                ReturnType.FILE_DESCRIPTOR,
            ),
            Signature(
                "int openat(int dirfd , const char * pathname , int flags , mode_t mode )",
                [
                    _a("dirfd", _fd),
                    _a("pathname", _path),
                    _a("flags", _flags),
                    _a("mode", _mode),
                ],
                ReturnType.FILE_DESCRIPTOR,
            ),
        ],
        brief="Open and possibly create a file",
        man_section=2,
    ),
    "close": _e(
        "close",
        "int close(int fd )",
        [_a("fd", _fd)],
        ReturnType.INT,
        "Close a file descriptor",
        2,
    ),
    "lseek": _e(
        "lseek",
        "off_t lseek(int fd , off_t offset , int whence )",
        [_a("fd", _fd), _a("offset", _off), _a("whence", _flags)],
        ReturnType.OFF,
        "Reposition read/write file offset",
        2,
    ),
    "pread64": _e(
        "pread64",
        "ssize_t pread(int fd , void * buf , size_t count , off_t offset )",
        [_a("fd", _fd), _a("buf", _buf), _a("count", _size), _a("offset", _off)],
        ReturnType.SSIZE,
        "Read from or write to a file descriptor at a given offset",
        2,
    ),
    "pwrite64": _e(
        "pwrite64",
        "ssize_t pwrite(int fd , const void * buf , size_t count , off_t offset )",
        [_a("fd", _fd), _a("buf", _buf), _a("count", _size), _a("offset", _off)],
        ReturnType.SSIZE,
        "Read from or write to a file descriptor at a given offset",
        2,
    ),
    "readv": _e(
        "readv",
        "ssize_t readv(int fd , const struct iovec * iov , int iovcnt )",
        [_a("fd", _fd), _a("iov", _struct_), _a("iovcnt", _int_)],
        ReturnType.SSIZE,
        "Read or write data into multiple buffers",
        2,
    ),
    "writev": _e(
        "writev",
        "ssize_t writev(int fd , const struct iovec * iov , int iovcnt )",
        [_a("fd", _fd), _a("iov", _struct_), _a("iovcnt", _int_)],
        ReturnType.SSIZE,
        "Read or write data into multiple buffers",
        2,
    ),
    "dup": _e(
        "dup",
        "int dup(int oldfd )",
        [_a("oldfd", _fd)],
        ReturnType.FILE_DESCRIPTOR,
        "Duplicate a file descriptor",
        2,
    ),
    "dup2": _e(
        "dup2",
        "int dup2(int oldfd , int newfd )",
        [_a("oldfd", _fd), _a("newfd", _fd)],
        ReturnType.FILE_DESCRIPTOR,
        "Duplicate a file descriptor",
        2,
    ),
    "dup3": _e(
        "dup3",
        "int dup3(int oldfd , int newfd , int flags )",
        [_a("oldfd", _fd), _a("newfd", _fd), _a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Duplicate a file descriptor",
        2,
    ),
    "stat": _e(
        "stat",
        "int stat(const char * pathname , struct stat * statbuf )",
        [_a("pathname", _path), _a("statbuf", _struct_)],
        ReturnType.INT,
        "Get file status",
        2,
    ),
    "fstat": _e(
        "fstat",
        "int fstat(int fd , struct stat * statbuf )",
        [_a("fd", _fd), _a("statbuf", _struct_)],
        ReturnType.INT,
        "Get file status",
        2,
    ),
    "lstat": _e(
        "lstat",
        "int lstat(const char * pathname , struct stat * statbuf )",
        [_a("pathname", _path), _a("statbuf", _struct_)],
        ReturnType.INT,
        "Get file status",
        2,
    ),
    "access": _e(
        "access",
        "int access(const char * pathname , int mode )",
        [_a("pathname", _path), _a("mode", _int_)],
        ReturnType.INT,
        "Check user's permissions for a file",
        2,
    ),
    "faccessat": _e(
        "faccessat",
        "int faccessat(int dirfd , const char * pathname , int mode , int flags )",
        [_a("dirfd", _fd), _a("pathname", _path), _a("mode", _int_), _a("flags", _flags)],
        ReturnType.INT,
        "Check user's permissions for a file",
        2,
    ),
    "unlink": _e(
        "unlink",
        "int unlink(const char * pathname )",
        [_a("pathname", _path)],
        ReturnType.INT,
        "Delete a name and possibly the file it refers to",
        2,
    ),
    "unlinkat": _e(
        "unlinkat",
        "int unlinkat(int dirfd , const char * pathname , int flags )",
        [_a("dirfd", _fd), _a("pathname", _path), _a("flags", _flags)],
        ReturnType.INT,
        "Delete a name and possibly the file it refers to",
        2,
    ),
    "rename": _e(
        "rename",
        "int rename(const char * oldpath , const char * newpath )",
        [_a("oldpath", _path), _a("newpath", _path)],
        ReturnType.INT,
        "Change the name or location of a file",
        2,
    ),
    "renameat": _e(
        "renameat",
        "int renameat(int olddirfd , const char * oldpath , int newdirfd , const char * newpath )",
        [
            _a("olddirfd", _fd),
            _a("oldpath", _path),
            _a("newdirfd", _fd),
            _a("newpath", _path),
        ],
        ReturnType.INT,
        "Change the name or location of a file",
        2,
    ),
    "renameat2": _e(
        "renameat2",
        "int renameat2(int olddirfd , const char * oldpath , int newdirfd , const char * newpath , unsigned int flags )",
        [
            _a("olddirfd", _fd),
            _a("oldpath", _path),
            _a("newdirfd", _fd),
            _a("newpath", _path),
            _a("flags", _flags),
        ],
        ReturnType.INT,
        "Change the name or location of a file",
        2,
    ),
    "mkdir": _e(
        "mkdir",
        "int mkdir(const char * pathname , mode_t mode )",
        [_a("pathname", _path), _a("mode", _mode)],
        ReturnType.INT,
        "Create a directory",
        2,
    ),
    "mkdirat": _e(
        "mkdirat",
        "int mkdirat(int dirfd , const char * pathname , mode_t mode )",
        [_a("dirfd", _fd), _a("pathname", _path), _a("mode", _mode)],
        ReturnType.INT,
        "Create a directory",
        2,
    ),
    "rmdir": _e(
        "rmdir",
        "int rmdir(const char * pathname )",
        [_a("pathname", _path)],
        ReturnType.INT,
        "Delete a directory",
        2,
    ),
    "link": _e(
        "link",
        "int link(const char * oldpath , const char * newpath )",
        [_a("oldpath", _path), _a("newpath", _path)],
        ReturnType.INT,
        "Make a new name for a file",
        2,
    ),
    "linkat": _e(
        "linkat",
        "int linkat(int olddirfd , const char * oldpath , int newdirfd , const char * newpath , int flags )",
        [
            _a("olddirfd", _fd),
            _a("oldpath", _path),
            _a("newdirfd", _fd),
            _a("newpath", _path),
            _a("flags", _flags),
        ],
        ReturnType.INT,
        "Make a new name for a file",
        2,
    ),
    "symlink": _e(
        "symlink",
        "int symlink(const char * target , const char * linkpath )",
        [_a("target", _path), _a("linkpath", _path)],
        ReturnType.INT,
        "Make a new name for a file",
        2,
    ),
    "symlinkat": _e(
        "symlinkat",
        "int symlinkat(const char * target , int newdirfd , const char * linkpath )",
        [_a("target", _path), _a("newdirfd", _fd), _a("linkpath", _path)],
        ReturnType.INT,
        "Make a new name for a file",
        2,
    ),
    "readlink": _e(
        "readlink",
        "ssize_t readlink(const char * pathname , char * buf , size_t bufsiz )",
        [_a("pathname", _path), _a("buf", _buf), _a("bufsiz", _size)],
        ReturnType.SSIZE,
        "Read value of a symbolic link",
        2,
    ),
    "readlinkat": _e(
        "readlinkat",
        "ssize_t readlinkat(int dirfd , const char * pathname , char * buf , size_t bufsiz )",
        [_a("dirfd", _fd), _a("pathname", _path), _a("buf", _buf), _a("bufsiz", _size)],
        ReturnType.SSIZE,
        "Read value of a symbolic link",
        2,
    ),
    "chmod": _e(
        "chmod",
        "int chmod(const char * pathname , mode_t mode )",
        [_a("pathname", _path), _a("mode", _mode)],
        ReturnType.INT,
        "Change permissions of a file",
        2,
    ),
    "fchmod": _e(
        "fchmod",
        "int fchmod(int fd , mode_t mode )",
        [_a("fd", _fd), _a("mode", _mode)],
        ReturnType.INT,
        "Change permissions of a file",
        2,
    ),
    "chown": _e(
        "chown",
        "int chown(const char * pathname , uid_t owner , gid_t group )",
        [_a("pathname", _path), _a("owner", _int_), _a("group", _int_)],
        ReturnType.INT,
        "Change ownership of a file",
        2,
    ),
    "fchown": _e(
        "fchown",
        "int fchown(int fd , uid_t owner , gid_t group )",
        [_a("fd", _fd), _a("owner", _int_), _a("group", _int_)],
        ReturnType.INT,
        "Change ownership of a file",
        2,
    ),
    "truncate": _e(
        "truncate",
        "int truncate(const char * path , off_t length )",
        [_a("path", _path), _a("length", _off)],
        ReturnType.INT,
        "Truncate a file to a specified length",
        2,
    ),
    "ftruncate": _e(
        "ftruncate",
        "int ftruncate(int fd , off_t length )",
        [_a("fd", _fd), _a("length", _off)],
        ReturnType.INT,
        "Truncate a file to a specified length",
        2,
    ),
    "getcwd": _e(
        "getcwd",
        "char *getcwd(char * buf , size_t size )",
        [_a("buf", _buf), _a("size", _size)],
        ReturnType.POINTER,
        "Get current working directory",
        3,
    ),
    "chdir": _e(
        "chdir",
        "int chdir(const char * path )",
        [_a("path", _path)],
        ReturnType.INT,
        "Change working directory",
        2,
    ),
    "fchdir": _e(
        "fchdir",
        "int fchdir(int fd )",
        [_a("fd", _fd)],
        ReturnType.INT,
        "Change working directory",
        2,
    ),
    "mmap": _e(
        "mmap",
        "void *mmap(void * addr , size_t length , int prot , int flags , int fd , off_t offset )",
        [
            _a("addr", _ptr),
            _a("length", _size),
            _a("prot", _flags),
            _a("flags", _flags),
            _a("fd", _fd),
            _a("offset", _off),
        ],
        ReturnType.POINTER,
        "Map or unmap files or devices into memory",
        2,
    ),
    "munmap": _e(
        "munmap",
        "int munmap(void * addr , size_t length )",
        [_a("addr", _ptr), _a("length", _size)],
        ReturnType.INT,
        "Map or unmap files or devices into memory",
        2,
    ),
    "mprotect": _e(
        "mprotect",
        "int mprotect(void * addr , size_t len , int prot )",
        [_a("addr", _ptr), _a("len", _size), _a("prot", _flags)],
        ReturnType.INT,
        "Set protection on a region of memory",
        2,
    ),
    "brk": _e(
        "brk",
        "int brk(void * addr )",
        [_a("addr", _ptr)],
        ReturnType.INT,
        "Change data segment size",
        2,
    ),
    "execve": _e(
        "execve",
        "int execve(const char * filename , char *const argv [], char *const envp [])",
        [_a("filename", _path), _a("argv", _ptr), _a("envp", _ptr)],
        ReturnType.INT,
        "Execute program",
        2,
    ),
    "fork": _e(
        "fork",
        "pid_t fork(void)",
        [],
        ReturnType.PID,
        "Create a child process",
        2,
    ),
    "vfork": _e(
        "vfork",
        "pid_t vfork(void)",
        [],
        ReturnType.PID,
        "Create a child process and block parent",
        2,
    ),
    "clone": _e(
        "clone",
        "long clone(unsigned long flags, void *child_stack, int *ptid, int *ctid, unsigned long newtls)",
        [
            _a("flags", _flags),
            _a("child_stack", _ptr),
            _a("ptid", _ptr),
            _a("ctid", _ptr),
            _a("newtls", _uint),
        ],
        ReturnType.PID,
        "Create a child process",
        2,
    ),
    "exit_group": _e(
        "exit_group",
        "void exit_group(int status )",
        [_a("status", _int_)],
        ReturnType.VOID,
        "Exit all threads in a process",
        2,
    ),
    "wait4": _e(
        "wait4",
        "pid_t wait4(pid_t pid , int * wstatus , int options , struct rusage * rusage )",
        [_a("pid", _pid), _a("wstatus", _ptr), _a("options", _flags), _a("rusage", _struct_)],
        ReturnType.PID,
        "Wait for process to change state, BSD style",
        2,
    ),
    "waitid": _e(
        "waitid",
        "int waitid(idtype_t idtype , id_t id , siginfo_t * infop , int options )",
        [_a("idtype", _int_), _a("id", _int_), _a("infop", _ptr), _a("options", _flags)],
        ReturnType.INT,
        "Wait for process to change state",
        2,
    ),
    "kill": _e(
        "kill",
        "int kill(pid_t pid , int sig )",
        [_a("pid", _pid), _a("sig", _sig_)],
        ReturnType.INT,
        "Send signal to a process",
        2,
    ),
    "getpid": _e(
        "getpid",
        "pid_t getpid(void)",
        [],
        ReturnType.PID,
        "Get process identification",
        2,
    ),
    "getppid": _e(
        "getppid",
        "pid_t getppid(void)",
        [],
        ReturnType.PID,
        "Get process identification",
        2,
    ),
    "getuid": _e(
        "getuid",
        "uid_t getuid(void)",
        [],
        ReturnType.INT,
        "Get user identity",
        2,
    ),
    "getgid": _e(
        "getgid",
        "gid_t getgid(void)",
        [],
        ReturnType.INT,
        "Get group identity",
        2,
    ),
    "geteuid": _e(
        "geteuid",
        "uid_t geteuid(void)",
        [],
        ReturnType.INT,
        "Get user identity",
        2,
    ),
    "getegid": _e(
        "getegid",
        "gid_t getegid(void)",
        [],
        ReturnType.INT,
        "Get group identity",
        2,
    ),
    "socket": _e(
        "socket",
        "int socket(int domain , int type , int protocol )",
        [_a("domain", _int_), _a("type", _int_), _a("protocol", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Create an endpoint for communication",
        2,
    ),
    "connect": _e(
        "connect",
        "int connect(int sockfd , const struct sockaddr * addr , socklen_t addrlen )",
        [_a("sockfd", _fd), _a("addr", _sockaddr), _a("addrlen", _size)],
        ReturnType.INT,
        "Initiate a connection on a socket",
        2,
    ),
    "accept": _e(
        "accept",
        "int accept(int sockfd , struct sockaddr * addr , socklen_t * addrlen )",
        [_a("sockfd", _fd), _a("addr", _sockaddr), _a("addrlen", _size)],
        ReturnType.FILE_DESCRIPTOR,
        "Accept a connection on a socket",
        2,
    ),
    "accept4": _e(
        "accept4",
        "int accept4(int sockfd , struct sockaddr * addr , socklen_t * addrlen , int flags )",
        [
            _a("sockfd", _fd),
            _a("addr", _sockaddr),
            _a("addrlen", _size),
            _a("flags", _flags),
        ],
        ReturnType.FILE_DESCRIPTOR,
        "Accept a connection on a socket",
        2,
    ),
    "bind": _e(
        "bind",
        "int bind(int sockfd , const struct sockaddr * addr , socklen_t addrlen )",
        [_a("sockfd", _fd), _a("addr", _sockaddr), _a("addrlen", _size)],
        ReturnType.INT,
        "Bind a name to a socket",
        2,
    ),
    "listen": _e(
        "listen",
        "int listen(int sockfd , int backlog )",
        [_a("sockfd", _fd), _a("backlog", _int_)],
        ReturnType.INT,
        "Listen for connections on a socket",
        2,
    ),
    "sendto": _e(
        "sendto",
        "ssize_t sendto(int sockfd , const void * buf , size_t len , int flags , const struct sockaddr * dest_addr , socklen_t addrlen )",
        [
            _a("sockfd", _fd),
            _a("buf", _buf),
            _a("len", _size),
            _a("flags", _flags),
            _a("dest_addr", _sockaddr),
            _a("addrlen", _size),
        ],
        ReturnType.SSIZE,
        "Send a message on a socket",
        2,
    ),
    "recvfrom": _e(
        "recvfrom",
        "ssize_t recvfrom(int sockfd , void * buf , size_t len , int flags , struct sockaddr * src_addr , socklen_t * addrlen )",
        [
            _a("sockfd", _fd),
            _a("buf", _buf),
            _a("len", _size),
            _a("flags", _flags),
            _a("src_addr", _sockaddr),
            _a("addrlen", _size),
        ],
        ReturnType.SSIZE,
        "Receive a message from a socket",
        2,
    ),
    "sendmsg": _e(
        "sendmsg",
        "ssize_t sendmsg(int sockfd , const struct msghdr * msg , int flags )",
        [_a("sockfd", _fd), _a("msg", _struct_), _a("flags", _flags)],
        ReturnType.SSIZE,
        "Send a message on a socket",
        2,
    ),
    "recvmsg": _e(
        "recvmsg",
        "ssize_t recvmsg(int sockfd , struct msghdr * msg , int flags )",
        [_a("sockfd", _fd), _a("msg", _struct_), _a("flags", _flags)],
        ReturnType.SSIZE,
        "Receive a message from a socket",
        2,
    ),
    "shutdown": _e(
        "shutdown",
        "int shutdown(int sockfd , int how )",
        [_a("sockfd", _fd), _a("how", _int_)],
        ReturnType.INT,
        "Shut down part of a full-duplex connection",
        2,
    ),
    "setsockopt": _e(
        "setsockopt",
        "int setsockopt(int sockfd , int level , int optname , const void * optval , socklen_t optlen )",
        [
            _a("sockfd", _fd),
            _a("level", _int_),
            _a("optname", _int_),
            _a("optval", _ptr),
            _a("optlen", _size),
        ],
        ReturnType.INT,
        "Get and set options on sockets",
        2,
    ),
    "getsockopt": _e(
        "getsockopt",
        "int getsockopt(int sockfd , int level , int optname , void * optval , socklen_t * optlen )",
        [
            _a("sockfd", _fd),
            _a("level", _int_),
            _a("optname", _int_),
            _a("optval", _ptr),
            _a("optlen", _size),
        ],
        ReturnType.INT,
        "Get and set options on sockets",
        2,
    ),
    "getsockname": _e(
        "getsockname",
        "int getsockname(int sockfd , struct sockaddr * addr , socklen_t * addrlen )",
        [_a("sockfd", _fd), _a("addr", _sockaddr), _a("addrlen", _size)],
        ReturnType.INT,
        "Get socket name",
        2,
    ),
    "getpeername": _e(
        "getpeername",
        "int getpeername(int sockfd , struct sockaddr * addr , socklen_t * addrlen )",
        [_a("sockfd", _fd), _a("addr", _sockaddr), _a("addrlen", _size)],
        ReturnType.INT,
        "Get name of connected peer socket",
        2,
    ),
    "socketpair": _e(
        "socketpair",
        "int socketpair(int domain , int type , int protocol , int sv [2])",
        [_a("domain", _int_), _a("type", _int_), _a("protocol", _flags), _a("sv", _int_)],
        ReturnType.FILE_DESCRIPTOR,
        "Create a pair of connected sockets",
        2,
    ),
    "select": _e(
        "select",
        "int select(int nfds , fd_set * readfds , fd_set * writefds , fd_set * exceptfds , struct timeval * timeout )",
        [
            _a("nfds", _fd),
            _a("readfds", _ptr),
            _a("writefds", _ptr),
            _a("exceptfds", _ptr),
            _a("timeout", _struct_),
        ],
        ReturnType.INT,
        "Synchronous I/O multiplexing",
        2,
    ),
    "poll": _e(
        "poll",
        "int poll(struct pollfd * fds , nfds_t nfds , int timeout )",
        [_a("fds", _struct_), _a("nfds", ArgType.other_type("nfds_t")), _a("timeout", _int_)],
        ReturnType.INT,
        "Wait for some event on a file descriptor",
        2,
    ),
    "ppoll": _e(
        "ppoll",
        "int ppoll(struct pollfd * fds , nfds_t nfds , const struct timespec * tmo_p , const sigset_t * sigmask )",
        [
            _a("fds", _struct_),
            _a("nfds", ArgType.other_type("nfds_t")),
            _a("tmo_p", _struct_),
            _a("sigmask", _ptr),
        ],
        ReturnType.INT,
        "Wait for some event on a file descriptor",
        2,
    ),
    "epoll_create": _e(
        "epoll_create",
        "int epoll_create(int size )",
        [_a("size", _int_)],
        ReturnType.FILE_DESCRIPTOR,
        "Open an epoll file descriptor",
        2,
    ),
    "epoll_create1": _e(
        "epoll_create1",
        "int epoll_create1(int flags )",
        [_a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Open an epoll file descriptor",
        2,
    ),
    "epoll_ctl": _e(
        "epoll_ctl",
        "int epoll_ctl(int epfd , int op , int fd , struct epoll_event * event )",
        [_a("epfd", _fd), _a("op", _int_), _a("fd", _fd), _a("event", _struct_)],
        ReturnType.INT,
        "Control interface for an epoll file descriptor",
        2,
    ),
    "epoll_wait": _e(
        "epoll_wait",
        "int epoll_wait(int epfd , struct epoll_event * events , int maxevents , int timeout )",
        [_a("epfd", _fd), _a("events", _struct_), _a("maxevents", _int_), _a("timeout", _int_)],
        ReturnType.INT,
        "Wait for an I/O event on an epoll file descriptor",
        2,
    ),
    "epoll_pwait": _e(
        "epoll_pwait",
        "int epoll_pwait(int epfd , struct epoll_event * events , int maxevents , int timeout , const sigset_t * sigmask )",
        [
            _a("epfd", _fd),
            _a("events", _struct_),
            _a("maxevents", _int_),
            _a("timeout", _int_),
            _a("sigmask", _ptr),
        ],
        ReturnType.INT,
        "Wait for an I/O event on an epoll file descriptor",
        2,
    ),
    "pipe": _e(
        "pipe",
        "int pipe(int pipefd [2])",
        [_a("pipefd", _fd)],
        ReturnType.INT,
        "Create pipe",
        2,
    ),
    "pipe2": _e(
        "pipe2",
        "int pipe2(int pipefd [2], int flags )",
        [_a("pipefd", _fd), _a("flags", _flags)],
        ReturnType.INT,
        "Create pipe",
        2,
    ),
    "ioctl": _e(
        "ioctl",
        "int ioctl(int fd , unsigned long request , ...)",
        [_a("fd", _fd), _a("request", _uint)],
        ReturnType.INT,
        "Control device",
        2,
    ),
    "fcntl": _e(
        "fcntl",
        "int fcntl(int fd , int cmd , ... /* arg */ )",
        [_a("fd", _fd), _a("cmd", _int_)],
        ReturnType.INT,
        "Manipulate file descriptor",
        2,
    ),
    "rt_sigaction": _e(
        "rt_sigaction",
        "int sigaction(int signum , const struct sigaction * act , struct sigaction * oldact )",
        [_a("signum", _sig_), _a("act", _struct_), _a("oldact", _struct_)],
        ReturnType.INT,
        "Examine and change a signal action",
        2,
    ),
    "rt_sigprocmask": SyscallInfo(
        name="rt_sigprocmask",
        signatures=[
            Signature(
                "int sigprocmask(int how , const sigset_t * set , sigset_t * oldset )",
                [_a("how", _int_), _a("set", _ptr), _a("oldset", _ptr)],
                ReturnType.INT,
            ),
            Signature(
                "int rt_sigprocmask(int how , const kernel_sigset_t * set , kernel_sigset_t * oldset , size_t sigsetsize )",
                [_a("how", _int_), _a("set", _ptr), _a("oldset", _ptr), _a("sigsetsize", _size)],
                ReturnType.INT,
            ),
            Signature(
                "int sigprocmask(int how , const old_kernel_sigset_t * set , old_kernel_sigset_t * oldset )",
                [_a("how", _int_), _a("set", _ptr), _a("oldset", _ptr)],
                ReturnType.INT,
            ),
        ],
        brief="Examine and change blocked signals",
        man_section=2,
    ),
    "rt_sigreturn": _e(
        "rt_sigreturn",
        "int sigreturn(...)",
        [],
        ReturnType.INT,
        "Return from signal handler and cleanup stack frame",
        2,
    ),
    "sigaltstack": _e(
        "sigaltstack",
        "int sigaltstack(const stack_t * ss , stack_t * old_ss )",
        [_a("ss", _ptr), _a("old_ss", _ptr)],
        ReturnType.INT,
        "Set and/or get signal stack context",
        2,
    ),
    "arch_prctl": SyscallInfo(
        name="arch_prctl",
        signatures=[
            Signature(
                "int arch_prctl(int code , unsigned long addr )",
                [_a("code", _int_), _a("addr", _uint)],
                ReturnType.INT,
            ),
            Signature(
                "int arch_prctl(int code , unsigned long * addr )",
                [_a("code", _int_), _a("addr", _ptr)],
                ReturnType.INT,
            ),
        ],
        brief="Set architecture-specific thread state",
        man_section=2,
    ),
    "set_tid_address": _e(
        "set_tid_address",
        "long set_tid_address(int * tidptr )",
        [_a("tidptr", _ptr)],
        ReturnType.INT,
        "Set pointer to thread ID",
        2,
    ),
    "set_robust_list": _e(
        "set_robust_list",
        "long set_robust_list(struct robust_list_head * head , size_t len )",
        [_a("head", _struct_), _a("len", _size)],
        ReturnType.INT,
        "Get/set list of robust futexes",
        2,
    ),
    "futex": _e(
        "futex",
        "int futex(int * uaddr , int futex_op , int val , const struct timespec * timeout , /* or: uint32_t val2 */ int * uaddr2 , int val3 )",
        [
            _a("uaddr", _ptr),
            _a("futex_op", _int_),
            _a("val", _int_),
            _a("timeout", _struct_),
            _a("uaddr2", _ptr),
            _a("val3", _int_),
        ],
        ReturnType.INT,
        "Fast user-space locking",
        2,
    ),
    "nanosleep": _e(
        "nanosleep",
        "int nanosleep(const struct timespec * req , struct timespec * rem )",
        [_a("req", _struct_), _a("rem", _struct_)],
        ReturnType.INT,
        "High-resolution sleep",
        2,
    ),
    "clock_gettime": _e(
        "clock_gettime",
        "int clock_gettime(clockid_t clk_id , struct timespec * tp )",
        [_a("clk_id", _int_), _a("tp", _struct_)],
        ReturnType.INT,
        "Clock and time functions",
        2,
    ),
    "clock_getres": _e(
        "clock_getres",
        "int clock_getres(clockid_t clk_id , struct timespec * res )",
        [_a("clk_id", _int_), _a("res", _struct_)],
        ReturnType.INT,
        "Clock and time functions",
        2,
    ),
    "clock_nanosleep": _e(
        "clock_nanosleep",
        "int clock_nanosleep(clockid_t clock_id , int flags , const struct timespec * request , struct timespec * remain )",
        [
            _a("clock_id", _int_),
            _a("flags", _flags),
            _a("request", _struct_),
            _a("remain", _struct_),
        ],
        ReturnType.INT,
        "High-resolution sleep with specifiable clock",
        2,
    ),
    "gettimeofday": _e(
        "gettimeofday",
        "int gettimeofday(struct timeval * tv , struct timezone * tz )",
        [_a("tv", _struct_), _a("tz", _struct_)],
        ReturnType.INT,
        "Get / set time",
        2,
    ),
    "getrlimit": _e(
        "getrlimit",
        "int getrlimit(int resource , struct rlimit * rlim )",
        [_a("resource", _int_), _a("rlim", _struct_)],
        ReturnType.INT,
        "Get/set resource limits",
        2,
    ),
    "prlimit64": _e(
        "prlimit64",
        "int prlimit(pid_t pid , int resource , const struct rlimit * new_limit , struct rlimit * old_limit )",
        [
            _a("pid", _pid),
            _a("resource", _int_),
            _a("new_limit", _struct_),
            _a("old_limit", _struct_),
        ],
        ReturnType.INT,
        "Get/set resource limits",
        2,
    ),
    "getdents64": _e(
        "getdents64",
        "int getdents64(unsigned int fd , struct linux_dirent64 * dirp , unsigned int count )",
        [_a("fd", _fd), _a("dirp", _struct_), _a("count", _size)],
        ReturnType.INT,
        "Get directory entries",
        2,
    ),
    "statfs": _e(
        "statfs",
        "int statfs(const char * path , struct statfs * buf )",
        [_a("path", _path), _a("buf", _struct_)],
        ReturnType.INT,
        "Get filesystem statistics",
        2,
    ),
    "fstatfs": _e(
        "fstatfs",
        "int fstatfs(int fd , struct statfs * buf )",
        [_a("fd", _fd), _a("buf", _struct_)],
        ReturnType.INT,
        "Get filesystem statistics",
        2,
    ),
    "statx": _e(
        "statx",
        "int statx(int dirfd , const char * pathname , int flags , unsigned int mask , struct statx * statxbuf )",
        [
            _a("dirfd", _fd),
            _a("pathname", _path),
            _a("flags", _flags),
            _a("mask", _uint),
            _a("statxbuf", _struct_),
        ],
        ReturnType.INT,
        "Get file status (extended)",
        2,
    ),
    "sendfile": _e(
        "sendfile",
        "ssize_t sendfile(int out_fd , int in_fd , off_t * offset , size_t count )",
        [_a("out_fd", _fd), _a("in_fd", _fd), _a("offset", _off), _a("count", _size)],
        ReturnType.SSIZE,
        "Transfer data between file descriptors",
        2,
    ),
    "eventfd2": _e(
        "eventfd2",
        "int eventfd(unsigned int initval , int flags )",
        [_a("initval", _uint), _a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Create a file descriptor for event notification",
        2,
    ),
    "timerfd_create": _e(
        "timerfd_create",
        "int timerfd_create(int clockid , int flags )",
        [_a("clockid", _int_), _a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Timers that notify via file descriptors",
        2,
    ),
    "timerfd_settime": _e(
        "timerfd_settime",
        "int timerfd_settime(int fd , int flags , const struct itimerspec * new_value , struct itimerspec * old_value )",
        [
            _a("fd", _fd),
            _a("flags", _flags),
            _a("new_value", _struct_),
            _a("old_value", _struct_),
        ],
        ReturnType.INT,
        "Timers that notify via file descriptors",
        2,
    ),
    "timerfd_gettime": _e(
        "timerfd_gettime",
        "int timerfd_gettime(int fd , struct itimerspec * curr_value )",
        [_a("fd", _fd), _a("curr_value", _struct_)],
        ReturnType.INT,
        "Timers that notify via file descriptors",
        2,
    ),
    "signalfd4": _e(
        "signalfd4",
        "int signalfd(int fd , const sigset_t * mask , int flags )",
        [_a("fd", _fd), _a("mask", _ptr), _a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Create a file descriptor for accepting signals",
        2,
    ),
    "inotify_init1": _e(
        "inotify_init1",
        "int inotify_init1(int flags )",
        [_a("flags", _flags)],
        ReturnType.FILE_DESCRIPTOR,
        "Initialize an inotify instance",
        2,
    ),
    "inotify_add_watch": _e(
        "inotify_add_watch",
        "int inotify_add_watch(int fd , const char * pathname , uint32_t mask )",
        [_a("fd", _fd), _a("pathname", _path), _a("mask", _int_)],
        ReturnType.INT,
        "Add a watch to an initialized inotify instance",
        2,
    ),
    "inotify_rm_watch": _e(
        "inotify_rm_watch",
        "int inotify_rm_watch(int fd , int wd )",
        [_a("fd", _fd), _a("wd", _int_)],
        ReturnType.INT,
        "Remove an existing watch from an inotify instance",
        2,
    ),
    "prctl": _e(
        "prctl",
        "int prctl(int option , unsigned long arg2 , unsigned long arg3 , unsigned long arg4 , unsigned long arg5 )",
        [
            _a("option", _int_),
            _a("arg2", _uint),
            _a("arg3", _uint),
            _a("arg4", _uint),
            _a("arg5", _uint),
        ],
        ReturnType.INT,
        "Operations on a process",
        2,
    ),
    "sysinfo": _e(
        "sysinfo",
        "int sysinfo(struct sysinfo * info )",
        [_a("info", _struct_)],
        ReturnType.INT,
        "Return system information",
        2,
    ),
    "uname": _e(
        "uname",
        "int uname(struct utsname * buf )",
        [_a("buf", _struct_)],
        ReturnType.INT,
        "Get name and information about current kernel",
        2,
    ),
    "getrandom": _e(
        "getrandom",
        "ssize_t getrandom(void *buf , size_t buflen , unsigned int flags )",
        [_a("buf", _ptr), _a("buflen", _size), _a("flags", _flags)],
        ReturnType.SSIZE,
        "Obtain a series of random bytes",
        2,
    ),
}


def lookup(name: str) -> "SyscallInfo | None":
    """Return the SyscallInfo for *name*, or None if not known."""
    return KNOWN_SYSCALLS.get(name)
