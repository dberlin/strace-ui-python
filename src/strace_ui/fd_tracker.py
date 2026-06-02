"""fd_tracker: faithful Python port of OCaml fd_tracker.ml

Tracks file-descriptor lifetimes across a parsed strace log, assigning a
stable FdId to each (pid, fd_number, generation) incarnation and recording
the origin syscall.  Immutable-style: every update returns a new FdTracker.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from strace_ui import parser


# ---------------------------------------------------------------------------
# FdId
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, order=True)
class FdId:
    """Unique identity for one incarnation of a file descriptor.

    Two processes sharing an inherited fd have the *same* FdId.
    After close+reopen the generation counter increments, yielding a new FdId.

    Field order: source_pid, fd_number, generation  (positional construction OK).
    """
    source_pid: int
    fd_number: int
    generation: int


# ---------------------------------------------------------------------------
# FdOrigin
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class FdOrigin:
    """Origin information for a single FdId incarnation."""
    syscall_index: int
    syscall_name: str
    summary: str


# ---------------------------------------------------------------------------
# Constants (frozensets, from OCaml)
# ---------------------------------------------------------------------------

fd_creating_syscalls: frozenset[str] = frozenset({
    "open",
    "openat",
    "socket",
    "accept",
    "accept4",
    "dup",
    "dup2",
    "dup3",
    "epoll_create",
    "epoll_create1",
    "eventfd2",
    "timerfd_create",
    "signalfd4",
    "inotify_init1",
})

fd_pair_syscalls: frozenset[str] = frozenset({"pipe", "pipe2", "socketpair"})

fd_closing_syscalls: frozenset[str] = frozenset({"close"})

fork_syscalls: frozenset[str] = frozenset({"clone", "clone3", "fork", "vfork"})


# ---------------------------------------------------------------------------
# extract_fd_pair
# ---------------------------------------------------------------------------

def extract_fd_pair(args_raw: str) -> list[int]:
    """Extract fd numbers from bracket notation like '[3, 4]' in args_raw.

    Port of OCaml lines 88-113: find the FIRST '[', then scan for the
    matching ']' using bracket depth, split the contents on ',' and run
    extract_fd_number on each stripped element.
    """
    bracket_idx = args_raw.find("[")
    if bracket_idx == -1:
        return []
    rest = args_raw[bracket_idx + 1:]

    # Find matching ']' by bracket depth
    depth = 0
    close_pos: Optional[int] = None
    for i, ch in enumerate(rest):
        if ch == "[":
            depth += 1
        elif ch == "]":
            if depth == 0:
                close_pos = i
                break
            depth -= 1

    if close_pos is None:
        return []

    inside = rest[:close_pos]
    result: list[int] = []
    for part in inside.split(","):
        fd_num = parser.extract_fd_number(part.strip())
        if fd_num is not None:
            result.append(fd_num)
    return result


# ---------------------------------------------------------------------------
# FdTracker
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FdTracker:
    """Immutable-style tracker for file-descriptor lifetimes.

    All mutating operations return a *new* FdTracker, leaving the original
    unchanged (value semantics for chained updates in tests).

    Attributes:
        fd_tables: pid → fd_number → FdId  (current live fds per process)
        generation_counters: (pid, fd_number) → int  (next generation value
            after all closes seen so far)
        origins: FdId → FdOrigin  (permanent; never removed)
        parent_pid_map: child_pid → parent_pid
    """

    fd_tables: dict[int, dict[int, FdId]]
    generation_counters: dict[tuple[int, int], int]
    origins: dict[FdId, FdOrigin]
    parent_pid_map: dict[int, int]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls) -> "FdTracker":
        return cls(
            fd_tables={},
            generation_counters={},
            origins={},
            parent_pid_map={},
        )

    # ------------------------------------------------------------------
    # Internal helpers (return copies — do not mutate self)
    # ------------------------------------------------------------------

    def _get_fd_table(self, pid: int) -> dict[int, FdId]:
        """Return the fd table for pid (empty dict if unknown)."""
        return self.fd_tables.get(pid, {})

    def _with_fd_set(self, pid: int, fd_number: int, fd_id: FdId) -> "FdTracker":
        """Return a new tracker with fd_tables[pid][fd_number] = fd_id."""
        new_table = dict(self._get_fd_table(pid))
        new_table[fd_number] = fd_id
        new_fd_tables = dict(self.fd_tables)
        new_fd_tables[pid] = new_table
        return dataclasses.replace(self, fd_tables=new_fd_tables)

    def _with_fd_removed(self, pid: int, fd_number: int) -> "FdTracker":
        """Return a new tracker with fd_tables[pid][fd_number] removed."""
        new_table = dict(self._get_fd_table(pid))
        new_table.pop(fd_number, None)
        new_fd_tables = dict(self.fd_tables)
        new_fd_tables[pid] = new_table
        return dataclasses.replace(self, fd_tables=new_fd_tables)

    def _bump_generation(self, pid: int, fd_number: int) -> "FdTracker":
        """Return a new tracker with generation_counters[(pid,fd_number)] += 1."""
        key = (pid, fd_number)
        current = self.generation_counters.get(key, 0)
        new_counters = dict(self.generation_counters)
        new_counters[key] = current + 1
        return dataclasses.replace(self, generation_counters=new_counters)

    def _current_generation(self, pid: int, fd_number: int) -> int:
        """Return current generation counter value (default 0)."""
        return self.generation_counters.get((pid, fd_number), 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, line: parser.ParsedLine) -> "FdTracker":
        """Return a new FdTracker reflecting the syscall in *line*.

        Port of OCaml lines 136-270.  Only successful (ValueResult) syscalls
        mutate state; all other result variants return self unchanged.
        """
        result = line.result
        # Only process successful syscalls (OCaml: match result with Value _ ->)
        if not isinstance(result, parser.ValueResult):
            return self

        pid = line.pid
        syscall_name = line.syscall_name
        args_raw = line.args_raw
        index = line.index

        # ---- fd-creating syscalls ----------------------------------------
        if syscall_name in fd_creating_syscalls:
            return_fd = parser.extract_return_int(result)
            if return_fd is None or return_fd < 0:
                return self

            args = parser.split_args(args_raw)
            # Build summary string (port lines 156-167)
            if syscall_name in ("open", "openat"):
                path = next(
                    (a for a in args if a.strip().startswith('"')),
                    "<unknown>",
                )
                summary = f"{syscall_name}({path})"
            elif syscall_name in ("dup", "dup2", "dup3"):
                summary = f"{syscall_name}({args_raw}) = {return_fd}"
            else:
                summary = f"{syscall_name}({args_raw})"

            # Implicit close: if slot already occupied, bump generation first
            t: FdTracker = self
            if return_fd in t._get_fd_table(pid):
                t = t._bump_generation(pid, return_fd)

            generation = t._current_generation(pid, return_fd)
            fd_id = FdId(source_pid=pid, fd_number=return_fd, generation=generation)
            origin = FdOrigin(syscall_index=index, syscall_name=syscall_name, summary=summary)

            t = t._with_fd_set(pid, return_fd, fd_id)
            new_origins = dict(t.origins)
            new_origins[fd_id] = origin
            return dataclasses.replace(t, origins=new_origins)

        # ---- fd-pair syscalls (pipe/pipe2/socketpair) --------------------
        elif syscall_name in fd_pair_syscalls:
            if parser.extract_return_int(result) != 0:
                return self

            fds = extract_fd_pair(args_raw)
            t = self
            for fd_number in fds:
                # Implicit close if slot occupied
                if fd_number in t._get_fd_table(pid):
                    t = t._bump_generation(pid, fd_number)

                generation = t._current_generation(pid, fd_number)
                fd_id = FdId(source_pid=pid, fd_number=fd_number, generation=generation)
                summary = f"{syscall_name}({args_raw})"
                origin = FdOrigin(syscall_index=index, syscall_name=syscall_name, summary=summary)

                t = t._with_fd_set(pid, fd_number, fd_id)
                new_origins = dict(t.origins)
                new_origins[fd_id] = origin
                t = dataclasses.replace(t, origins=new_origins)
            return t

        # ---- fork syscalls (clone/clone3/fork/vfork) ---------------------
        elif syscall_name in fork_syscalls:
            child = parser.extract_return_int(result)
            if child is None or child <= 0:
                return self

            parent_table = self._get_fd_table(pid)
            # Copy parent fd table to child
            new_fd_tables = dict(self.fd_tables)
            new_fd_tables[child] = dict(parent_table)

            # Record parent-child relationship
            new_parent_map = dict(self.parent_pid_map)
            new_parent_map[child] = pid

            t = dataclasses.replace(
                self,
                fd_tables=new_fd_tables,
                parent_pid_map=new_parent_map,
            )

            # Inherit parent's generation counters into child
            # (port lines 236-248: fold over generation_counters, copy pid→child)
            new_counters = dict(t.generation_counters)
            for (counter_pid, fd_number), counter_val in self.generation_counters.items():
                if counter_pid == pid:
                    new_counters[(child, fd_number)] = counter_val
            return dataclasses.replace(t, generation_counters=new_counters)

        # ---- fd-closing syscalls -----------------------------------------
        elif syscall_name in fd_closing_syscalls:
            args = parser.split_args(args_raw)
            if not args:
                return self
            fd_num = parser.extract_fd_number(args[0])
            if fd_num is None:
                return self

            t = self._with_fd_removed(pid, fd_num)
            return t._bump_generation(pid, fd_num)

        # ---- unrecognised syscall ----------------------------------------
        else:
            return self

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def resolve_fd(self, pid: int = None, fd_number: int = None, **kw) -> Optional[FdId]:
        """Return the current FdId at (pid, fd_number), or None if not open.

        Accepts both positional (pid, fd_number) and keyword-only forms.
        """
        if pid is None:
            pid = kw["pid"]
        if fd_number is None:
            fd_number = kw["fd_number"]
        return self._get_fd_table(pid).get(fd_number)

    def resolve_fd_or_default(self, pid: int = None, fd_number: int = None, **kw) -> Optional[FdId]:
        """Return the FdId for (pid, fd_number), synthesising gen-0 for pre-trace fds.

        Port of OCaml lines 281-289:
        - If currently open → that FdId.
        - Elif generation_counter entry exists → None (was tracked, now closed).
        - Else → synthesise FdId(pid, fd_number, 0) (fd existed before tracing).
        """
        if pid is None:
            pid = kw["pid"]
        if fd_number is None:
            fd_number = kw["fd_number"]
        fd_id = self.resolve_fd(pid=pid, fd_number=fd_number)
        if fd_id is not None:
            return fd_id
        key = (pid, fd_number)
        if key in self.generation_counters:
            return None
        return FdId(source_pid=pid, fd_number=fd_number, generation=0)

    def lookup_origin(self, fd_id: FdId) -> Optional[FdOrigin]:
        """Return the origin of an fd by its FdId, or None."""
        return self.origins.get(fd_id)

    def parent_pid(self, *, pid: int) -> Optional[int]:
        """Return the parent PID of *pid* if known from clone/fork/vfork."""
        return self.parent_pid_map.get(pid)

    def lookup(self, *, pid: int, fd_number: int) -> Optional[FdOrigin]:
        """Return the origin of the currently open fd at (pid, fd_number).

        Port of OCaml lines 299-303.  Returns None if the fd is not open.
        """
        fd_id = self.resolve_fd(pid=pid, fd_number=fd_number)
        if fd_id is None:
            return None
        return self.lookup_origin(fd_id)
