"""Tests for filter_editor — faithful port of OCaml filter_editor.ml."""
from strace_ui.filter_editor import apply_action, EditState, is_editing, editing_buffer
import strace_ui.filter_editor as FE
from strace_ui import filter as F


def test_start_appends_trailing_space():
    state, sub = apply_action(None, F.parse("read"), FE.Start())
    assert state.buf == "read " and state.cursor == 5
    assert sub is None


def test_start_regex_appends_slash():
    state, _ = apply_action(None, F.parse("read"), FE.StartRegex())
    assert state.buf == "read /"


def test_start_empty_filter():
    state, _ = apply_action(None, F.parse(""), FE.Start())
    assert state.buf == "" and state.cursor == 0


def test_start_regex_empty_filter():
    state, _ = apply_action(None, F.parse(""), FE.StartRegex())
    assert state.buf == "/"


def test_key_inserts_at_cursor():
    s = EditState(buf="rd", cursor=1)
    s2, _ = apply_action(s, [], FE.Key("e"))
    assert s2.buf == "red" and s2.cursor == 2


def test_backspace():
    s = EditState(buf="read", cursor=4)
    s2, _ = apply_action(s, [], FE.Backspace())
    assert s2.buf == "rea" and s2.cursor == 3


def test_delete_forward():
    s = EditState(buf="read", cursor=0)
    s2, _ = apply_action(s, [], FE.DeleteForward())
    assert s2.buf == "ead" and s2.cursor == 0


def test_kill_to_end_and_start():
    s = EditState(buf="abcdef", cursor=3)
    assert apply_action(s, [], FE.KillToEnd())[0].buf == "abc"
    s2 = apply_action(s, [], FE.KillToStart())[0]
    assert s2.buf == "def" and s2.cursor == 0


def test_kill_word_backward():
    s = EditState(buf="%net read", cursor=9)
    s2, _ = apply_action(s, [], FE.KillWordBackward())
    assert s2.buf == "%net " and s2.cursor == 5


def test_move_word_forward():
    s = EditState(buf="%net read", cursor=0)
    s2, _ = apply_action(s, [], FE.MoveWordForward())
    assert s2.cursor == 5


def test_move_word_backward():
    s = EditState(buf="%net read", cursor=9)
    s2, _ = apply_action(s, [], FE.MoveWordBackward())
    assert s2.cursor == 5


def test_move_left_right_clamped():
    s = EditState(buf="ab", cursor=0)
    assert apply_action(s, [], FE.MoveLeft())[0].cursor == 0
    assert apply_action(EditState("ab", 2), [], FE.MoveRight())[0].cursor == 2
    assert apply_action(EditState("ab", 0), [], FE.MoveToEnd())[0].cursor == 2
    assert apply_action(EditState("ab", 2), [], FE.MoveToStart())[0].cursor == 0


def test_submit_normalizes_and_clears():
    s = EditState(buf="  %net  read ", cursor=0)
    state, submitted = apply_action(s, [], FE.Submit())
    assert state is None
    assert submitted == "%net read"


def test_cancel_clears():
    s = EditState(buf="x", cursor=1)
    state, submitted = apply_action(s, [], FE.Cancel())
    assert state is None and submitted is None


def test_is_editing():
    assert not is_editing(None)
    assert is_editing(EditState("a", 1))
    assert editing_buffer(EditState("ab", 1)) == "ab"
    assert editing_buffer(None) is None
