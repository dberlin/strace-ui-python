"""Pilot smoke test for StraceUiApp.

Tests that the app mounts, renders, and key→action wiring works without crashing.
Uses strace_argv=None so no actual strace process is launched.
"""
import pytest
import pytest_asyncio

from strace_ui.app import StraceUiApp
from strace_ui.model import default_model, AddLine, Focus
from strace_ui.themes import get_theme, default_theme_name

# Three synthetic strace lines (pid=100, short format)
LINES = [
    '100 1.000000 openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3',
    '100 1.100000 read(3, "root:x:0:0", 1024) = 10',
    '100 1.200000 close(3) = 0',
]


@pytest.mark.asyncio
async def test_app_runs_and_handles_keys():
    model = default_model(resolve_pid_info=lambda pid: None)
    app = StraceUiApp(
        model=model,
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        # Feed lines into the model
        for ln in LINES:
            app.dispatch(AddLine(ln))
        await pilot.pause(0.1)

        # All lines should be loaded
        assert app.model.syscall_list.total_count() == 3

        # Navigation
        await pilot.press("j")           # SelectDown
        await pilot.pause(0.05)
        assert app.model.selected_index() == 1

        await pilot.press("G")           # SelectBottom
        await pilot.pause(0.05)
        assert app.model.selected_index() == 2

        await pilot.press("g")           # SelectTop
        await pilot.pause(0.05)
        assert app.model.selected_index() == 0

        # Tab switches focus
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert app.model.focus == Focus.DETAIL_PANE

        await pilot.press("tab")
        await pilot.pause(0.05)
        assert app.model.focus == Focus.SYSCALL_LIST

        # x cycles render mode
        initial_mode = app.model.render_mode
        await pilot.press("x")
        await pilot.pause(0.05)
        assert app.model.render_mode != initial_mode

        # ? opens help
        await pilot.press("question_mark")
        await pilot.pause(0.05)
        assert app.model.show_help is True

        # Any key (escape) dismisses help
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.model.show_help is False

        # f starts filter edit, type "read", enter to submit
        await pilot.press("f")
        await pilot.pause(0.05)
        from strace_ui import filter_editor as FE
        assert FE.is_editing(app.model.filter_editor)

        await pilot.press("r", "e", "a", "d")
        await pilot.pause(0.05)
        assert FE.editing_buffer(app.model.filter_editor) is not None

        await pilot.press("enter")
        await pilot.pause(0.05)
        # After submit, filter editor should be closed
        assert not FE.is_editing(app.model.filter_editor)
        # Filter should be applied — only "read" syscall visible
        fc = app.model.filtered_count()
        assert fc == 1

        # Clear the filter
        await pilot.press("alt+f")
        await pilot.pause(0.05)
        assert app.model.filtered_count() == 3

        # % cycles preset filter
        await pilot.press("percent_sign")
        await pilot.pause(0.05)
        # No assertion on count, just no crash

        # Clear again
        await pilot.press("alt+f")
        await pilot.pause(0.05)

        # h hides selected syscall (the first one, openat)
        app.dispatch(AddLine(LINES[0]))  # re-add so we have something to hide
        await pilot.pause(0.05)
        await pilot.press("g")           # go to top
        await pilot.pause(0.05)
        await pilot.press("h")
        await pilot.pause(0.05)
        # The openat syscall should be hidden
        for i in range(app.model.filtered_count()):
            line = app.model.get_filtered(i)
            assert line.syscall_name != "openat", "openat should be hidden"

        # Clear filter and restore
        await pilot.press("alt+f")
        await pilot.pause(0.05)

        # m toggles man page
        await pilot.press("m")
        await pilot.pause(0.05)
        assert app.model.show_man_page is True

        await pilot.press("m")
        await pilot.pause(0.05)
        assert app.model.show_man_page is False

        # ctrl+c quits (but run_test will handle the exit)
        # We just verify no exception was raised throughout.


@pytest.mark.asyncio
async def test_filter_edit_escape_cancels():
    """Pressing escape while editing cancels without applying filter."""
    model = default_model(resolve_pid_info=lambda pid: None)
    app = StraceUiApp(
        model=model,
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        for ln in LINES:
            app.dispatch(AddLine(ln))
        await pilot.pause(0.1)

        # Start editing
        await pilot.press("f")
        await pilot.pause(0.05)

        from strace_ui import filter_editor as FE
        assert FE.is_editing(app.model.filter_editor)

        await pilot.press("o", "p", "e", "n")
        await pilot.pause(0.05)

        # Escape cancels
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not FE.is_editing(app.model.filter_editor)
        # Filter should be unchanged (no filter applied)
        assert app.model.filtered_count() == 3


@pytest.mark.asyncio
async def test_detail_focus_scroll():
    """Switching to detail pane and scrolling doesn't crash."""
    model = default_model(resolve_pid_info=lambda pid: None)
    app = StraceUiApp(
        model=model,
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        for ln in LINES:
            app.dispatch(AddLine(ln))
        await pilot.pause(0.1)

        # Switch to detail pane
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert app.model.focus == Focus.DETAIL_PANE

        # Scroll in detail pane (j/k with detail focus)
        await pilot.press("j")
        await pilot.pause(0.05)
        await pilot.press("k")
        await pilot.pause(0.05)
        await pilot.press("G")
        await pilot.pause(0.05)
        await pilot.press("g")
        await pilot.pause(0.05)

        # Page down/up in detail
        await pilot.press("d")
        await pilot.pause(0.05)
        await pilot.press("u")
        await pilot.pause(0.05)

        # Switch back
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert app.model.focus == Focus.SYSCALL_LIST
