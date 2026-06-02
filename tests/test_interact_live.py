import os, shutil, pytest
from strace_ui.app import StraceUiApp
from strace_ui.cli import build_strace_args
from strace_ui.model import default_model, RenderMode, Focus
from strace_ui.themes import get_theme, default_theme_name

pytestmark = pytest.mark.skipif(shutil.which("strace") is None, reason="no strace")

async def _live_app():
    read_fd, write_fd = os.pipe(); os.set_inheritable(write_fd, True)
    argv = build_strace_args(write_fd=write_fd, trace_expr=None, attach_pid=None, program=["ls","/etc"])
    app = StraceUiApp(model=default_model(resolve_pid_info=lambda p: None),
                      theme=get_theme(default_theme_name()), strace_argv=argv,
                      write_fd=write_fd, read_fd=read_fd)
    return app

@pytest.mark.asyncio
async def test_interactions_on_live_data():
    app = await _live_app()
    async with app.run_test() as pilot:
        for _ in range(60):
            await pilot.pause(0.1)
            if app.model.syscall_list.total_count() > 5: break
        total = app.model.syscall_list.total_count()
        assert total > 5
        # navigation
        await pilot.press("G"); await pilot.pause()
        assert app.model.selected_index() == app.model.filtered_count()-1
        await pilot.press("g"); await pilot.pause()
        assert app.model.selected_index() == 0
        await pilot.press("j","j"); await pilot.pause()
        assert app.model.selected_index() == 2
        # render mode cycle
        await pilot.press("x"); await pilot.pause()
        assert app.model.render_mode is RenderMode.HEXDUMP
        # man toggle
        await pilot.press("m"); await pilot.pause()
        assert app.model.show_man_page is True
        # focus toggle
        await pilot.press("tab"); await pilot.pause()
        assert app.model.focus is Focus.DETAIL_PANE
        await pilot.press("tab"); await pilot.pause()
        # filter to 'openat' via filter editor
        await pilot.press("f")
        for c in "openat": await pilot.press(c)
        await pilot.press("enter"); await pilot.pause()
        from strace_ui.filter import to_normalized_string
        assert to_normalized_string(app.model.syscall_filter) == "openat"
        fc = app.model.filtered_count()
        assert 0 < fc <= total
        assert all(app.model.get_filtered(i).syscall_name=="openat" for i in range(fc))
        # clear filter (alt+f)
        await pilot.press("alt+f"); await pilot.pause()
        assert app.model.filtered_count() == total
        # preset cycle (%)
        await pilot.press("percent_sign"); await pilot.pause()
        assert to_normalized_string(app.model.syscall_filter) == "%desc"
        # help modal then dismiss
        await pilot.press("alt+f")  # clear back
        await pilot.press("question_mark"); await pilot.pause()
        assert app.model.show_help is True
        await pilot.press("escape"); await pilot.pause()
        assert app.model.show_help is False
        print(f"OK: {total} rows, all interactions worked")
