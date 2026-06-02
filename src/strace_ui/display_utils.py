"""display_utils: faithful Python port of OCaml display_utils.ml"""


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
