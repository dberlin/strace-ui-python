from strace_ui.display_utils import split_top_level


def test_split_top_level_plain():
    assert split_top_level("a, b, c", on=",") == ["a", " b", " c"]


def test_split_top_level_ignores_nested_brackets():
    assert split_top_level("a, [b, c], d", on=",") == ["a", " [b, c]", " d"]


def test_split_top_level_ignores_nested_braces_and_parens():
    assert split_top_level("{x=1, y=2}, htons(0, 1)", on=",") == ["{x=1, y=2}", " htons(0, 1)"]


def test_split_top_level_ignores_commas_in_quoted_strings():
    assert split_top_level('"a,b", c', on=",") == ['"a,b"', " c"]


def test_split_top_level_quote_with_escaped_quote():
    assert split_top_level(r'"a\",b", c', on=",") == [r'"a\",b"', " c"]


def test_split_top_level_empty():
    assert split_top_level("", on=",") == []
