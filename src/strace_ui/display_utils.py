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


def hexdump_bytes_per_line(width: int, total_bytes: int) -> int:
    """Compute best bytes-per-line for a hexdump given available width and total buffer length.

    Offset prefix: 4 hex digits for <=64KB, 8 otherwise.
    Line with N bytes and P-digit offset: (P+1) + 3*N + floor((N-1)/8) + 2 + N + 1
    = (P+4) + 4*N + (N-1)/8.
    """
    offset_digits = 8 if total_bytes > 0xFFFF else 4
    fixed = offset_digits + 1 + 1 + 1

    def try_n(n: int) -> int:
        line_width = fixed + (4 * n) + ((n - 1) // 8)
        if line_width > width:
            return try_n(n - 8)
        return n

    start = (((width - fixed) // 4 // 8) + 1) * 8
    max_fits = max(8, try_n(max(8, start)))
    # Pick smallest multiple-of-8 group count that covers total_bytes
    groups = (total_bytes + 7) // 8
    max_needed = max(1, groups) * 8
    return min(max_fits, max_needed)


def extract_ip_addresses(s: str) -> list[str]:
    """Extract all unique valid IPv4 addresses from a string, sorted ascending."""
    ips: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i].isdigit():
            start = i
            dot_count = 0
            while i < n and (s[i].isdigit() or s[i] == "."):
                if s[i] == ".":
                    dot_count += 1
                i += 1
            if dot_count == 3:
                candidate = s[start:i]
                parts = candidate.split(".")
                if (
                    len(parts) == 4
                    and all(
                        p
                        and p.isdigit()
                        and int(p) <= 255
                        for p in parts
                    )
                ):
                    ips.append(candidate)
        else:
            i += 1
    # Dedup and sort
    return sorted(set(ips))


def resolve_ips_in_string(s: str, dns_cache: dict[str, str]) -> str:
    """Replace all IP addresses with their resolved hostnames from dns_cache."""
    for ip, hostname in dns_cache.items():
        s = s.replace(ip, hostname)
    return s


def compact_args_raw(args_raw: str) -> str:
    """Produce compact args string for list view, stripping fd annotations."""
    if not args_raw.strip():
        return ""
    args = [a.strip() for a in split_top_level(args_raw, on=",")]
    compact_args = [strip_fd_annotations(a.strip()) for a in args]
    return ", ".join(compact_args)


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
