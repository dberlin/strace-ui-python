"""Performance-regression tests for the Textual app.

The detail pane re-render (`render_detail`) is expensive (milliseconds for lines
with large buffers). Re-running it on every appended syscall under a high-volume
trace (e.g. `ping`) saturated the event loop and starved keyboard input. These
tests pin the fix: the detail pane re-renders only when what it displays changes.
"""

from __future__ import annotations

import pytest

from strace_ui.app import StraceUiApp
from strace_ui.model import AddLine, default_model
from strace_ui.themes import default_theme_name, get_theme
from strace_ui.widgets import DetailWidget

L1 = '100 1.0 openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3'
L2 = '100 1.1 read(3, "data", 1024) = 4'
FLOOD = '100 2.0 recvmsg(3, {msg_name=...}, 0) = 64'


def _make_app():
    return StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )


@pytest.mark.asyncio
async def test_detail_not_rerendered_on_unrelated_appends():
    app = _make_app()
    async with app.run_test() as pilot:
        app.dispatch(AddLine(L1))  # first line -> selection set -> detail renders
        app.dispatch(AddLine(L2))
        await pilot.pause()

        detail = app.query_one(DetailWidget)
        calls = {"n": 0}
        original = detail.update_detail

        def counting():
            calls["n"] += 1
            return original()

        detail.update_detail = counting  # type: ignore[method-assign]

        # Flood with appends that do NOT move the selection.
        for _ in range(100):
            app.dispatch(AddLine(FLOOD))
        await pilot.pause()
        assert calls["n"] == 0, "detail re-rendered on appends that didn't change selection"

        # Moving the selection MUST re-render the detail.
        await pilot.press("j")
        await pilot.pause()
        assert calls["n"] >= 1, "detail did not re-render when selection changed"


@pytest.mark.asyncio
async def test_detail_rerenders_on_render_mode_change():
    app = _make_app()
    async with app.run_test() as pilot:
        app.dispatch(AddLine(L1))
        app.dispatch(AddLine(L2))
        await pilot.pause()

        detail = app.query_one(DetailWidget)
        calls = {"n": 0}
        original = detail.update_detail

        def counting():
            calls["n"] += 1
            return original()

        detail.update_detail = counting  # type: ignore[method-assign]

        await pilot.press("x")  # cycle render mode -> detail content changes
        await pilot.pause()
        assert calls["n"] >= 1, "detail did not re-render when render mode changed"


# --- O(1)-per-line scaling guards (structural, not timing-based) -------------

def test_virtual_list_append_shares_backing_o1():
    """append must not copy the backing lists (O(1), shared) — guards O(n^2)."""
    from strace_ui.virtual_list import VirtualList

    vl1 = VirtualList.create()
    vl2 = vl1.append("a", passes_filter=True)
    vl3 = vl2.append("b", passes_filter=True)
    # Shared backing store across versions => no per-append copy.
    assert vl2.all_items is vl1.all_items
    assert vl3.all_items is vl1.all_items
    assert vl2.filtered_indices is vl1.filtered_indices


def test_apply_action_does_not_copy_resolved_fds():
    """AddLine must mutate resolved_fds in place (O(1)), not copy it per line."""
    m1 = default_model(resolve_pid_info=lambda pid: None)
    from strace_ui.model import apply_action

    m2 = apply_action(m1, AddLine(L1))
    m3 = apply_action(m2, AddLine(L2))
    # Same dict object threaded through => no O(n) copy on each appended line.
    assert m3.resolved_fds is m2.resolved_fds
    assert len(m3.resolved_fds) == 2
