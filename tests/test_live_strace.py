import asyncio
import os
import shutil

import pytest

from strace_ui.app import StraceUiApp
from strace_ui.cli import build_strace_args
from strace_ui.model import default_model
from strace_ui.themes import get_theme, default_theme_name


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("strace") is None, reason="strace not installed")
async def test_live_strace_streams_into_model():
    read_fd, write_fd = os.pipe()
    os.set_inheritable(write_fd, True)
    argv = build_strace_args(write_fd=write_fd, trace_expr=None, attach_pid=None,
                             program=["ls", "/etc"])
    model = default_model(resolve_pid_info=lambda pid: None)
    app = StraceUiApp(model=model, theme=get_theme(default_theme_name()),
                      strace_argv=argv, write_fd=write_fd, read_fd=read_fd)
    async with app.run_test() as pilot:
        # give strace time to run and stream (up to 5 seconds)
        for _ in range(50):
            await pilot.pause(0.1)
            if app.model.syscall_list.total_count() > 0:
                break
        assert app.model.syscall_list.total_count() > 0, "no syscalls streamed from live strace"
