"""parser: faithful Python port of OCaml strace_parser.ml"""

from __future__ import annotations

import dataclasses
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
