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
