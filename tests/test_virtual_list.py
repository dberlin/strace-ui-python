from strace_ui.virtual_list import VirtualList


def test_append_and_counts():
    vl = VirtualList.create()
    vl = vl.append("a", passes_filter=True)
    vl = vl.append("b", passes_filter=False)
    vl = vl.append("c", passes_filter=True)
    assert vl.total_count() == 3
    assert vl.filtered_count() == 2
    assert vl.get_filtered(0) == "a"
    assert vl.get_filtered(1) == "c"


def test_select_actions_clamp():
    vl = VirtualList.create()
    for x in "abc":
        vl = vl.append(x, passes_filter=True)
    vl = vl.select_down().select_down().select_down()
    assert vl.selected_index == 2
    vl = vl.select_up().select_up().select_up()
    assert vl.selected_index == 0
    assert vl.select_bottom().selected_index == 2
    assert vl.select_top().selected_index == 0


def test_refilter_preserves_selection_to_nearest_prior():
    vl = VirtualList.create()
    for x in ["a", "b", "c", "d"]:
        vl = vl.append(x, passes_filter=True)
    vl = vl.jump_to_filtered_index(2)   # selected raw index 2 ("c")
    keep = {"a", "d"}
    vl = vl.refilter(lambda item: item in keep)
    assert vl.get_selected() == "a"


def test_set_item():
    vl = VirtualList.create().append("a", passes_filter=True)
    vl = vl.set_item(0, "A")
    assert vl.get_raw(0) == "A"


def test_get_filtered_out_of_range():
    vl = VirtualList.create().append("a", passes_filter=True)
    assert vl.get_filtered(5) is None
    assert vl.get_filtered(-1) is None


def test_get_selected_empty():
    vl = VirtualList.create()
    assert vl.get_selected() is None


def test_append_clamps_selection():
    # When the only filtered item count shrinks logic: appending keeps selection valid
    vl = VirtualList.create()
    vl = vl.append("a", passes_filter=True)   # fc=1, sel clamped to 0
    assert vl.selected_index == 0
