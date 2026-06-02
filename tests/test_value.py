from strace_ui.value import Atom, String, Struct, Array, Call, parse, to_lines


def test_parse_atom():
    assert parse("42") == Atom("42")


def test_parse_quoted_string():
    assert parse('"hello"') == String("hello")


def test_parse_struct():
    assert parse("{sa_family=AF_INET, sin_port=htons(0)}") == Struct([
        ("sa_family", Atom("AF_INET")),
        ("sin_port", Call("htons", "0")),
    ])


def test_parse_array():
    assert parse("[1, 2, 3]") == Array([Atom("1"), Atom("2"), Atom("3")])


def test_parse_empty_array():
    assert parse("[]") == Array([])


def test_parse_bare_field_in_struct():
    assert parse("{FOO}") == Struct([("FOO", Atom(""))])


def test_parse_nested():
    assert parse("{a=[1, {b=2}]}") == Struct([
        ("a", Array([Atom("1"), Struct([("b", Atom("2"))])])),
    ])


def test_to_lines_struct_tree():
    v = parse("{sa_family=AF_INET, sin_addr=inet_addr(\"127.0.0.1\")}")
    assert to_lines(v) == [
        "├─sa_family = AF_INET",
        '╰─sin_addr = inet_addr("127.0.0.1")',
    ]


def test_to_lines_array_tree():
    v = parse("[{x=1}, {y=2}]")
    assert to_lines(v) == [
        "├─[0]",
        "│ ╰─x = 1",
        "╰─[1]",
        "  ╰─y = 2",
    ]
