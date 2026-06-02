"""Pilot smoke test for StraceUiApp.

Tests that the app mounts, renders, and key→action wiring works without crashing.
Uses strace_argv=None so no actual strace process is launched.
"""
import pytest
import pytest_asyncio
from io import StringIO

from rich.console import Console

from strace_ui.app import StraceUiApp, HelpOverlay
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


# ---------------------------------------------------------------------------
# Fix 1: Help overlay rendering tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_help_overlay_visible_toggles():
    """HelpOverlay widget display must track model.show_help.

    Asserts that the overlay widget is mounted, hidden initially,
    becomes visible after pressing '?', and hidden again after Escape.
    Also verifies that the overlay content contains the expected help text.
    """
    app = StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.dispatch(AddLine('100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
        await pilot.pause(0.1)

        overlay = app.query_one(HelpOverlay)

        # Initially hidden
        assert overlay.display is False, "Help overlay must be hidden at startup"
        assert app.model.show_help is False

        # Toggle on with '?'
        await pilot.press("question_mark")
        await pilot.pause(0.05)
        assert app.model.show_help is True
        assert overlay.display is True, "Help overlay must be visible when show_help is True"

        # Content must contain the help text (render it via Rich to plain string)
        buf = StringIO()
        console = Console(file=buf, no_color=True, width=70)
        console.print(overlay.content)
        rendered = buf.getvalue()
        assert "Keyboard Shortcuts" in rendered, (
            "Help overlay content must include 'Keyboard Shortcuts'"
        )
        assert "Follow selected FD" in rendered, (
            "Help overlay content must include 'Follow selected FD'"
        )

        # Dismiss with Escape
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.model.show_help is False
        assert overlay.display is False, "Help overlay must be hidden after dismiss"


@pytest.mark.asyncio
async def test_help_overlay_f1_toggles():
    """F1 key also toggles the help overlay."""
    app = StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        overlay = app.query_one(HelpOverlay)
        assert overlay.display is False

        await pilot.press("f1")
        await pilot.pause(0.05)
        assert app.model.show_help is True
        assert overlay.display is True

        # Any key while help is shown closes it
        await pilot.press("j")
        await pilot.pause(0.05)
        assert app.model.show_help is False
        assert overlay.display is False


# ---------------------------------------------------------------------------
# Fix 2: Filter label shown in list pane border_subtitle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_label_shows_expr():
    """After applying a filter, border_subtitle must contain the filter expression.

    Verifies the fix that render_filter_label() result is actually surfaced
    in the list pane border text rather than being discarded.
    """
    app = StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.dispatch(AddLine('100 1.0 read(3, "x", 1) = 1'))
        await pilot.pause(0.1)

        list_pane = app.query_one("#list-pane")

        # Before any filter the default shows "all"
        subtitle = list_pane.border_subtitle or ""
        assert "f:" in subtitle, f"Expected 'f:' prefix in border_subtitle, got: {subtitle!r}"

        # Apply a 'read' filter: press f, type 'r','e','a','d', Enter
        await pilot.press("f")
        for ch in "read":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)

        subtitle = list_pane.border_subtitle or ""
        assert "read" in subtitle, (
            f"Expected 'read' in border_subtitle after filter, got: {subtitle!r}"
        )


@pytest.mark.asyncio
async def test_filter_edit_mode_is_visually_distinct():
    """While editing, the list pane shows a clear FILTER prompt + block cursor;
    when not editing it shows the normal Syscalls title."""
    from strace_ui.widgets import SyscallListWidget

    app = StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )
    async with app.run_test() as pilot:
        app.dispatch(AddLine('100 1.0 read(3, "x", 1) = 1'))
        await pilot.pause()
        pane = app.query_one(SyscallListWidget)
        assert "Syscalls" in str(pane.border_title)
        assert "FILTER" not in str(pane.border_title)

        await pilot.press("f")
        for c in "mm":
            await pilot.press(c)
        await pilot.pause()
        assert "FILTER" in str(pane.border_title), "no clear editing indicator in title"
        assert "mm" in str(pane.border_subtitle)
        assert "█" in str(pane.border_subtitle), "no visible cursor while editing"

        await pilot.press("escape")
        await pilot.pause()
        assert "Syscalls" in str(pane.border_title)
        assert "FILTER" not in str(pane.border_title)


@pytest.mark.asyncio
async def test_filter_label_shows_edit_buffer():
    """During filter editing the in-progress buffer must appear in border_subtitle."""
    app = StraceUiApp(
        model=default_model(resolve_pid_info=lambda pid: None),
        theme=get_theme(default_theme_name()),
        strace_argv=None,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.dispatch(AddLine('100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
        await pilot.pause(0.1)

        list_pane = app.query_one("#list-pane")

        # Start editing and type 'ope' — buffer should appear immediately
        await pilot.press("f")
        await pilot.pause(0.05)
        for ch in "ope":
            await pilot.press(ch)
        await pilot.pause(0.05)

        subtitle = list_pane.border_subtitle or ""
        assert "ope" in subtitle, (
            f"Expected partial buffer 'ope' in border_subtitle during edit, "
            f"got: {subtitle!r}"
        )

        # Cancel editing — subtitle reverts to default filter display
        await pilot.press("escape")
        await pilot.pause(0.05)
        subtitle_after = list_pane.border_subtitle or ""
        assert "ope" not in subtitle_after or "f:" in subtitle_after, (
            "After cancel, border_subtitle should revert to the committed filter"
        )
