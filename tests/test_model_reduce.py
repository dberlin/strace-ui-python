from strace_ui.model import default_model, resolve_fds, passes_filter
from strace_ui.parser import parse_line


def test_default_model_empty():
    m = default_model()
    assert m.next_index == 0
    assert m.syscall_list.total_count() == 0
    assert m.syscall_filter == []


def test_default_model_primary_pid_registers():
    m = default_model(primary_pid=42, resolve_pid_info=lambda pid: None)
    assert m.pid_map.short_id(42) == 0


def test_resolve_fds_for_open_returns_new_fd():
    from strace_ui.fd_tracker import FdTracker
    p = parse_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3')
    fds = resolve_fds(p, fd_tracker=FdTracker.empty())
    assert any(f.fd_number == 3 for f in fds)


# ---------------------------------------------------------------------------
# Task 18: apply_action reducer tests
# ---------------------------------------------------------------------------

from strace_ui.model import default_model, apply_action
from strace_ui import model as M
from strace_ui.parser import ValueResult


def feed(m, *lines):
    for ln in lines:
        m = apply_action(m, M.AddLine(ln))
    return m


def test_add_normal_line_appends_and_indexes():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3')
    assert m.syscall_list.total_count() == 1
    assert m.next_index == 1
    assert m.fd_tracker.resolve_fd(100, 3) is not None


def test_unparseable_still_advances_index():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m, "garbage line")
    assert m.next_index == 1
    assert m.syscall_list.total_count() == 0


def test_unfinished_then_resumed_merges():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '7 2.5 recvmsg(3, {a=1}, <unfinished ...>',
        '7 2.6 <... recvmsg resumed> 0) = 64 <0.0001>')
    assert m.syscall_list.total_count() == 1
    row = m.syscall_list.get_raw(0)
    assert row.result == ValueResult("64")
    assert m.pending_syscalls == {}


def test_fork_then_child_fd_reresolved():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 clone(child_stack=NULL) = 200',
        '200 1.2 read(3, "x", 1) = 1')
    fds = m.resolved_fds[2]
    assert any(f.source_pid == 100 and f.fd_number == 3 for f in fds)


def test_unfinished_clone_child_before_resume_gets_reresolved():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 clone(child_stack=NULL <unfinished ...>',
        '200 1.2 read(3, "x", 1) = 1',
        '100 1.3 <... clone resumed>) = 200')
    fds = m.resolved_fds[2]
    assert any(f.source_pid == 100 and f.fd_number == 3 for f in fds)


def test_resumed_without_pending_appends_new_row():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m, '7 2.6 <... recvmsg resumed> 0) = 64 <0.0001>')
    assert m.syscall_list.total_count() == 1
    assert m.syscall_list.get_raw(0).result == ValueResult("64")


def test_set_filter_refilters():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 read(3, "x", 1) = 1')
    m = apply_action(m, M.SetFilter("read"))
    assert m.syscall_list.filtered_count() == 1
    assert m.syscall_list.get_selected().syscall_name == "read"


def test_cycle_preset_filter_order():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = apply_action(m, M.CyclePresetFilter())
    from strace_ui.filter import to_normalized_string
    assert to_normalized_string(m.syscall_filter) == "%desc"


def test_toggle_help_and_render_mode_and_focus():
    m = default_model(resolve_pid_info=lambda pid: None)
    assert apply_action(m, M.ToggleHelp()).show_help is True
    from strace_ui.model import RenderMode, Focus
    assert apply_action(m, M.ToggleRenderMode()).render_mode is RenderMode.HEXDUMP
    assert apply_action(m, M.ToggleFocus()).focus is Focus.DETAIL_PANE
