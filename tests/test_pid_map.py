from strace_ui.pid_map import PidMap, PidInfo


def test_register_and_short_id():
    m = PidMap.empty()
    m = m.register(100)
    m = m.register(200)
    assert m.short_id(100) == 0
    assert m.short_id(200) == 1
    assert m.short_id(999) is None


def test_register_idempotent():
    m = PidMap.empty().register(100).register(100)
    assert m.short_id(100) == 0
    assert m.next_id == 1


def test_display_width():
    m = PidMap.empty()
    assert m.display_width() == 1
    for p in range(15):
        m = m.register(1000 + p)   # ids 0..14 -> max id 14 -> width 2
    assert m.display_width() == 2


def test_summary_process_vs_thread():
    m = PidMap.empty().register(5)
    m = m.set_info(5, PidInfo(cmdline="ping localhost", thread_name="ping", is_thread=False))
    assert m.summary(5) == "ping localhost"
    m = m.set_info(5, PidInfo(cmdline="ping localhost", thread_name="worker", is_thread=True))
    assert m.summary(5) == "thread: worker (ping localhost)"


def test_summary_unknown_none():
    assert PidMap.empty().summary(5) is None
