"""parser: faithful Python port of OCaml strace_parser.ml"""

from __future__ import annotations

import dataclasses
import re
from typing import Union

from strace_ui.display_utils import split_top_level


# ---------------------------------------------------------------------------
# Result union types
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ValueResult:
    value: str


@dataclasses.dataclass(frozen=True)
class ErrorResult:
    errno: str
    description: str


@dataclasses.dataclass(frozen=True)
class Unfinished:
    pass


@dataclasses.dataclass(frozen=True)
class Resumed:
    inner: "Result"


@dataclasses.dataclass(frozen=True)
class Signal:
    text: str


@dataclasses.dataclass(frozen=True)
class Exit:
    text: str


Result = Union[ValueResult, ErrorResult, Unfinished, Resumed, Signal, Exit]


# ---------------------------------------------------------------------------
# ParsedLine
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ParsedLine:
    index: int
    pid: int
    timestamp: float
    syscall_name: str
    args_raw: str
    result: Result
    duration: float | None
    raw_line: str


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def split_args(raw: str) -> list[str]:
    """Split comma-separated args at the top level (respecting brackets/strings)."""
    if not raw.strip():
        return []
    return [part.strip() for part in split_top_level(raw, ",")]


def _safe_int(s: str) -> int | None:
    """Parse s as a decimal integer, returning None on failure."""
    try:
        return int(s)
    except (ValueError, OverflowError):
        return None


def extract_fd_number(arg_str: str) -> int | None:
    """Return the integer fd from an arg like '3</path/to/file>' or '3'.

    Returns None for AT_FDCWD or non-integer args.
    """
    s = arg_str.strip()
    if "<" in s:
        num_str, _ = s.split("<", 1)
        return _safe_int(num_str.strip())
    if s.startswith("AT_FDCWD"):
        return None
    return _safe_int(s)


def extract_return_int(result: Result) -> int | None:
    """Extract the integer return value from a ValueResult.

    Handles plain integers, hex (0x…), fd-annotated values (N<…>),
    and values with trailing text (N space rest).
    Returns None for non-ValueResult inputs.
    """
    if not isinstance(result, ValueResult):
        return None
    s = result.value.strip()
    if "<" in s:
        num_str, _ = s.split("<", 1)
        return _safe_int(num_str.strip())
    if s.startswith("0x"):
        try:
            return int(s, 16)
        except (ValueError, OverflowError):
            return None
    if " " in s:
        num_str, _ = s.split(" ", 1)
        return _safe_int(num_str.strip())
    return _safe_int(s)


# ---------------------------------------------------------------------------
# Parsing internals
# ---------------------------------------------------------------------------

# Matches: <pid> <timestamp> <rest>
_PREFIX_RE = re.compile(r"^(\d+)\s+(\d+\.\d+)\s+(.*)", re.DOTALL)

# Matches an error result: "= -1 ERRNO (description)"
_ERROR_RE = re.compile(
    r"^= -1 ([A-Z0-9]+)\s+\(([^)]*)\)(.*)",
    re.DOTALL,
)

_UNFINISHED_SUFFIX = "<unfinished ...>"


def _extract_duration_from_value(s: str) -> tuple[str, float | None]:
    """Strip a trailing <duration> from a value string.

    Returns (value_without_duration, duration_or_None).
    OCaml: rsplit on '<', check suffix '>'.
    """
    s = s.rstrip()
    idx = s.rfind("<")
    if idx == -1:
        return s, None
    before = s[:idx]
    after = s[idx + 1:]
    if after.endswith(">"):
        dur_str = after[:-1].strip()
        try:
            d = float(dur_str)
            return before.rstrip(), d
        except ValueError:
            pass
    return s, None


def _result_and_duration(s: str) -> tuple[Result, float | None]:
    """Parse 'result_and_duration' from a string that follows the closing paren.

    Handles:
    - '<unfinished ...>'
    - '= -1 ERRNO (desc) [<dur>]'
    - '= VALUE [<dur>]'
    """
    stripped = s.strip()

    if stripped.startswith(_UNFINISHED_SUFFIX):
        return Unfinished(), None

    m = _ERROR_RE.match(stripped)
    if m:
        errno = m.group(1)
        description = m.group(2)
        rest = m.group(3)
        _, dur = _extract_duration_from_value(rest)
        return ErrorResult(errno, description), dur

    if stripped.startswith("= "):
        value_raw = stripped[2:]  # everything after "= "
        value_str, dur = _extract_duration_from_value(value_raw)
        return ValueResult(value_str.strip()), dur

    # Fallback: treat the whole thing as a bare value
    value_str, dur = _extract_duration_from_value(stripped)
    return ValueResult(value_str.strip()), dur


def _find_matching_close_paren(rest: str) -> tuple[str, int]:
    """Scan `rest` for the depth-0 closing ')'.

    Only paren depth is tracked; quoted strings (with backslash escapes)
    are skipped.  Brace/bracket depth is NOT tracked (per OCaml source).

    Returns (inside_str, index_after_close).
    """
    depth = 0
    i = 0
    n = len(rest)
    buf: list[str] = []

    while i < n:
        c = rest[i]
        if c == '"':
            # consume quoted string
            buf.append(c)
            i += 1
            while i < n:
                qc = rest[i]
                buf.append(qc)
                i += 1
                if qc == "\\":
                    # escape: consume next char unconditionally
                    if i < n:
                        buf.append(rest[i])
                        i += 1
                elif qc == '"':
                    break
        elif c == "(":
            depth += 1
            buf.append(c)
            i += 1
        elif c == ")":
            if depth == 0:
                # This is the matching close paren
                return "".join(buf), i + 1
            depth -= 1
            buf.append(c)
            i += 1
        else:
            buf.append(c)
            i += 1

    # No matching close paren found — return everything
    return "".join(buf), n


# ---------------------------------------------------------------------------
# parse_line
# ---------------------------------------------------------------------------

def parse_line(index: int, raw: str) -> ParsedLine | None:
    """Parse one strace output line into a ParsedLine, or return None."""
    line = raw.lstrip()

    m = _PREFIX_RE.match(line)
    if not m:
        return None

    pid = int(m.group(1))
    timestamp = float(m.group(2))
    remainder = m.group(3)

    # --- Signal line ---
    if remainder.startswith("---"):
        return ParsedLine(
            index=index,
            pid=pid,
            timestamp=timestamp,
            syscall_name="<<signal>>",
            args_raw="",
            result=Signal(remainder),
            duration=None,
            raw_line=line,
        )

    # --- Exit line ---
    if remainder.startswith("+++"):
        return ParsedLine(
            index=index,
            pid=pid,
            timestamp=timestamp,
            syscall_name="<<exit>>",
            args_raw="",
            result=Exit(remainder),
            duration=None,
            raw_line=line,
        )

    # --- Resumed line: '<... name resumed>...' ---
    if remainder.startswith("<... "):
        after_prefix = remainder[5:]  # strip '<... '
        # find the name (up to whitespace)
        ws_idx = 0
        while ws_idx < len(after_prefix) and not after_prefix[ws_idx].isspace():
            ws_idx += 1
        name = after_prefix[:ws_idx]
        tail = after_prefix[ws_idx:].lstrip()
        # expect 'resumed>'
        if not tail.startswith("resumed>"):
            return None
        after_gt = tail[len("resumed>"):]

        # split on first ') = '
        sep = ") = "
        sep_idx = after_gt.find(sep)
        if sep_idx != -1:
            trailing_args = after_gt[:sep_idx].strip()
            result_part = after_gt[sep_idx + 2:].lstrip()  # skip ')' + ' '
        else:
            # No ') = ' found — chop trailing ')'
            trailing_args = after_gt.rstrip()
            if trailing_args.endswith(")"):
                trailing_args = trailing_args[:-1].rstrip()
            trailing_args = trailing_args.strip()
            result_part = ""

        inner_result, dur = _result_and_duration(result_part) if result_part else (ValueResult(""), None)
        return ParsedLine(
            index=index,
            pid=pid,
            timestamp=timestamp,
            syscall_name=name,
            args_raw=trailing_args,
            result=Resumed(inner_result),
            duration=dur,
            raw_line=line,
        )

    # --- Normal syscall: name(args) = result ---
    paren_idx = remainder.find("(")
    if paren_idx == -1:
        return None

    name = remainder[:paren_idx].strip()
    rest = remainder[paren_idx + 1:]  # everything after '('

    # Check for unfinished
    if rest.rstrip().endswith(_UNFINISHED_SUFFIX):
        # args_raw is everything before the unfinished suffix, rstripped
        args_raw = rest.rstrip()[: -len(_UNFINISHED_SUFFIX)].rstrip()
        return ParsedLine(
            index=index,
            pid=pid,
            timestamp=timestamp,
            syscall_name=name,
            args_raw=args_raw,
            result=Unfinished(),
            duration=None,
            raw_line=line,
        )

    # Find matching close paren
    args_raw, idx_after_close = _find_matching_close_paren(rest)
    after_close = rest[idx_after_close:].lstrip()

    result, dur = _result_and_duration(after_close)

    return ParsedLine(
        index=index,
        pid=pid,
        timestamp=timestamp,
        syscall_name=name,
        args_raw=args_raw,
        result=result,
        duration=dur,
        raw_line=line,
    )


# ---------------------------------------------------------------------------
# merge_resumed
# ---------------------------------------------------------------------------

def merge_resumed(original: ParsedLine, resumed: ParsedLine) -> ParsedLine:
    """Merge an unfinished line with its resumed counterpart.

    Port of OCaml lines 243-266.
    """
    left = original.args_raw.rstrip()
    right = resumed.args_raw.lstrip()

    if not left:
        args_raw = right
    elif not right:
        args_raw = left
    else:
        if left.endswith(","):
            left = left[:-1].rstrip()
        args_raw = left + ", " + right

    # Unwrap Resumed wrapper if present
    if isinstance(resumed.result, Resumed):
        result: Result = resumed.result.inner
    else:
        result = resumed.result

    return dataclasses.replace(
        original,
        args_raw=args_raw,
        result=result,
        duration=resumed.duration,
        raw_line=original.raw_line + " ... " + resumed.raw_line,
    )
