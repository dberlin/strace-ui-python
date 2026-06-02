"""filter: faithful Python port of OCaml syscall_filter.ml — Task 12.

Provides a filter expression type (list[Term]) with parsing and serialisation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

from strace_ui.schema import Family
from strace_ui.fd_tracker import FdTracker, FdId


# ---------------------------------------------------------------------------
# Term types — all frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncludeFamily:
    """Include syscalls belonging to a Family."""
    family: Family


@dataclass(frozen=True)
class IncludeSyscall:
    """Explicitly include a syscall by name."""
    name: str


@dataclass(frozen=True)
class ExcludeSyscall:
    """Explicitly exclude a syscall by name."""
    name: str


@dataclass(frozen=True)
class FilterPid:
    """Only pass events from this PID."""
    pid: int


@dataclass(frozen=True)
class ExcludePid:
    """Exclude events from this PID."""
    pid: int


@dataclass(frozen=True)
class FilterFd:
    """Only pass events that touch a specific fd (optionally with generation).

    Field order: (fd_number, generation) — positional construction works.
    """
    fd_number: int
    generation: Optional[int]


@dataclass(frozen=True)
class FilterRelatedPid:
    """Only pass events from PIDs related (via fork ancestry) to this PID."""
    pid: int


class Regex:
    """Filter term that applies a regex search against the raw line.

    Two Regex instances with the same source pattern string compare equal.
    """

    __slots__ = ("_pattern",)

    def __init__(self, pattern: "re.Pattern[str]") -> None:
        self._pattern = pattern

    @property
    def pattern(self) -> str:
        """Return the source pattern string."""
        return self._pattern.pattern

    def matches(self, s: str) -> bool:
        """Return True if the pattern matches anywhere in *s* (unanchored search)."""
        return bool(self._pattern.search(s))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Regex):
            return self._pattern.pattern == other._pattern.pattern
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._pattern.pattern)

    def __repr__(self) -> str:
        return f"Regex({self._pattern.pattern!r})"


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Term = Union[IncludeFamily, IncludeSyscall, ExcludeSyscall, FilterPid, ExcludePid,
             FilterFd, FilterRelatedPid, Regex]

# ---------------------------------------------------------------------------
# empty / is_empty
# ---------------------------------------------------------------------------

empty: list[Term] = []


def is_empty(t: list[Term]) -> bool:
    return len(t) == 0


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def to_normalized_string(terms: list[Term]) -> str:
    """Serialise a filter term list to a canonical string (no leading/trailing space)."""
    parts: list[str] = []
    for term in terms:
        if isinstance(term, IncludeFamily):
            parts.append(term.family.to_display_string())
        elif isinstance(term, IncludeSyscall):
            parts.append(term.name)
        elif isinstance(term, ExcludeSyscall):
            parts.append(f"-{term.name}")
        elif isinstance(term, FilterPid):
            parts.append(f"pid:{term.pid}")
        elif isinstance(term, ExcludePid):
            parts.append(f"!pid:{term.pid}")
        elif isinstance(term, FilterFd):
            if term.generation is None:
                parts.append(f"fd:{term.fd_number}")
            else:
                parts.append(f"fd:{term.fd_number}.{term.generation}")
        elif isinstance(term, FilterRelatedPid):
            parts.append(f"rel:{term.pid}")
        elif isinstance(term, Regex):
            # Escape literal '/' inside the pattern as '\/'
            escaped = term.pattern.replace("/", "\\/")
            parts.append(f"/{escaped}/")
        else:
            raise TypeError(f"Unknown term type: {type(term)}")
    return " ".join(parts)


def to_display_string(terms: list[Term]) -> str:
    """Return "all" for an empty filter, otherwise the normalised string."""
    if is_empty(terms):
        return "all"
    return to_normalized_string(terms)


def normalize(s: str) -> str:
    """Parse *s* and re-serialise to a canonical string."""
    return to_normalized_string(parse(s))


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_simple_token(token: str) -> Term:
    """Parse a single non-regex token (no slashes) into a Term."""
    token = token.strip()

    if token.startswith("!pid:"):
        num_str = token[len("!pid:"):]
        try:
            return ExcludePid(int(num_str))
        except ValueError:
            return IncludeSyscall(token)

    if token.startswith("pid:"):
        num_str = token[len("pid:"):]
        try:
            return FilterPid(int(num_str))
        except ValueError:
            return IncludeSyscall(token)

    if token.startswith("rel:"):
        num_str = token[len("rel:"):]
        try:
            return FilterRelatedPid(int(num_str))
        except ValueError:
            return IncludeSyscall(token)

    if token.startswith("fd:"):
        fd_str = token[len("fd:"):]
        dot_pos = fd_str.find(".")
        if dot_pos != -1:
            num_str = fd_str[:dot_pos]
            gen_str = fd_str[dot_pos + 1:]
            try:
                fd_number = int(num_str)
                generation = int(gen_str)
                return FilterFd(fd_number, generation)
            except ValueError:
                return IncludeSyscall(token)
        else:
            try:
                return FilterFd(int(fd_str), None)
            except ValueError:
                return IncludeSyscall(token)

    if token.startswith("%"):
        for f in Family:
            if f.to_display_string() == token:
                return IncludeFamily(f)
        return IncludeSyscall(token)

    if token.startswith("-") or token.startswith("!"):
        return ExcludeSyscall(token[1:])

    if token.startswith("+"):
        return IncludeSyscall(token[1:])

    return IncludeSyscall(token)


def parse_regex_body(body: str) -> str:
    """Process escape sequences inside a regex token body.

    ``\\/`` → literal ``/``; ``\\x`` (any other x) → ``\\x`` (keep backslash).
    """
    buf: list[str] = []
    i = 0
    length = len(body)
    while i < length:
        c = body[i]
        if c == "\\" and i + 1 < length:
            nxt = body[i + 1]
            if nxt == "/":
                buf.append("/")
                i += 2
            else:
                buf.append("\\")
                i += 1
        else:
            buf.append(c)
            i += 1
    return "".join(buf)


def make_regex_term(pattern: str) -> Optional[Regex]:
    """Compile *pattern* into a Regex term; return None for empty patterns."""
    if not pattern:
        return None
    try:
        compiled = re.compile(pattern)
    except re.error:
        compiled = re.compile(re.escape(pattern))
    return Regex(compiled)


def tokenize(s: str) -> list[tuple[str, str]]:
    """Tokenize a filter string into a list of ('plain', token) / ('regex', body) pairs.

    Regex tokens are delimited by ``/…/`` (where the closing ``/`` must not be
    preceded by a backslash).  Everything else is split on spaces.
    """
    length = len(s)
    tokens: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0

    def flush_plain() -> None:
        content = "".join(buf)
        buf.clear()
        for tok in content.split(" "):
            tok = tok.strip()
            if tok:
                tokens.append(("plain", tok))

    while i < length:
        c = s[i]
        if c == "/":
            flush_plain()
            # Scan for the closing slash (not preceded by backslash)
            j = i + 1
            while j < length:
                if s[j] == "/" and (j == 0 or s[j - 1] != "\\"):
                    break
                j += 1
            body = s[i + 1:j]
            tokens.append(("regex", body))
            if j < length:
                i = j + 1
            else:
                i = j
        else:
            buf.append(c)
            i += 1

    flush_plain()
    return tokens


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


def parse(s: str) -> list[Term]:
    """Parse a filter expression string into a list of Terms."""
    s = s.strip()
    if not s:
        return []
    terms: list[Term] = []
    for kind, value in tokenize(s):
        if kind == "plain":
            terms.append(parse_simple_token(value))
        else:  # 'regex'
            pattern = parse_regex_body(value)
            term = make_regex_term(pattern)
            if term is not None:
                terms.append(term)
    return terms


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def add_exclusion(t: list[Term], syscall_name: str) -> list[Term]:
    return t + [ExcludeSyscall(syscall_name)]


def add_inclusion(t: list[Term], syscall_name: str) -> list[Term]:
    return t + [IncludeSyscall(syscall_name)]


def add_pid_filter(t: list[Term], pid: int) -> list[Term]:
    return t + [FilterPid(pid)]


def add_pid_exclusion(t: list[Term], pid: int) -> list[Term]:
    return t + [ExcludePid(pid)]


# ---------------------------------------------------------------------------
# SyscallInfo (for passes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyscallInfo:
    """Input record for filter evaluation."""
    syscall_name: str
    pid: int
    fd_ids: list[FdId]
    raw_line: str


# ---------------------------------------------------------------------------
# passes — ancestry helpers + main evaluator
# ---------------------------------------------------------------------------


def is_ancestor(fd_tracker: "FdTracker", *, pid: int, target: int) -> bool:
    """Return True if *pid* is an ancestor of *target* in the fork tree.

    Walks from *target* upward through parent_pid links.  Stops at *pid*
    (True) or when there is no more parent (False).  A visited set prevents
    infinite loops.
    """
    visited: set[int] = set()

    def walk(current: int) -> bool:
        if current == pid:
            return True
        if current in visited:
            return False
        visited.add(current)
        parent = fd_tracker.parent_pid(pid=current)
        if parent is not None:
            return walk(parent)
        return False

    return walk(target)


def is_related(fd_tracker: "FdTracker", *, pid: int, target: int) -> bool:
    """Return True if *pid* and *target* are the same process or related by ancestry."""
    return (
        pid == target
        or is_ancestor(fd_tracker, pid=pid, target=target)
        or is_ancestor(fd_tracker, pid=target, target=pid)
    )


def passes(terms: list[Term], info: "SyscallInfo", *, fd_tracker: "FdTracker") -> bool:
    """Evaluate whether *info* passes the filter described by *terms*.

    Rules (port of OCaml lines 264-333):
    - Empty filter  → always True.
    - No inclusions → everything passes unless explicitly excluded.
    - Inclusions    → only included names/families pass.
    - Exclusions, pid/fd/regex constraints are applied on top.
    """
    if is_empty(terms):
        return True

    syscall_name = info.syscall_name
    pid = info.pid
    fd_ids = info.fd_ids
    raw_line = info.raw_line

    # Determine whether any inclusion terms are present
    has_inclusions = any(
        isinstance(term, (IncludeFamily, IncludeSyscall)) for term in terms
    )

    # Inclusion check
    if has_inclusions:
        included = any(
            (isinstance(term, IncludeFamily) and term.family.includes(syscall_name))
            or (isinstance(term, IncludeSyscall) and term.name == syscall_name)
            for term in terms
        )
    else:
        included = True

    # Exclusion check
    excluded = any(
        isinstance(term, ExcludeSyscall) and term.name == syscall_name
        for term in terms
    )

    # PID constraints: every FilterPid / ExcludePid / FilterRelatedPid must pass
    pid_ok = all(
        (not isinstance(term, FilterPid) or term.pid == pid)
        and (not isinstance(term, ExcludePid) or term.pid != pid)
        and (not isinstance(term, FilterRelatedPid) or is_related(fd_tracker, pid=pid, target=term.pid))
        for term in terms
    )

    # FD constraints: every FilterFd term must have a matching fd_id in info.fd_ids
    fd_ok = all(
        not isinstance(term, FilterFd)
        or any(
            fid.fd_number == term.fd_number
            and (term.generation is None or fid.generation == term.generation)
            for fid in fd_ids
        )
        for term in terms
    )

    # Regex constraints: every Regex term must match the raw line
    regex_ok = all(
        not isinstance(term, Regex) or term.matches(raw_line)
        for term in terms
    )

    return included and not excluded and pid_ok and fd_ok and regex_ok
