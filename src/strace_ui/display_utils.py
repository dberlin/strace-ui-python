"""display_utils: faithful Python port of OCaml display_utils.ml"""


def decode_strace_escapes(s: str) -> str:
    """Decode strace escape sequences into raw bytes.

    Handles \\n, \\t, \\r, \\\\, \\", \\0, \\xNN (hex), and plain chars.
    The \\x branch only applies when there are at least 2 chars after 'x'
    (OCaml guard: i+3 < len). If those 2 chars aren't valid hex, emits '\\' and
    advances 1. A '\\' with no following char -> literal backslash.
    """
    buf: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if i + 1 < n and s[i] == "\\":
            next_c = s[i + 1]
            if next_c == "n":
                buf.append("\n")
                i += 2
            elif next_c == "t":
                buf.append("\t")
                i += 2
            elif next_c == "r":
                buf.append("\r")
                i += 2
            elif next_c == "\\":
                buf.append("\\")
                i += 2
            elif next_c == '"':
                buf.append('"')
                i += 2
            elif next_c == "0":
                buf.append("\x00")
                i += 2
            elif next_c == "x" and i + 3 < n:
                # OCaml guard: i+3 < len means there are at least 2 chars after 'x'
                hex_str = s[i + 2 : i + 4]
                try:
                    val = int(hex_str, 16)
                    buf.append(chr(val))
                    i += 4
                except ValueError:
                    buf.append("\\")
                    i += 1
            else:
                buf.append("\\")
                buf.append(next_c)
                i += 2
        else:
            buf.append(s[i])
            i += 1
    return "".join(buf)


def split_escaped_at_byte(s: str, byte_count: int) -> tuple[str, str]:
    """Split strace-escaped string at a logical byte boundary.

    \\xNN counts as 1 byte (4 source chars), any other \\c counts as 1 byte
    (2 source chars), plain char counts as 1 byte (1 source char).
    Returns (s[:pos], s[pos:]).
    """
    n = len(s)
    byte_idx = 0
    i = 0
    while i < n and byte_idx < byte_count:
        if i + 1 < n and s[i] == "\\":
            next_c = s[i + 1]
            if next_c == "x":
                i += 4
            else:
                i += 2
        else:
            i += 1
        byte_idx += 1
    return s[:i], s[i:]


def strip_fd_annotations(arg: str) -> str:
    """Strip fd path annotations from an argument string.

    E.g. "3</usr/lib64/libc.so>" becomes "3".
    Only strips if the prefix before '<' is a digit, '-', or starts with AT_FDCWD.
    """
    if "<" in arg:
        num, _rest = arg.split("<", 1)
        num = num.rstrip()
        if (
            num
            and (
                num[0].isdigit()
                or num[0] == "-"
                or num.startswith("AT_FDCWD")
            )
        ):
            return num
        return arg
    return arg


def wrap_string(s: str, width: int) -> list[str]:
    """Wrap string into width-sized chunks."""
    if width <= 0 or len(s) <= width:
        return [s]
    lines: list[str] = []
    pos = 0
    n = len(s)
    while pos < n:
        chunk_len = min(width, n - pos)
        lines.append(s[pos : pos + chunk_len])
        pos += chunk_len
    return lines


def split_top_level(s: str, on: str) -> list[str]:
    """Split s on delimiter `on`, but only at depth 0 (not inside brackets or strings)."""
    result: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_string:
            current.append(c)
            if c == '"':
                k = i - 1
                backslashes = 0
                while k >= 0 and s[k] == "\\":
                    backslashes += 1
                    k -= 1
                if backslashes % 2 == 0:
                    in_string = False
        elif c == on and depth == 0:
            result.append("".join(current))
            current = []
        else:
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == '"':
                in_string = True
            current.append(c)
        i += 1
    if current:
        result.append("".join(current))
    return result
