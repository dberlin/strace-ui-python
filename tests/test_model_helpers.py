from strace_ui.model import (
    RenderMode, Focus, is_fd_return_type, extract_fd_numbers, buffer_meaningful_length,
)
from strace_ui.parser import parse_line

def test_render_mode_cycle():
    assert RenderMode.AUTO.cycle() is RenderMode.HEXDUMP
    assert RenderMode.HEXDUMP.cycle() is RenderMode.STRING
    assert RenderMode.STRING.cycle() is RenderMode.AUTO
def test_render_mode_short_strings():
    assert RenderMode.AUTO.to_short_string() == "auto"
    assert RenderMode.HEXDUMP.to_short_string() == "hex"
    assert RenderMode.STRING.to_short_string() == "str"
def test_should_hexdump_in_auto_detects_binary():
    assert RenderMode.should_hexdump_in_auto(r"\xff\x00")
    assert not RenderMode.should_hexdump_in_auto("plain text")
def test_use_hexdump_modes():
    assert RenderMode.HEXDUMP.use_hexdump(escaped_content="abc")
    assert not RenderMode.STRING.use_hexdump(escaped_content=r"\xff")
def test_is_fd_return_type():
    assert is_fd_return_type(syscall_name="openat", args_raw='AT_FDCWD, "/a", 0')
    assert not is_fd_return_type(syscall_name="read", args_raw='3, "x", 1')
def test_extract_fd_numbers_args_and_return():
    p = parse_line(0, '100 1.0 dup2(4, 5) = 5')
    assert set(extract_fd_numbers(p)) >= {4, 5}
def test_buffer_meaningful_length_read():
    p = parse_line(0, '100 1.0 read(3, "abcdef", 100) = 4')
    assert buffer_meaningful_length(syscall_name="read", arg_index=1,
                                    args=['3', '"abcdef"', '100'], result=p.result) == 4
def test_buffer_meaningful_length_write_uses_count_arg():
    p = parse_line(0, '100 1.0 write(1, "abcdef", 6) = 6')
    assert buffer_meaningful_length(syscall_name="write", arg_index=1,
                                    args=['1', '"abcdef"', '6'], result=p.result) == 6
def test_buffer_meaningful_length_unknown_is_none():
    p = parse_line(0, '100 1.0 read(3, "abc", 9) = 3')
    assert buffer_meaningful_length(syscall_name="read", arg_index=0,
                                    args=['3', '"abc"', '9'], result=p.result) is None
