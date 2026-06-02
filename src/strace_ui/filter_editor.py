"""filter_editor: faithful Python port of OCaml filter_editor.ml (lines 1-260).

Provides a pure state machine for an in-place filter editor with emacs-style
cursor motions.  The render_label function (which requires a terminal/UI layer)
is intentionally excluded and belongs in a later render module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from strace_ui import filter as F


# ---------------------------------------------------------------------------
# EditState — the editor's mutable snapshot (frozen dataclass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditState:
    """Snapshot of the editor buffer and cursor position.

    Positional construction (``EditState("ab", 1)``) and keyword construction
    both work because the fields are declared in order.
    """

    buf: str
    cursor: int


# The editor value ``t`` is ``EditState | None``; ``None`` means not editing.
EditorState = Optional[EditState]


# ---------------------------------------------------------------------------
# Action types — each is a frozen dataclass (fields only where needed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Start:
    """Begin editing from the current filter (appends a trailing space)."""


@dataclass(frozen=True)
class StartRegex:
    """Begin editing a regex filter (appends ' /' or '/' if empty)."""


@dataclass(frozen=True)
class Key:
    """Insert a single character at the cursor."""

    c: str


@dataclass(frozen=True)
class Backspace:
    """Delete the character before the cursor."""


@dataclass(frozen=True)
class DeleteForward:
    """Delete the character at the cursor."""


@dataclass(frozen=True)
class MoveLeft:
    """Move the cursor one position to the left (clamped to 0)."""


@dataclass(frozen=True)
class MoveRight:
    """Move the cursor one position to the right (clamped to len(buf))."""


@dataclass(frozen=True)
class MoveToStart:
    """Move the cursor to position 0."""


@dataclass(frozen=True)
class MoveToEnd:
    """Move the cursor to the end of the buffer."""


@dataclass(frozen=True)
class KillToEnd:
    """Delete everything from the cursor to the end of the buffer."""


@dataclass(frozen=True)
class KillToStart:
    """Delete everything from the start of the buffer up to the cursor."""


@dataclass(frozen=True)
class KillWordBackward:
    """Delete the word immediately before the cursor (emacs Ctrl-w)."""


@dataclass(frozen=True)
class MoveWordForward:
    """Move the cursor forward past the next word (emacs Alt-f)."""


@dataclass(frozen=True)
class MoveWordBackward:
    """Move the cursor backward to the start of the previous word (emacs Alt-b)."""


@dataclass(frozen=True)
class Submit:
    """Accept the buffer, normalise it, and leave edit mode."""


@dataclass(frozen=True)
class Cancel:
    """Discard the buffer and leave edit mode without submitting."""


Action = Union[
    Start, StartRegex, Key, Backspace, DeleteForward,
    MoveLeft, MoveRight, MoveToStart, MoveToEnd,
    KillToEnd, KillToStart, KillWordBackward,
    MoveWordForward, MoveWordBackward,
    Submit, Cancel,
]


# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------


def is_editing(t: EditorState) -> bool:
    """Return True when the editor is active (i.e. t is not None)."""
    return t is not None


def editing_buffer(t: EditorState) -> Optional[str]:
    """Return the current buffer string, or None when not editing."""
    if t is None:
        return None
    return t.buf


# ---------------------------------------------------------------------------
# Word-boundary helpers (port of OCaml lines 152-183)
# ---------------------------------------------------------------------------


def word_boundary_backward(buf: str, cursor: int) -> int:
    """Return the start position of the word immediately before *cursor*.

    Emacs Alt-b / Ctrl-w semantics: skip spaces backward, then skip
    non-spaces backward.
    """
    if cursor == 0:
        return 0
    pos = cursor - 1
    # Skip trailing spaces
    while pos > 0 and buf[pos] == " ":
        pos -= 1
    # Skip the word characters
    while pos > 0 and buf[pos - 1] != " ":
        pos -= 1
    return pos


def word_boundary_forward(buf: str, cursor: int) -> int:
    """Return the position just past the next word starting at *cursor*.

    Emacs Alt-f semantics: skip non-spaces forward, then skip spaces forward.
    """
    n = len(buf)
    if cursor >= n:
        return n
    pos = cursor
    # Skip current word
    while pos < n and buf[pos] != " ":
        pos += 1
    # Skip trailing spaces
    while pos < n and buf[pos] == " ":
        pos += 1
    return pos


# ---------------------------------------------------------------------------
# apply_action — the core state transition (port of OCaml lines 193-260)
# ---------------------------------------------------------------------------


def apply_action(
    t: EditorState,
    current_filter: list,
    action: Action,
) -> tuple[EditorState, Optional[str]]:
    """Apply *action* to the editor state *t* and return ``(new_state, submitted)``.

    *current_filter* is the current list of filter ``Term``s (used only by
    ``Start`` and ``StartRegex``).

    Returns a 2-tuple:
    - ``new_state``: the updated ``EditState``, or ``None`` when not editing.
    - ``submitted``: the normalised filter string when ``Submit`` is applied and
      the editor was active; ``None`` otherwise.
    """
    # --- Start actions (always valid regardless of whether we are editing) ---

    if isinstance(action, Start):
        initial = F.to_normalized_string(current_filter)
        if initial and not initial.endswith(" "):
            initial = initial + " "
        return EditState(initial, len(initial)), None

    if isinstance(action, StartRegex):
        initial = F.to_normalized_string(current_filter)
        initial = "/" if not initial else initial + " /"
        return EditState(initial, len(initial)), None

    # --- Submit / Cancel (valid regardless of editing state) ---

    if isinstance(action, Submit):
        if t is not None:
            return None, F.normalize(t.buf)
        return t, None

    if isinstance(action, Cancel):
        return None, None

    # --- Editing actions: only act when in editing mode (OCaml with_editing_state) ---

    if t is None:
        return t, None

    buf = t.buf
    cursor = t.cursor

    if isinstance(action, Key):
        new_buf = buf[:cursor] + action.c + buf[cursor:]
        return EditState(new_buf, cursor + 1), None

    if isinstance(action, Backspace):
        if cursor > 0:
            new_buf = buf[: cursor - 1] + buf[cursor:]
            return EditState(new_buf, cursor - 1), None
        return EditState(buf, cursor), None

    if isinstance(action, DeleteForward):
        if cursor < len(buf):
            new_buf = buf[:cursor] + buf[cursor + 1:]
            return EditState(new_buf, cursor), None
        return EditState(buf, cursor), None

    if isinstance(action, MoveLeft):
        return EditState(buf, max(0, cursor - 1)), None

    if isinstance(action, MoveRight):
        return EditState(buf, min(len(buf), cursor + 1)), None

    if isinstance(action, MoveToStart):
        return EditState(buf, 0), None

    if isinstance(action, MoveToEnd):
        return EditState(buf, len(buf)), None

    if isinstance(action, KillToEnd):
        return EditState(buf[:cursor], cursor), None

    if isinstance(action, KillToStart):
        return EditState(buf[cursor:], 0), None

    if isinstance(action, KillWordBackward):
        nc = word_boundary_backward(buf, cursor)
        new_buf = buf[:nc] + buf[cursor:]
        return EditState(new_buf, nc), None

    if isinstance(action, MoveWordForward):
        return EditState(buf, word_boundary_forward(buf, cursor)), None

    if isinstance(action, MoveWordBackward):
        return EditState(buf, word_boundary_backward(buf, cursor)), None

    raise TypeError(f"Unknown action type: {type(action)}")
