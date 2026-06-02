# strace-ui Python Port Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reimplement the OCaml `strace_ui` interactive strace viewer in Python + Textual with full feature parity.

**Architecture:** Preserve the original's Elm-style design: a pure, immutable `Model` with an `Action` union and a pure `apply_action(model, action) -> model` reducer, plus a separate render pass. All non-trivial logic lives in pure modules with no I/O and no Textual imports, so it is unit-tested with pytest (TDD). A thin Textual shell owns the terminal, holds the model, dispatches actions on keypresses, and runs async tasks (strace reader, man-page fetch, reverse-DNS).

**Tech Stack:** Python 3.11+, [Textual](https://textual.textualize.io/) (brings Rich), `pytest`. Runtime needs `strace` and `man` on `PATH`.

**Reference source:** The OCaml original is at `/home/dannyb/sources/strace_ui/src/`. Each pure module is a faithful translation of the correspondingly-named `.ml` file. When in doubt about exact behavior, read the OCaml — but the **pytest tests in this plan are the authoritative behavioral contract**. Translate the OCaml so the tests pass.

**Spec:** `docs/superpowers/specs/2026-06-02-strace-ui-python-port-design.md`

**Conventions for every task below:**
- TDD: write the failing test first, run it to watch it fail, implement minimally, run it to watch it pass, commit.
- Run a single test with `pytest tests/test_X.py::test_name -v`; run a module's suite with `pytest tests/test_X.py -v`.
- Commit messages use Conventional Commits (`feat:`, `test:`, `chore:`).
- Use `@superpowers:test-driven-development` discipline throughout.
- Data classes use `@dataclass(frozen=True)` unless the field set genuinely needs mutation; tagged unions use frozen dataclasses + `isinstance` dispatch (see Task 2 for the established pattern — follow it everywhere).

---

## Chunk 1: Scaffold, display_utils, value

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/strace_ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "strace-ui"
version = "0.1.0"
description = "Interactive strace viewer (Python port of janestreet/strace_ui)"
requires-python = ">=3.11"
dependencies = ["textual>=0.60"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
strace-ui = "strace_ui.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty `src/strace_ui/__init__.py` and `tests/__init__.py`**

Both files contain only a single comment line, e.g. `# strace_ui package`.

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
build/
dist/
.venv/
```

- [ ] **Step 4: Create and activate a venv, install dev deps**

Run:
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```
Expected: installs textual + pytest, `strace-ui` script registered.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `pytest -q`
Expected: `no tests ran` (exit 0 or 5 — both fine).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: project scaffold (pyproject, package layout, pytest config)"
```

---

### Task 2: `display_utils.split_top_level`

This is the foundational primitive used by the parser and value modules. **Establish the module here.**

**Files:**
- Create: `src/strace_ui/display_utils.py`
- Test: `tests/test_display_utils.py`

Reference: `/home/dannyb/sources/strace_ui/src/display_utils.ml` lines 173-210.

- [ ] **Step 1: Write the failing test**

```python
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
    # An escaped quote does not end the string; the comma inside stays nested.
    assert split_top_level(r'"a\",b", c', on=",") == [r'"a\",b"', " c"]

def test_split_top_level_empty():
    assert split_top_level("", on=",") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_display_utils.py -v`
Expected: FAIL (ModuleNotFoundError / ImportError).

- [ ] **Step 3: Implement `split_top_level`**

Port the OCaml char-scanner exactly. Algorithm: walk chars; track `depth` for `()[]{}` and an `in_string` flag for `"`. A `"` toggles string mode unless it is escaped (count preceding consecutive backslashes; even count = real quote). Split on `on` only when `depth == 0` and not in a string. Push the final buffer if non-empty. Empty input → `[]`.

```python
def split_top_level(s: str, on: str) -> list[str]:
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
                # even number of preceding backslashes => real closing quote
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_display_utils.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/display_utils.py tests/test_display_utils.py
git commit -m "feat: display_utils.split_top_level"
```

---

### Task 3: `display_utils` escape/byte/string helpers

**Files:**
- Modify: `src/strace_ui/display_utils.py`
- Modify: `tests/test_display_utils.py`

Reference: `display_utils.ml` lines 6-51 (`decode_strace_escapes`), 78-94 (`split_escaped_at_byte`), 98-125 (`strip_fd_annotations`, `wrap_string`).

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.display_utils import (
    decode_strace_escapes, split_escaped_at_byte, strip_fd_annotations, wrap_string,
)

def test_decode_basic_escapes():
    assert decode_strace_escapes(r"a\nb\tc") == "a\nb\tc"

def test_decode_hex_escape():
    assert decode_strace_escapes(r"\x41\x42") == "AB"

def test_decode_null_and_backslash_and_quote():
    assert decode_strace_escapes(r"\0\\\"") == "\x00\\\""

def test_decode_dangling_backslash_kept():
    # A trailing lone backslash is preserved literally.
    assert decode_strace_escapes("a\\") == "a\\"

def test_split_escaped_at_byte_counts_hex_as_one():
    # 3 logical bytes: \x41, B, \x43
    meaningful, trailing = split_escaped_at_byte(r"\x41B\x43", byte_count=2)
    assert meaningful == r"\x41B"
    assert trailing == r"\x43"

def test_strip_fd_annotations_numeric():
    assert strip_fd_annotations("3</usr/lib/libc.so>") == "3"

def test_strip_fd_annotations_at_fdcwd():
    assert strip_fd_annotations("AT_FDCWD</home>") == "AT_FDCWD"

def test_strip_fd_annotations_non_numeric_unchanged():
    assert strip_fd_annotations("AF_INET<x>") == "AF_INET<x>"

def test_wrap_string():
    assert wrap_string("abcdef", width=2) == ["ab", "cd", "ef"]
    assert wrap_string("abc", width=10) == ["abc"]
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_display_utils.py -v` → FAIL (ImportError on new names).

- [ ] **Step 3: Implement the four functions**

`decode_strace_escapes`: walk chars; on `\` look at next char: `n`→`\n`, `t`→`\t`, `r`→`\r`, `\\`→`\\`, `"`→`"`, `0`→`\x00`, `x`+2 hex digits→that byte (if the 2 chars aren't valid hex, emit a literal backslash and advance 1), any other → emit backslash + that char. A `\` with no following char → literal backslash. **Boundary detail (match OCaml exactly):** the `\x` branch only applies when there are at least 2 chars after the `x` (OCaml guard `i+3 < len`); when `\x` is too close to end-of-string, it falls through to the generic "any other" branch (emit `\` + `x`), not the invalid-hex branch. (Note: decoded bytes are produced as a `str`; `chr(n)` for the hex byte, matching the OCaml which builds an OCaml string of bytes. For hexdump rendering these are treated as code points 0-255.)

`split_escaped_at_byte(s, byte_count)`: walk logical bytes; `\xNN` consumes 4 source chars, any other `\c` consumes 2, plain char consumes 1; stop after `byte_count` logical bytes; return `(s[:split_pos], s[split_pos:])`.

`strip_fd_annotations(arg)`: if there's a `<`, take the part before it, rstrip; if that part is non-empty and starts with a digit or `-` or is prefixed `AT_FDCWD`, return it; else return the original arg. No `<` → return arg.

`wrap_string(s, width)`: if `width <= 0` or `len(s) <= width` → `[s]`; else slice into `width`-sized chunks.

(Implement faithfully from the OCaml; the tests pin the edge cases.)

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_display_utils.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/display_utils.py tests/test_display_utils.py
git commit -m "feat: display_utils escape/byte/fd/wrap helpers"
```

---

### Task 4: `display_utils` IP + hexdump-layout + compact helpers

**Files:**
- Modify: `src/strace_ui/display_utils.py`
- Modify: `tests/test_display_utils.py`

Reference: `display_utils.ml` lines 59-74 (`hexdump_bytes_per_line`), 129-169 (IP helpers), 213-223 (`compact_args_raw`).

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.display_utils import (
    extract_ip_addresses, resolve_ips_in_string, hexdump_bytes_per_line, compact_args_raw,
)

def test_extract_ip_addresses_dedups_and_sorts():
    s = "5<UDP:[30.32.177.12:34003->30.10.253.70:0]> 30.32.177.12"
    assert extract_ip_addresses(s) == ["30.10.253.70", "30.32.177.12"]

def test_extract_ip_rejects_octet_over_255():
    assert extract_ip_addresses("999.1.1.1") == []

def test_resolve_ips_in_string():
    s = "3<TCP:[10.0.0.1:80->10.0.0.2:443]>"
    cache = {"10.0.0.1": "foo", "10.0.0.2": "bar"}
    assert resolve_ips_in_string(s, cache) == "3<TCP:[foo:80->bar:443]>"

def test_hexdump_bytes_per_line_multiple_of_8():
    n = hexdump_bytes_per_line(width=80, total_bytes=256)
    assert n % 8 == 0 and n >= 8

def test_hexdump_bytes_per_line_small_buffer_caps_to_need():
    # 3 bytes need only one group of 8.
    assert hexdump_bytes_per_line(width=200, total_bytes=3) == 8

def test_compact_args_strips_fd_annotations():
    assert compact_args_raw('3</a/b>, "hi", 0x5') == '3, "hi", 0x5'
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`hexdump_bytes_per_line(width, total_bytes)`: port the OCaml math exactly:
```
offset_digits = 8 if total_bytes > 0xFFFF else 4
fixed = offset_digits + 1 + 1 + 1
# try_n decreases by 8 until line_width fits: line_width = fixed + 4*n + (n-1)//8
start = ((width - fixed)//4//8 + 1) * 8
max_fits = max(8, <largest n=start,start-8,... with line_width<=width>)   # floored at 8
max_needed = max(1, (total_bytes+7)//8) * 8
return min(max_fits, max_needed)
```
Translate `try_n` as a loop starting at `max(8, start)`, decrementing by 8 while `line_width > width`, never below 8.

`extract_ip_addresses(s)`: scan for runs of digits-and-dots beginning at a digit; if a run has exactly 3 dots and splits into 4 non-empty integer parts each ≤ 255, it's an IP. Dedup and sort ascending (string sort, matching OCaml `dedup_and_sort ~compare:String.compare`).

`resolve_ips_in_string(s, dns_cache)`: for each `(ip, hostname)` in the cache, `s = s.replace(ip, hostname)`. (Order: OCaml folds over a map; since replacements are IP→hostname and IPs are distinct substrings, order is immaterial for the tested cases. Iterate the dict as-is.)

`compact_args_raw(args_raw)`: if blank → `""`; else `split_top_level(args_raw, ",")`, strip each, `strip_fd_annotations` each, join with `", "`.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/display_utils.py tests/test_display_utils.py
git commit -m "feat: display_utils IP, hexdump-layout, compact helpers"
```

---

### Task 5: `value` — strace value tree parser

**Files:**
- Create: `src/strace_ui/value.py`
- Test: `tests/test_value.py`

Reference: `/home/dannyb/sources/strace_ui/src/strace_value.ml`.

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the value tree + parse**

Define five frozen dataclasses as the tagged union (this is the **established union pattern** for the whole project):

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Atom:
    value: str

@dataclass(frozen=True)
class String:
    value: str

@dataclass(frozen=True)
class Call:
    name: str
    arg: str

@dataclass(frozen=True)
class Struct:
    fields: list  # list[tuple[str, Value]]

@dataclass(frozen=True)
class Array:
    elems: list  # list[Value]

Value = Atom | String | Struct | Call | Array
```

> **Note on equality with lists:** the tests compare `Struct([...])`/`Array([...])` using list literals. `Struct`/`Array` store the sequence as a plain `list` field on a `@dataclass(frozen=True)` (frozen blocks reassigning the field, not mutating the list — acceptable here), so dataclass `==` compares the lists element-by-element.

`parse(s)` (port `strace_value.ml` lines 20-78): strip; empty → `Atom("")`; starts with `"` → strip one leading/trailing quote → `String`; starts with `{` → strip braces, `split_top_level(inner, ",")`, each field: strip, skip empty, split on first `=` → `(key.strip(), parse(value.strip()))`, no `=` → `(field, Atom(""))` → `Struct`; starts with `[` → strip brackets, empty inner → `Array([])` else split + parse each → `Array`; else if `name(arg)` shape (split on first `(`, non-empty name, stripped rest ends with `)`) → `Call(name, inner)`; else `Atom(s)`.

Use `from strace_ui.display_utils import split_top_level`.

`to_lines` and the generic `fold_tree`: port `strace_value.ml` lines 91-191. Implement `fold_tree` with the six callbacks (`emit`, `render_atom`, `render_string`, `render_call`, `render_prefix`, `render_prefix_with_value`, `render_prefix_with_multi`) and the `├─`/`╰─` prefix + `│ `/`  ` child-indent logic, recursing into struct/array children and using the scalar paths for leaves. Then `to_lines(t, render_string=lambda s: [f'"{s}"'])` builds the string list exactly as the OCaml `to_lines` does.

Pay attention to the multi-line string path (`render_prefix_with_multi`): single view → inline `prefix+key = view`; empty key → first inline then rest at child indent; else key on its own line then views at child indent.

- [ ] **Step 4: Run to verify pass** (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/value.py tests/test_value.py
git commit -m "feat: strace value tree parser and tree renderer"
```

---

## Chunk 2: parser, schema, pid_map

### Task 6: `parser` — Result + ParsedLine types and helpers

**Files:**
- Create: `src/strace_ui/parser.py`
- Test: `tests/test_parser.py`

Reference: `/home/dannyb/sources/strace_ui/src/strace_parser.ml`.

- [ ] **Step 1: Write failing tests for the small helpers first**

```python
from strace_ui.parser import (
    ValueResult, ErrorResult, Unfinished, Resumed, Signal, Exit,
    split_args, extract_fd_number, extract_return_int,
)

def test_split_args_basic():
    assert split_args('3, "hi", {x=1, y=2}') == ['3', '"hi"', '{x=1, y=2}']

def test_split_args_empty():
    assert split_args("") == []

def test_extract_fd_number():
    assert extract_fd_number("3</a>") == 3
    assert extract_fd_number("3") == 3
    assert extract_fd_number("AT_FDCWD") is None
    assert extract_fd_number("foo") is None

def test_extract_return_int_plain():
    assert extract_return_int(ValueResult("0")) == 0

def test_extract_return_int_with_annotation():
    assert extract_return_int(ValueResult("3<socket:[123]>")) == 3

def test_extract_return_int_hex():
    assert extract_return_int(ValueResult("0x7f6")) == 0x7f6

def test_extract_return_int_with_trailing_text():
    assert extract_return_int(ValueResult("0 (Timeout)")) == 0

def test_extract_return_int_error_is_none():
    assert extract_return_int(ErrorResult("ENOENT", "No such file")) is None
```

Define the Result union as frozen dataclasses: `ValueResult(value:str)`, `ErrorResult(errno:str, description:str)`, `Unfinished()`, `Resumed(inner:Result)`, `Signal(text:str)`, `Exit(text:str)`. (Name `ValueResult`/`ErrorResult` to avoid clashing with builtins.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the union + the three helpers**

- `split_args(raw)`: blank → `[]`; else `split_top_level(raw, ",")` each stripped.
- `extract_fd_number(arg)`: strip; if `<` present, int-or-None of part before `<`; else `AT_FDCWD` prefix → None, else int-or-None of whole.
- `extract_return_int(result)`: only `ValueResult`; strip; `<` present → int before `<`; `0x` prefix → int base 16 (guard exceptions → None); else int before first space, else whole; non-Value → None. Use a safe `int_or_none` helper.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/parser.py tests/test_parser.py
git commit -m "feat: parser result types and fd/return/arg helpers"
```

---

### Task 7: `parser.parse_line` — full line parser

**Files:**
- Modify: `src/strace_ui/parser.py`
- Modify: `tests/test_parser.py`

Reference: `strace_parser.ml` lines 31-241.

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.parser import parse_line, ValueResult, ErrorResult, Unfinished, Resumed, Signal, Exit

def test_parse_normal():
    line = "1234 1700000000.123456 read(3, \"abc\", 100) = 3 <0.000123>"
    p = parse_line(0, line)
    assert p.pid == 1234
    assert abs(p.timestamp - 1700000000.123456) < 1e-6
    assert p.syscall_name == "read"
    assert p.args_raw == '3, "abc", 100'
    assert p.result == ValueResult("3")
    assert abs(p.duration - 0.000123) < 1e-9

def test_parse_error():
    p = parse_line(1, '5 1.0 access(\"/x\", F_OK) = -1 ENOENT (No such file or directory)')
    assert p.result == ErrorResult("ENOENT", "No such file or directory")

def test_parse_unfinished():
    p = parse_line(2, '7 2.5 recvmsg(3, {msg_name=...} <unfinished ...>')
    assert isinstance(p.result, Unfinished)
    assert p.args_raw == "3, {msg_name=...}"

def test_parse_resumed():
    p = parse_line(3, '7 2.6 <... recvmsg resumed>, 0) = 64 <0.0001>')
    assert p.syscall_name == "recvmsg"
    assert isinstance(p.result, Resumed)
    assert p.result.inner == ValueResult("64")
    assert abs(p.duration - 0.0001) < 1e-9

def test_parse_signal():
    p = parse_line(4, "9 3.0 --- SIGCHLD {si_signo=SIGCHLD} ---")
    assert p.syscall_name == "<<signal>>"
    assert isinstance(p.result, Signal)

def test_parse_exit():
    p = parse_line(5, "9 3.1 +++ exited with 0 +++")
    assert p.syscall_name == "<<exit>>"
    assert isinstance(p.result, Exit)

def test_parse_unparseable_returns_none():
    assert parse_line(6, "not a strace line") is None

def test_parse_nested_parens_in_args():
    p = parse_line(7, '1 1.0 ioctl(3, TCGETS, {c_iflag=ICRNL (foo), c_oflag=0}) = 0')
    assert p.args_raw == "3, TCGETS, {c_iflag=ICRNL (foo), c_oflag=0}"
    assert p.result == ValueResult("0")
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `ParsedLine` dataclass + `parse_line` + `merge_resumed`**

`ParsedLine` frozen dataclass: `index, pid, timestamp, syscall_name, args_raw, result, duration, raw_line`.

Port the parser. The OCaml uses the Angstrom combinator library; in Python implement it directly:
1. `line = raw.lstrip()`.
2. Match leading `pid` (digits), then whitespace, then `timestamp` (float `digits.digits`), then whitespace. If this prefix doesn't match, return `None`.
3. On the remainder, dispatch:
   - starts with `---` → `Signal(rest)`, name `<<signal>>`.
   - starts with `+++` → `Exit(rest)`, name `<<exit>>`.
   - starts with `<... ` → resumed: parse name (non-space) then ` resumed>`; split the text after `>` on `") = "` to separate trailing args from result; parse result+duration on the result part; `Resumed(result)`.
   - else → normal: name = chars up to `(`; if the rstripped remainder ends with `<unfinished ...>`, strip it → `Unfinished`, no duration; else find the matching close paren (paren-depth + quote-skip scanner — reuse the same logic as `split_top_level`'s string handling), `args_raw` = inside, then parse result+duration from after the `)`.

Helpers to port: `extract_duration_from_value(s)` (rsplit on `<`, if suffix `>` and the inner parses as float → strip it as duration), `parse_result` + `result_and_duration` (Value extracts trailing duration from value; Error consumes trailing duration; other → no duration).

`merge_resumed(original, resumed)`: port lines 243-266 (join args dropping a trailing comma on the left, unwrap `Resumed`, take resumed duration, append raw lines with ` ... `).

Write the close-paren scanner as a small function returning `(args_inside, index_after_close)`.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Add a `merge_resumed` test, run, then commit**

```python
def test_merge_resumed():
    orig = parse_line(0, '7 2.5 recvmsg(3, {a=1} <unfinished ...>')
    res = parse_line(1, '7 2.6 <... recvmsg resumed>, 0) = 64 <0.0001>')
    merged = merge_resumed(orig, res)
    assert merged.args_raw == "3, {a=1}, 0"
    assert merged.result == ValueResult("64")
    assert abs(merged.duration - 0.0001) < 1e-9
```

```bash
git add src/strace_ui/parser.py tests/test_parser.py
git commit -m "feat: parser.parse_line and merge_resumed"
```

---

### Task 8: `schema` — types, Family, best_signature (structure)

**Files:**
- Create: `src/strace_ui/schema.py`
- Test: `tests/test_schema.py`

Reference: `/home/dannyb/sources/strace_ui/src/syscall_schema.ml`.

- [ ] **Step 1: Write failing tests for the type machinery and families**

```python
from strace_ui.schema import (
    ArgType, ReturnType, ArgSpec, Signature, SyscallInfo, Family, lookup,
)

def test_argtype_is_fd():
    assert ArgType.FILE_DESCRIPTOR.is_file_descriptor()
    assert not ArgType.PATH.is_file_descriptor()

def test_returntype_is_fd():
    assert ReturnType.FILE_DESCRIPTOR.is_file_descriptor()
    assert not ReturnType.INT.is_file_descriptor()

def test_best_signature_exact_match():
    info = SyscallInfo(
        name="x", brief="", man_section=2,
        signatures=[
            Signature("a", [ArgSpec("p", ArgType.INT)], ReturnType.INT),
            Signature("b", [ArgSpec("p", ArgType.INT), ArgSpec("q", ArgType.INT)], ReturnType.INT),
        ],
    )
    assert info.best_signature(arg_count=2).c_signature == "b"

def test_best_signature_fallback_to_most_args():
    info = SyscallInfo(
        name="x", brief="", man_section=2,
        signatures=[
            Signature("a", [ArgSpec("p", ArgType.INT)], ReturnType.INT),
            Signature("b", [ArgSpec("p", ArgType.INT), ArgSpec("q", ArgType.INT)], ReturnType.INT),
        ],
    )
    assert info.best_signature(arg_count=5).c_signature == "b"

def test_family_display_strings():
    assert Family.NETWORK.to_display_string() == "%net"
    assert Family.ALL.to_display_string() == "all"
    assert Family.DESC.to_display_string() == "%desc"

def test_family_net_includes():
    assert Family.NETWORK.includes("socket")
    assert not Family.NETWORK.includes("read")

def test_family_all_includes_everything():
    assert Family.ALL.includes("anything")
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the type machinery + Family**

- `ArgType`: the 15 named kinds **plus an `OTHER(str)` variant that carries a payload string**. This payload IS used by the table — `poll` and `ppoll` use `Arg_type.Other "nfds_t"` (syscall_schema.ml:767, 778) — so it must be representable; a bare `enum.Enum` cannot hold the payload. **Use this design:** a frozen dataclass `ArgType(kind: str, other: str | None = None)` with module-level singletons for the 15 fixed kinds (`FILE_DESCRIPTOR = ArgType("file_descriptor")`, `PATH = ArgType("path")`, …, `MODE = ArgType("mode")`) and a helper `ArgType.other(s) -> ArgType` returning `ArgType("other", s)`. Add `is_file_descriptor(self) -> bool` returning `self.kind == "file_descriptor"`. The fixed singletons compare by identity *and* value (frozen dataclass `==`); tests use `is ArgType.FILE_DESCRIPTOR` which holds for the singletons.
- `ReturnType`: `enum.Enum` (FILE_DESCRIPTOR, INT, SSIZE, POINTER, VOID, PID, OFF) with `is_file_descriptor`.
- `ArgSpec(name, arg_type)`, `Signature(c_signature, args, return_type)` frozen dataclasses.
- `SyscallInfo(name, signatures, brief, man_section)` with `best_signature(arg_count)`: exact arg-count match else the signature with the most args (else first).
- `Family`: `enum.Enum` (ALL, DESC, FILE, MEMORY, NETWORK, PROCESS, SIGNAL, IPC) with `to_display_string()` and `includes(syscall_name)`. ALL → always True; IPC → empty list (False). The membership lists for DESC/FILE/MEMORY/NETWORK/PROCESS/SIGNAL are ported verbatim from `syscall_schema.ml` lines 1169-1325 — store each as a module-level `frozenset`.
- `lookup(name)` returns `KNOWN_SYSCALLS.get(name)` (table filled in next task; for now `KNOWN_SYSCALLS = {}` so import works).

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/schema.py tests/test_schema.py
git commit -m "feat: schema types, Family classification, best_signature"
```

---

### Task 9: `schema` — port the 119-syscall table

**Files:**
- Modify: `src/strace_ui/schema.py`
- Modify: `tests/test_schema.py`

Reference: `syscall_schema.ml` lines 91-1142 (the `known_syscalls` table).

- [ ] **Step 1: Write failing tests asserting a representative sample**

```python
from strace_ui.schema import lookup, ArgType, ReturnType

def test_read_entry():
    info = lookup("read")
    assert info is not None
    sig = info.signatures[0]
    assert sig.c_signature == "ssize_t read(int fd , void * buf , size_t count )"
    assert [a.name for a in sig.args] == ["fd", "buf", "count"]
    assert sig.args[0].arg_type is ArgType.FILE_DESCRIPTOR
    assert sig.args[1].arg_type is ArgType.BUFFER
    assert sig.return_type is ReturnType.SSIZE
    assert info.brief == "Read from a file descriptor"
    assert info.man_section == 2

def test_table_size():
    # The OCaml table has 119 entries.
    from strace_ui.schema import KNOWN_SYSCALLS
    assert len(KNOWN_SYSCALLS) == 119

def test_openat_is_fd_return():
    assert lookup("openat").signatures[0].return_type is ReturnType.FILE_DESCRIPTOR

def test_socket_lookup():
    assert lookup("socket") is not None

def test_poll_uses_other_argtype():
    # poll's 2nd arg is `Arg_type.Other "nfds_t"` in the OCaml table.
    nfds = lookup("poll").signatures[0].args[1].arg_type
    assert nfds.kind == "other" and nfds.other == "nfds_t"

def test_unknown_lookup_none():
    assert lookup("definitely_not_a_syscall") is None
```

- [ ] **Step 2: Run to verify failure** (table empty / size mismatch).

- [ ] **Step 3: Port the table**

Translate every entry from the OCaml `known_syscalls` alist into a Python `dict[str, SyscallInfo]` named `KNOWN_SYSCALLS`. The OCaml uses short aliases (`fd`, `path`, `ptr`, `int_`, `uint`, `size`, `off`, `flags`, `buf`, `pid`, `sig_`, `mode`, `struct_`, `sockaddr`) — map each to the corresponding `ArgType` singleton. The inline form `Arg_type.Other "nfds_t"` (used by `poll`/`ppoll`) maps to `ArgType.other("nfds_t")`. Use a small local helper to keep it terse:

```python
def _a(name, t): return ArgSpec(name, t)
def _e(name, c_signature, args, return_type, brief, man_section):
    return name, SyscallInfo(name, [Signature(c_signature, args, return_type)], brief, man_section)
def _em(name, signatures, brief, man_section):
    return name, SyscallInfo(name, signatures, brief, man_section)
```

This is mechanical but must be exact. **Work in sub-batches and keep a running count** so the final `len == 119`. Read the OCaml entries directly; do not paraphrase signatures, briefs, or man sections. Watch for the few `entry_multi` cases (multiple signatures) and port all their signatures.

> Optional accelerator (allowed): write a throwaway script that regex-extracts the entries from `syscall_schema.ml` and emits Python, then hand-verify a sample. The throwaway script must not be committed.

- [ ] **Step 4: Run to verify pass** (sample + size + fd-return).

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/schema.py tests/test_schema.py
git commit -m "feat: port 119-syscall schema table"
```

---

### Task 10: `pid_map`

**Files:**
- Create: `src/strace_ui/pid_map.py`
- Test: `tests/test_pid_map.py`

Reference: `/home/dannyb/sources/strace_ui/src/pid_map.ml`.

- [ ] **Step 1: Write failing tests**

```python
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
    assert m.display_width() == 1           # no pids -> 1
    for p in range(15):
        m = m.register(1000 + p)            # ids 0..14 -> max id 14 -> width 2
    assert m.display_width() == 2

def test_summary_process_vs_thread():
    m = PidMap.empty().register(5)
    m = m.set_info(5, PidInfo(cmdline="ping localhost", thread_name="ping", is_thread=False))
    assert m.summary(5) == "ping localhost"
    m = m.set_info(5, PidInfo(cmdline="ping localhost", thread_name="worker", is_thread=True))
    assert m.summary(5) == "thread: worker (ping localhost)"

def test_summary_unknown_none():
    assert PidMap.empty().summary(5) is None
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`PidInfo` frozen dataclass `(cmdline, thread_name, is_thread)`. `PidMap` immutable-style dataclass `(pid_to_short: dict, next_id: int, infos: dict)` with classmethod `empty()`, and methods `register`, `short_id`, `display_width`, `info`, `set_info`, `summary` — each returning a new `PidMap` where it mutates (copy the dicts). Port semantics from the OCaml exactly (display_width: `1` if no ids, else `len(str(next_id-1))`).

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/pid_map.py tests/test_pid_map.py
git commit -m "feat: pid_map short-id mapping and summaries"
```

---

## Chunk 3: fd_tracker, filter, filter_editor

### Task 11: `fd_tracker`

**Files:**
- Create: `src/strace_ui/fd_tracker.py`
- Test: `tests/test_fd_tracker.py`

Reference: `/home/dannyb/sources/strace_ui/src/fd_tracker.ml`.

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.parser import parse_line
from strace_ui.fd_tracker import FdTracker, FdId

def _line(idx, text):
    p = parse_line(idx, text)
    assert p is not None
    return p

def test_open_creates_fd_with_origin():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3'))
    fid = t.resolve_fd(pid=100, fd_number=3)
    assert fid == FdId(source_pid=100, fd_number=3, generation=0)
    origin = t.lookup_origin(fid)
    assert origin.syscall_name == "openat"
    assert '"/etc/passwd"' in origin.summary
    assert origin.syscall_index == 0

def test_close_bumps_generation():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 close(3) = 0'))
    assert t.resolve_fd(pid=100, fd_number=3) is None
    # reopen -> generation 1
    t = t.update(_line(2, '100 1.2 openat(AT_FDCWD, "/b", O_RDONLY) = 3'))
    assert t.resolve_fd(pid=100, fd_number=3) == FdId(100, 3, 1)

def test_dup2_implicit_close_bumps_generation():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 5'))
    # dup2 onto an occupied slot 5 implicitly closes the old fd -> generation 1
    t = t.update(_line(1, '100 1.1 dup2(4, 5) = 5'))
    assert t.resolve_fd(100, 5) == FdId(100, 5, 1)

def test_pipe_pair_records_both():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 pipe2([3, 4], O_CLOEXEC) = 0'))
    assert t.resolve_fd(100, 3) == FdId(100, 3, 0)
    assert t.resolve_fd(100, 4) == FdId(100, 4, 0)

def test_fork_inherits_fd_table():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 clone(child_stack=NULL) = 200'))
    # child 200 inherits the same FdId for fd 3
    assert t.resolve_fd(200, 3) == FdId(source_pid=100, fd_number=3, generation=0)
    assert t.parent_pid(pid=200) == 100

def test_resolve_or_default_pretrace_fd():
    t = FdTracker.empty()
    # fd never tracked -> synthesize generation 0
    assert t.resolve_fd_or_default(pid=100, fd_number=7) == FdId(100, 7, 0)

def test_resolve_or_default_closed_is_none():
    t = FdTracker.empty()
    t = t.update(_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3'))
    t = t.update(_line(1, '100 1.1 close(3) = 0'))
    # previously tracked but closed -> None (not synthesized)
    assert t.resolve_fd_or_default(pid=100, fd_number=3) is None
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `FdTracker`**

`FdId` frozen dataclass `(source_pid, fd_number, generation)` — hashable, orderable (`order=True`) for use as dict keys and in sorted dedup. `FdOrigin` frozen dataclass `(syscall_index, syscall_name, summary)`.

`FdTracker` immutable-style dataclass with the four maps from the spec. Port `update`, `resolve_fd`, `resolve_fd_or_default`, `lookup_origin`, `parent_pid`, `lookup`, plus the constant syscall sets and `extract_fd_pair` (depth-aware bracket scan), exactly from the OCaml. Each `update` branch (create / pair / fork / close) returns a new tracker with copied dicts.

Key details to preserve:
- Only successful `ValueResult` results mutate the tracker.
- fd-creating: negative return → no-op; summary formatting per-syscall (open/openat → first quoted arg; dup* → `name(args) = fd`; else `name(args)`); occupied slot → bump generation before recording.
- fork: copy parent's fd table to the child; copy parent's generation counters into the child's keys.
- close: bump `(pid, fd)` generation and remove from table.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/fd_tracker.py tests/test_fd_tracker.py
git commit -m "feat: fd_tracker with generations, fork inheritance, provenance"
```

---

### Task 12: `filter` — parse + to_string

**Files:**
- Create: `src/strace_ui/filter.py`
- Test: `tests/test_filter.py`

Reference: `/home/dannyb/sources/strace_ui/src/syscall_filter.ml`.

- [ ] **Step 1: Write failing tests for parsing/serialization**

```python
from strace_ui.filter import (
    parse, to_display_string, to_normalized_string, normalize,
    IncludeFamily, IncludeSyscall, ExcludeSyscall, FilterPid, ExcludePid,
    FilterFd, FilterRelatedPid, Regex,
)
from strace_ui.schema import Family

def test_parse_family():
    assert parse("%net") == [IncludeFamily(Family.NETWORK)]

def test_parse_include_exclude_syscall():
    assert parse("read -write !futex +open") == [
        IncludeSyscall("read"), ExcludeSyscall("write"),
        ExcludeSyscall("futex"), IncludeSyscall("open"),
    ]

def test_parse_pid_terms():
    assert parse("pid:5 !pid:9 rel:3") == [FilterPid(5), ExcludePid(9), FilterRelatedPid(3)]

def test_parse_fd_terms():
    assert parse("fd:3 fd:4.2") == [FilterFd(3, None), FilterFd(4, 2)]

def test_parse_regex():
    terms = parse("/foo.*bar/")
    assert len(terms) == 1 and isinstance(terms[0], Regex)
    assert terms[0].matches("xxfooZZbar")

def test_to_display_string_empty_is_all():
    assert to_display_string([]) == "all"

def test_normalize_roundtrip():
    assert normalize("  %net   read  -write ") == "%net read -write"

def test_empty_regex_dropped():
    assert parse("//") == []
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement the Term union, tokenizer, parser, serializers**

Define the eight term dataclasses (frozen). `FilterFd` must have field order `(fd_number: int, generation: int | None)` so the Task 12 test's positional construction `FilterFd(3, None)` / `FilterFd(4, 2)` is correct. `Regex` wraps a compiled `re.Pattern`; give it a `.matches(s)` helper and `.pattern` property; implement `__eq__` by compiled pattern string so tests comparing `Regex` instances work (or compare via `to_normalized_string`). For equality in `test_parse_regex` we only check `isinstance` + `matches`, so a value-based `__eq__` is optional but recommended.

Port `tokenize` (special `/regex/` handling: a regex token runs to the next unescaped `/` or end; everything else splits on spaces), `parse_simple_token`, `parse_regex_body` (backslash-slash → slash, other backslash kept), `make_regex_term` (invalid pattern → `re.escape` literal; empty → dropped), `parse`, `to_normalized_string`, `to_display_string`, `normalize`, and the `add_*` helpers.

Regex substitution note (from spec): use Python `re`; on `re.error`, fall back to `re.compile(re.escape(pattern))`.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/filter.py tests/test_filter.py
git commit -m "feat: filter expression parsing and serialization"
```

---

### Task 13: `filter.passes` + relationship logic

**Files:**
- Modify: `src/strace_ui/filter.py`
- Modify: `tests/test_filter.py`

Reference: `syscall_filter.ml` lines 227-333.

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.filter import parse, passes, SyscallInfo as FInfo  # define a small info struct
from strace_ui.fd_tracker import FdTracker, FdId
from strace_ui.parser import parse_line

def _info(name, pid, fd_ids=(), raw=""):
    return FInfo(syscall_name=name, pid=pid, fd_ids=list(fd_ids), raw_line=raw or name)

def test_passes_empty_is_all():
    assert passes([], _info("read", 1), fd_tracker=FdTracker.empty())

def test_passes_inclusion_only_matches():
    f = parse("read")
    assert passes(f, _info("read", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("write", 1), fd_tracker=FdTracker.empty())

def test_passes_exclusion_only():
    f = parse("-write")
    assert passes(f, _info("read", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("write", 1), fd_tracker=FdTracker.empty())

def test_passes_family():
    f = parse("%net")
    assert passes(f, _info("socket", 1), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 1), fd_tracker=FdTracker.empty())

def test_passes_pid_filter():
    f = parse("pid:5")
    assert passes(f, _info("read", 5), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 6), fd_tracker=FdTracker.empty())

def test_passes_fd_filter_with_generation():
    f = parse("fd:3.1")
    ok = _info("read", 1, fd_ids=[FdId(1, 3, 1)])
    no = _info("read", 1, fd_ids=[FdId(1, 3, 0)])
    assert passes(f, ok, fd_tracker=FdTracker.empty())
    assert not passes(f, no, fd_tracker=FdTracker.empty())

def test_passes_regex_on_raw_line():
    f = parse("/EAGAIN/")
    assert passes(f, _info("read", 1, raw="read(3) = -1 EAGAIN"), fd_tracker=FdTracker.empty())
    assert not passes(f, _info("read", 1, raw="read(3) = 5"), fd_tracker=FdTracker.empty())

def test_passes_related_pid_via_fork():
    t = FdTracker.empty()
    t = t.update(parse_line(0, '100 1.0 clone(child_stack=NULL) = 200'))
    f = parse("rel:100")
    assert passes(f, _info("read", 200), fd_tracker=t)   # child related to ancestor
    assert passes(f, _info("read", 100), fd_tracker=t)
    assert not passes(f, _info("read", 999), fd_tracker=t)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `passes`, `is_ancestor`, `is_related`, and the `SyscallInfo` carrier**

Add a small frozen dataclass (the test imports it as `SyscallInfo`; name it `SyscallInfo` in `filter.py`, distinct from `schema.SyscallInfo`) `(syscall_name, pid, fd_ids, raw_line)`. Port `is_ancestor` (walk parent_pid chain with a visited set), `is_related` (equal or ancestor either direction), and `passes` with the exact rule order: empty → True; compute `has_inclusions`, `included`, `excluded`, `pid_ok`, `fd_ok`, `regex_ok`; result = `included and not excluded and pid_ok and fd_ok and regex_ok`.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/filter.py tests/test_filter.py
git commit -m "feat: filter.passes with pid/fd/regex/relationship evaluation"
```

---

### Task 14: `filter_editor`

**Files:**
- Create: `src/strace_ui/filter_editor.py`
- Test: `tests/test_filter_editor.py`

Reference: `/home/dannyb/sources/strace_ui/src/filter_editor.ml` lines 1-260 (skip `render_label`, which goes in render.py).

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.filter_editor import apply_action, EditState, is_editing
from strace_ui import filter as F
import strace_ui.filter_editor as FE

def start(current="read"):
    state, submitted = apply_action(None, F.parse(current), FE.Start())
    return state

def test_start_appends_trailing_space():
    state, _ = apply_action(None, F.parse("read"), FE.Start())
    assert state.buf == "read " and state.cursor == 5

def test_start_regex_appends_slash():
    state, _ = apply_action(None, F.parse("read"), FE.StartRegex())
    assert state.buf == "read /"

def test_key_inserts_at_cursor():
    s = EditState(buf="rd", cursor=1)
    s2, _ = apply_action(s, [], FE.Key("e"))
    assert s2.buf == "red" and s2.cursor == 2

def test_backspace():
    s = EditState(buf="read", cursor=4)
    s2, _ = apply_action(s, [], FE.Backspace())
    assert s2.buf == "rea" and s2.cursor == 3

def test_kill_word_backward():
    s = EditState(buf="%net read", cursor=9)
    s2, _ = apply_action(s, [], FE.KillWordBackward())
    assert s2.buf == "%net " and s2.cursor == 5

def test_move_word_forward():
    s = EditState(buf="%net read", cursor=0)
    s2, _ = apply_action(s, [], FE.MoveWordForward())
    assert s2.cursor == 5

def test_submit_normalizes_and_clears():
    s = EditState(buf="  %net  read ", cursor=0)
    state, submitted = apply_action(s, [], FE.Submit())
    assert state is None
    assert submitted == "%net read"

def test_cancel_clears():
    s = EditState(buf="x", cursor=1)
    state, submitted = apply_action(s, [], FE.Cancel())
    assert state is None and submitted is None
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`EditState` frozen dataclass `(buf, cursor)`. The editor's `t` is `EditState | None`. Action union: frozen dataclasses `Start, StartRegex, Key(c), Backspace, DeleteForward, MoveLeft, MoveRight, MoveToStart, MoveToEnd, KillToEnd, KillToStart, KillWordBackward, MoveWordForward, MoveWordBackward, Submit, Cancel`. `is_editing(t)`, `editing_buffer(t)`. Port `word_boundary_backward/forward` and `apply_action` returning `(new_state, submitted_filter_str | None)`. `Submit` returns `(None, filter.normalize(buf))`; `Cancel` returns `(None, None)`. Use `from strace_ui import filter as F` and call `F.to_normalized_string` / `F.normalize`.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/filter_editor.py tests/test_filter_editor.py
git commit -m "feat: filter_editor pure state machine with emacs motions"
```

---

## Chunk 4: model (virtual list, render mode, reducer)

### Task 15: `virtual_list` — VirtualList state

**Files:**
- Create: `src/strace_ui/virtual_list.py`
- Test: `tests/test_virtual_list.py`

Reference: `/home/dannyb/sources/strace_ui/src/virtual_list.ml`. This is a self-contained unit with zero dependencies on the rest of the model, so it lives in its own module (mirroring the separate OCaml compilation unit) to keep `model.py` focused on the reducer. `model.py` will `from strace_ui.virtual_list import VirtualList` and re-export it (`from strace_ui.virtual_list import VirtualList  # re-export`) so later tasks and tests can import `VirtualList` from either module.

- [ ] **Step 1: Write failing tests**

```python
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
    vl = vl.select_down().select_down().select_down()   # clamps at 2
    assert vl.selected_index == 2
    vl = vl.select_up().select_up().select_up()          # clamps at 0
    assert vl.selected_index == 0
    assert vl.select_bottom().selected_index == 2
    assert vl.select_top().selected_index == 0

def test_refilter_preserves_selection_to_nearest_prior():
    vl = VirtualList.create()
    for x in ["a", "b", "c", "d"]:
        vl = vl.append(x, passes_filter=True)
    vl = vl.jump_to_filtered_index(2)        # selected raw index 2 ("c")
    # New filter keeps only "a" and "d" (raw 0 and 3).
    keep = {"a", "d"}
    vl = vl.refilter(lambda item: item in keep)
    # nearest filtered index whose raw index <= 2 is "a" (index 0)
    assert vl.get_selected() == "a"

def test_set_item():
    vl = VirtualList.create().append("a", passes_filter=True)
    vl = vl.set_item(0, "A")
    assert vl.get_raw(0) == "A"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `VirtualList`**

Immutable-style dataclass holding `all_items: list`, `filtered_indices: list[int]`, `selected_index: int`. Methods: `create()`, `total_count`, `filtered_count`, `get_filtered`, `get_raw`, `get_selected`, `selected_raw_index`, `append(item, passes_filter)`, `set_item(idx, item)`, `refilter(passes)`, and the actions `select_up/down/top/bottom/jump_to_filtered_index`. Mirror the OCaml: `append` clamps selection to `min(selected, max(0, fc-1))`; `refilter` preserves selection by finding the highest filtered index with raw index ≤ previous selected raw index.

> **Performance note:** the OCaml uses a copy-on-write box to share the underlying vector. In Python, returning a new dataclass that *shares the same lists* (mutating them in place in `append`/`set_item`) is acceptable for the live app, but it breaks value-style tests. Keep it simple and correct: `append`/`set_item` copy the lists (`list(...)`). If profiling later shows this is too slow for very large traces, switch `all_items` to an append-only shared list (only `append` mutates the tail) — but that is a later optimization, not part of this task.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/virtual_list.py tests/test_virtual_list.py
git commit -m "feat: VirtualList filtered-index state with selection preservation"
```

---

### Task 16: `model` — RenderMode, Focus, helper functions

**Files:**
- Modify: `src/strace_ui/model.py`
- Test: `tests/test_model_helpers.py`

Reference: `strace_ui_app.ml` lines 6-47 (RenderMode), 124-267 (helpers).

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.model import (
    RenderMode, Focus, is_fd_return_type, extract_fd_numbers, buffer_meaningful_length,
)
from strace_ui.parser import parse_line, ValueResult

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
    # dup2 has two fd args; return is also an fd
    assert set(extract_fd_numbers(p)) >= {4, 5}

def test_buffer_meaningful_length_read():
    p = parse_line(0, '100 1.0 read(3, "abcdef", 100) = 4')
    assert buffer_meaningful_length(syscall_name="read", arg_index=1,
                                    args=['3', '"abcdef"', '100'], result=p.result) == 4

def test_buffer_meaningful_length_write_uses_count_arg():
    # write's meaningful length comes from arg 2 (count), not the return value.
    p = parse_line(0, '100 1.0 write(1, "abcdef", 6) = 6')
    assert buffer_meaningful_length(syscall_name="write", arg_index=1,
                                    args=['1', '"abcdef"', '6'], result=p.result) == 6

def test_buffer_meaningful_length_unknown_is_none():
    p = parse_line(0, '100 1.0 read(3, "abc", 9) = 3')
    assert buffer_meaningful_length(syscall_name="read", arg_index=0,
                                    args=['3', '"abc"', '9'], result=p.result) is None
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

- `RenderMode` enum (AUTO/HEXDUMP/STRING) with `cycle`, `to_short_string`, static `should_hexdump_in_auto(escaped_content)` (decode escapes; True if any byte >127 or non-printable non-whitespace), and `use_hexdump(escaped_content)` (HEXDUMP→True, STRING→False, AUTO→should_hexdump_in_auto).
- `Focus` enum (SYSCALL_LIST/DETAIL_PANE).
- `is_fd_return_type(syscall_name, args_raw)`: look up schema, `best_signature(arg_count=len(split_args))`, return_type is fd.
- `extract_fd_numbers(line)`: port lines 140-187 (schema-driven arg fds incl. bracket notation, plus return fd when fd-return-type; no schema → first arg if numeric).
- `buffer_meaningful_length(syscall_name, arg_index, args, result)`: port the match table lines 891-913.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/model.py tests/test_model_helpers.py
git commit -m "feat: RenderMode, Focus, fd-extraction and buffer-length helpers"
```

---

### Task 17: `model` — Model dataclass, Action union, resolve helpers

**Files:**
- Modify: `src/strace_ui/model.py`
- Test: `tests/test_model_reduce.py` (created here, extended next task)

Reference: `strace_ui_app.ml` lines 56-122 (Model, Action), 189-316 (resolve helpers), 634-660 (default_model).

- [ ] **Step 1: Write a failing test for `default_model` + `resolve_fds` + `passes_filter`**

```python
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
    # before update, tracker empty -> open's return fd 3 resolves to synthesized gen-0
    fds = resolve_fds(p, fd_tracker=FdTracker.empty())
    assert any(f.fd_number == 3 for f in fds)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement Model, Action, and the resolve helpers**

- `Model` dataclass with all fields from the spec §3.8 (`syscall_list, fd_tracker, syscall_filter, render_mode, next_index, show_man_page, man_page_cache, dns_cache, focus, show_help, filter_editor, pending_syscalls, resolved_fds, pid_map, resolve_pid_info`). Provide convenience methods mirroring the OCaml `Model` accessors (`selected_index`, `filtered_count`, `get_filtered`, `get_selected`). Since the model is large, use `dataclasses.replace` for updates (define a small `_with(self, **kw)` wrapper or just call `replace`).
- `Action` union: frozen dataclasses for each variant in the spec.
- `resolve_fds(line, fd_tracker)`: `extract_fd_numbers` then `resolve_fd_or_default` each, dropping `None`.
- `passes_filter(line, syscall_filter, fd_tracker, resolved_fds)`: get fd_ids from `resolved_fds[line.index]` or compute; build `filter.SyscallInfo`; call `filter.passes`.
- `default_model(primary_pid=None, resolve_pid_info=resolve_pid_info_via_procfs)`.
- Also port `fd_follow_filter`, `find_filtered_index_matching_filter`, `re_resolve_child_fds`, `update_filter_from_selected` as module functions (used by the reducer next task).

> `resolve_pid_info_via_procfs` reads `/proc` — define it here as the default injectable, exactly porting lines 607-632. It is impure but isolated and injectable (tests pass a stub).

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/model.py tests/test_model_reduce.py
git commit -m "feat: Model, Action union, fd-resolution and filter helpers"
```

---

### Task 18: `model.apply_action` — the reducer

**Files:**
- Modify: `src/strace_ui/model.py`
- Modify: `tests/test_model_reduce.py`

Reference: `strace_ui_app.ml` lines 318-605.

- [ ] **Step 1: Write failing tests covering the tricky reducer paths**

```python
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
        '7 2.5 recvmsg(3, {a=1} <unfinished ...>',
        '7 2.6 <... recvmsg resumed>, 0) = 64 <0.0001>',
    )
    assert m.syscall_list.total_count() == 1   # merged into one row
    row = m.syscall_list.get_raw(0)
    assert row.result == ValueResult("64")
    assert m.pending_syscalls == {}

def test_fork_then_child_fd_reresolved():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 clone(child_stack=NULL) = 200',
        '200 1.2 read(3, "x", 1) = 1',
    )
    # child read's fd 3 should resolve to parent's FdId (source_pid=100)
    read_idx = 2
    fds = m.resolved_fds[read_idx]
    assert any(f.source_pid == 100 and f.fd_number == 3 for f in fds)

def test_unfinished_clone_child_before_resume_gets_reresolved():
    # The hard path: a child syscall arrives AFTER an unfinished clone but BEFORE it
    # resumes. re_resolve_child_fds must rewrite the child line's empty resolved_fds
    # once the clone resumes and the child's fd table appears.
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 clone(child_stack=NULL <unfinished ...>',   # unfinished clone
        '200 1.2 read(3, "x", 1) = 1',                       # child runs before resume
        '100 1.3 <... clone resumed>) = 200',                # clone resumes -> child 200
    )
    read_idx = 2  # the child read's parsed index
    fds = m.resolved_fds[read_idx]
    assert any(f.source_pid == 100 and f.fd_number == 3 for f in fds)

def test_resumed_without_pending_appends_new_row():
    # A <... X resumed> with no matching unfinished entry is appended as its own row.
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m, '7 2.6 <... recvmsg resumed>, 0) = 64 <0.0001>')
    assert m.syscall_list.total_count() == 1
    assert m.syscall_list.get_raw(0).result == ValueResult("64")

def test_set_filter_refilters():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = feed(m,
        '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3',
        '100 1.1 read(3, "x", 1) = 1',
    )
    m = apply_action(m, M.SetFilter("read"))
    assert m.syscall_list.filtered_count() == 1
    assert m.syscall_list.get_selected().syscall_name == "read"

def test_cycle_preset_filter_order():
    m = default_model(resolve_pid_info=lambda pid: None)
    m = apply_action(m, M.CyclePresetFilter())   # "" -> %desc
    from strace_ui.filter import to_normalized_string
    assert to_normalized_string(m.syscall_filter) == "%desc"

def test_toggle_help_and_render_mode_and_focus():
    m = default_model(resolve_pid_info=lambda pid: None)
    assert apply_action(m, M.ToggleHelp()).show_help is True
    from strace_ui.model import RenderMode, Focus
    assert apply_action(m, M.ToggleRenderMode()).render_mode is RenderMode.HEXDUMP
    assert apply_action(m, M.ToggleFocus()).focus is Focus.DETAIL_PANE
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `apply_action`**

Port the full reducer faithfully, dispatching on the `Action` variant via `isinstance`. Implement every branch from the spec §3.8 / OCaml lines 318-605, including:
- `AddLine`: parse; on `None` just bump `next_index`. Register pid (resolve pid info on first sight). Branch on result kind: `Unfinished` (resolve fds against current tracker, append, record pending index), `Resumed` (find pending → merge → set_item → resolve before+after update → dedup+sort → store → `re_resolve_child_fds` → clear pending; else fall through to normal-with-fd-update path), normal (resolve before+after update → dedup+sort → store → append). Always `next_index += 1`.
- Selection actions delegate to `VirtualList`.
- `JumpToIndex` (find filtered index with matching raw index).
- `SetFilter`, `HideSelected`, `ShowOnlySelected`, `FilterSelectedPid`, `ExcludeSelectedPid` (via `update_filter_from_selected`).
- `CyclePresetFilter` (the documented order).
- `FilterEdit` (delegate to `filter_editor.apply_action`; on submit → `SetFilter`).
- `ToggleHelp`, `ToggleRenderMode`, `ToggleManPage`, `SetManPage`, `SetDnsEntry`, `ToggleFocus`, `JumpToFilteredIndex`.
- `FollowFd`, `JumpFdPrev`, `JumpFdNext`, `JumpFdOrigin`.

Use `dataclasses.replace` for model updates.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/model.py tests/test_model_reduce.py
git commit -m "feat: apply_action reducer (full Elm-style state transitions)"
```

---

### Task 19: Full pure-core regression run

**Files:** none (verification gate)

- [ ] **Step 1: Run the entire suite**

Run: `pytest -v`
Expected: all tests across `display_utils, value, parser, schema, pid_map, fd_tracker, filter, filter_editor, model_*` PASS.

- [ ] **Step 2: Capture real strace fixtures for confidence**

Run (if `strace` available; otherwise skip and note):
```bash
strace -ttt -T -f -x -yy -v -s 1024 -o /tmp/strace_sample.txt -- ping -c1 localhost 2>/dev/null || true
```

- [ ] **Step 3: Add a fixture-driven smoke test**

`tests/test_fixture_smoke.py`: if `/tmp/strace_sample.txt` exists, feed every line through `apply_action(AddLine)` and assert no exception and `filtered_count <= total_count`. Use `pytest.mark.skipif` when the fixture is absent. This guards against parser crashes on real-world lines.

- [ ] **Step 4: Commit**

```bash
git add tests/test_fixture_smoke.py
git commit -m "test: fixture-driven smoke test over real strace output"
```

---

## Chunk 5: themes, render, widgets, app, cli

> The Textual layer is verified primarily by manual run-through (the original has no UI tests). Keep pure, testable helpers (theme lookup, hexdump byte math already done) under test; treat rendering/layout/keys as manual-verification steps with an explicit checklist.

### Task 20: `themes` — palette registry

**Files:**
- Create: `src/strace_ui/themes.py`
- Test: `tests/test_themes.py`

Reference: original CLI help (`/home/dannyb/sources/strace_ui/bin/main-help-for-review.org`) for the flavor name list; `strace_ui_app.ml` lines 662-699 for the role set.

- [ ] **Step 1: Write failing tests**

```python
from strace_ui.themes import THEMES, get_theme, default_theme_name, Theme

def test_default_is_mocha():
    assert default_theme_name() == "Catppuccin_Mocha"

def test_all_18_themes_present():
    assert len(THEMES) == 18

def test_each_theme_has_all_roles():
    roles = ["fg","bg","highlight","accent","green","red","yellow","dim","blue","teal","key_hint"]
    for name, t in THEMES.items():
        for r in roles:
            assert getattr(t, r), f"{name} missing {r}"

def test_get_theme_case_insensitive_and_unknown():
    assert get_theme("catppuccin_mocha") is THEMES["Catppuccin_Mocha"]
    import pytest
    with pytest.raises(KeyError):
        get_theme("nope")
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `themes.py`**

`Theme` frozen dataclass with the 11 role fields, each a hex string like `"#cdd6f4"`. `THEMES: dict[str, Theme]` with all 18 flavors from the help list: `Catppuccin_Mocha`, `Catppuccin_Macchiato`, `Catppuccin_Frappe`, `Catppuccin_Latte`, `Vscode_dark`, `Vscode_light`, `Gruvbox_dark`, `Gruvbox_light`, `Dracula`, `Kanagawa`, `Tokyo_night_dark`, `Tokyo_night_light`, `Monokai`, `Bluloco`, `Solarized_dark`, `Solarized_light`, `Terminal_16`, `Terminal_16_inverted`.

Map the OCaml Catppuccin roles to hex from the canonical Catppuccin palette: `fg=Text, bg=Crust, highlight=Surface1, accent=Mauve, green=Green, red=Red, yellow=Yellow, dim=Overlay0, blue=Blue, teal=Teal, key_hint=Peach`. Use the published Catppuccin hex values for each of the four flavors. For the other themes, use each palette's canonical hex for the analogous roles (background = darkest/crust-equivalent, fg = main text, accent = the palette's purple/primary, etc.). For `Terminal_16` / `Terminal_16_inverted`, use ANSI-16 names mapped to representative hex (these intentionally lean on the terminal palette).

`get_theme(name)`: case-insensitive lookup (normalize to the canonical key); raise `KeyError` if unknown. `default_theme_name()` → `"Catppuccin_Mocha"`.

> This is data entry. Sources: the Catppuccin style guide for the four flavors; the canonical palettes for Gruvbox, Dracula, Tokyo Night, Solarized, Monokai, Kanagawa, VSCode Dark+/Light+, and Bluloco. Pick the closest role for each.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/themes.py tests/test_themes.py
git commit -m "feat: 18-theme palette registry (role-based)"
```

---

### Task 21: `render` — Rich renderables (pure-ish)

**Files:**
- Create: `src/strace_ui/render.py`
- Test: `tests/test_render.py`

Reference: `strace_ui_app.ml` render functions (704-1278), `hexdump_view.ml`, `filter_editor.ml render_label`.

This module converts model data + a `Theme` into Rich renderables (`rich.text.Text`, `rich.console.Group`). Most output is visual; test the **plain-text content** of renderables (via `Text.plain`) for the deterministic parts, leaving color to manual verification.

- [ ] **Step 1: Write failing tests for text content**

```python
from rich.text import Text
from strace_ui.render import (
    render_syscall_row_text, hexdump_lines_text, render_value_tree_text,
)
from strace_ui.themes import THEMES
from strace_ui.parser import parse_line
from strace_ui.value import parse as vparse

T = THEMES["Catppuccin_Mocha"]

def test_syscall_row_contains_name_and_result():
    p = parse_line(0, '100 1.0 openat(AT_FDCWD, "/a", O_RDONLY) = 3')
    txt = render_syscall_row_text(p, theme=T, width=60, short_id=1, pid_width=1, selected_pid=100)
    s = txt.plain
    assert "openat" in s
    assert s.rstrip().endswith("3") or "3" in s

def test_hexdump_lines_format():
    # 3 bytes -> one line with offset, hex, and ascii gutter
    lines = hexdump_lines_text("ABC", theme=T, bytes_per_line=8)
    assert len(lines) == 1
    s = lines[0].plain
    assert s.startswith("0000 ")
    assert "41 42 43" in s
    assert "│ABC" in s or "ABC" in s

def test_value_tree_text():
    lines = render_value_tree_text(vparse("{a=1, b=2}"), theme=T)
    plains = [l.plain for l in lines]
    assert plains == ["├─a = 1", "╰─b = 2"]
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement render helpers**

Build Rich `Text` objects with `Style(color=...)` from the theme. Implement at minimum:
- `render_syscall_row_text(line, theme, width, short_id, pid_width, selected_pid)` — pid column, space, syscall name, `(compact_args)` truncated to fit, gap fill, truncated result with fd-vs-value coloring; pad/crop to `width`. Mirror `render_syscall_line` (lines 724-827).
- `hexdump_lines_text(decoded_str, theme, bytes_per_line)` — offset column (`%04x`/`%08x`), grouped hex bytes, `│`, ASCII gutter (printable char, or colored `n`/`r`/`t`, low-byte hex digit, or `.`), trailing `│`. Mirror `hexdump_view.ml`.
- `render_value_tree_text(value, theme)` — wrap `value.fold_tree` with Rich emitters producing styled `Text` per line. Mirror `tree_views` (842-887).

Also implement (no separate unit tests; covered by manual run): `render_detail(...)` (header/args/result/raw/man sections — lines 971-1278), `render_help_modal`, `render_filter_label` (port `filter_editor.ml render_label`), `render_buffer_value`, `render_arg_value`. These return Rich renderables consumed by widgets.

Keep functions pure (no Textual, no I/O); they take a `Theme` and model data and return Rich objects.

- [ ] **Step 4: Run to verify pass** (the three text tests).

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/render.py tests/test_render.py
git commit -m "feat: Rich renderers for rows, hexdump, value tree, detail, help"
```

---

### Task 22: `widgets` — virtual list + detail panes

**Files:**
- Create: `src/strace_ui/widgets.py`

Reference: `virtual_list.ml render` (122-145), pane layout in `strace_ui_app.ml` (1539-1627).

No unit tests (Textual widgets); verified in Task 24's manual checklist.

- [ ] **Step 1: Implement `SyscallListWidget`**

A Textual `Widget` (or `Static` subclass) that, on render, reads the current `Model` (passed in / held by the app), computes the visible window from its own height: `scroll_offset = clamp(selected - height//2, 0, max(0, filtered_count - height))`, and builds a `rich.console.Group` of `render_syscall_row_text(...)` for the visible rows (using `theme`, `selected_pid`, `pid_width = pid_map.display_width()`). Empty list → centered "Waiting for syscalls...". Implement `render()` returning the Group; the app calls `refresh()` when the model changes.

- [ ] **Step 2: Implement `DetailWidget`**

A scrollable widget rendering `render_detail(selected_line, ...)`. Use Textual's `ScrollableContainer`/`VerticalScroll` to host a `Static` whose content is the detail Group, OR implement manual scroll offset matching the original's detail scroller (the original supports half-screen scroll, top/bottom). Simplest faithful approach: host the detail `Static` in a `VerticalScroll` and map the detail-focus keys to its scroll methods. Expose `scroll_down/up/half/top/bottom`.

- [ ] **Step 3: Implement the two bordered panes + titles/hints**

Compose with Textual borders (round) and titles. Left title `Syscalls` (+` <tab>` when unfocused), filter label top-right, `selected/total` bottom-right. Right title `Details` (+` <tab>`), `x:<mode> m:man` hint top-right. Use the focus color (accent vs dim).

- [ ] **Step 4: Manual import check**

Run: `python -c "import strace_ui.widgets"`
Expected: no error.

- [ ] **Step 5: Commit**

```bash
git add src/strace_ui/widgets.py
git commit -m "feat: Textual widgets for syscall list and detail panes"
```

---

### Task 23: `app` — Textual App, keybindings, async effects

**Files:**
- Create: `src/strace_ui/app.py`

Reference: `strace_ui_app.ml` (1368-1722 keybindings/effects, 1453-1531 man/DNS edges).

No unit tests; verified in Task 24.

- [ ] **Step 1: Implement the `StraceUiApp(App)` skeleton**

Holds `self.model: Model`, a `theme: Theme`, and a method `dispatch(action)` that sets `self.model = apply_action(self.model, action)` then refreshes the widgets. Compose the two panes (Task 22) in `compose()`. Compute pane dimensions from terminal size on resize (golden-ratio split, `min(50,...)` list cap), and pass viewport height/width into the list widget.

- [ ] **Step 2: Implement key handling (`on_key`)**

Port the focus-dependent dispatch from spec §3.10 exactly: Ctrl-c quit; F1/`?` toggle help; while help shown any key dismisses; Tab/Shift-Tab toggle focus; while filter editing route to the editor key map (spec §3.9); else the global keys (`f / % h H p P x m F < > ^`, `Alt-f` clear); `j/k/g/G` and `Ctrl-d|d|PgDn` / `Ctrl-u|u|PgUp` switch on focus (list selection/full-height page vs detail scroller half/top/bottom). Map each to a `dispatch(Action...)` or a detail-scroller call.

- [ ] **Step 3: Implement async effects**

- **strace reader**: a Textual worker (`@work(thread=False)` / asyncio) reads lines from the pipe `asyncio.StreamReader` and calls `self.call_from_thread`/`self.dispatch(AddLine(line))` per line.
- **man-page fetch**: when the selected syscall changes and `show_man_page` and the page is uncached, run `man --nj <section> <name>` via `asyncio.create_subprocess_exec` with `MANWIDTH` env = `str(max(40, detail_width - 2))` (exact formula from `strace_ui_app.ml:1481`) and `<section>` = the schema's `man_section` (default `2` when the syscall isn't in the schema, matching line 1479); on completion `dispatch(SetManPage(...))`. On non-zero/failed `man`, store `f"Could not load man page for {name}"`. Track the "current key" to avoid duplicate fetches (mirror the on_change edge).
- **reverse-DNS**: when the selected line's args contain unresolved IPs, resolve each via `loop.run_in_executor(None, socket.gethostbyaddr, ip)` (fall back to the IP on error) and `dispatch(SetDnsEntry(...))`.

Implement these as reactions to selection/model changes (e.g. after each `dispatch`, check whether man/DNS work is needed). Keep them idempotent.

- [ ] **Step 4: Implement startup/shutdown hooks**

`run_app(model, strace_proc, pipe_reader, flavor)` entry that mounts the app; on exit, SIGTERM the strace process; surface a stored strace error (set by the CLI monitor) as a non-zero exit / printed message.

- [ ] **Step 5: Manual import check + commit**

Run: `python -c "import strace_ui.app"` → no error.
```bash
git add src/strace_ui/app.py
git commit -m "feat: Textual app shell with keybindings and async effects"
```

---

### Task 24: `cli` — argparse, strace launch, error handling + manual verification

**Files:**
- Create: `src/strace_ui/cli.py`
- Create: `src/strace_ui/__main__.py`
- Test: `tests/test_cli_args.py`

Reference: `strace_ui_app.ml command` (1724-1849), `bin/main.ml`.

- [ ] **Step 1: Write failing tests for argv building**

```python
from strace_ui.cli import build_strace_args

def test_build_args_program():
    args = build_strace_args(write_fd=7, trace_expr=None, attach_pid=None, program=["ping", "localhost"])
    assert args[:10] == ["-ttt","-T","-f","-x","-yy","-v","-s","1024","-o","/dev/fd/7"]
    assert args[-3:] == ["--", "ping", "localhost"]

def test_build_args_pid_and_expr():
    args = build_strace_args(write_fd=7, trace_expr="trace=%net", attach_pid=12345, program=[])
    assert "-e" in args and "trace=%net" in args
    assert "-p" in args and "12345" in args

def test_build_args_requires_target():
    import pytest
    with pytest.raises(SystemExit):
        build_strace_args(write_fd=7, trace_expr=None, attach_pid=None, program=[])
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `cli.py`**

- `build_strace_args(write_fd, trace_expr, attach_pid, program)` → the fixed flags `["-ttt","-T","-f","-x","-yy","-v","-s","1024","-o", f"/dev/fd/{write_fd}"]` + (`-e EXPR` if set) + (`-p PID` if attach else `-- prog args`; error if neither).
- `main(argv=None)`:
  - argparse mirroring the original flags: positional `program` (REMAINDER), `-e/--expr`, `-p/--pid` (int), `-theme/--theme` (default `Catppuccin_Mocha`, choices = theme names), `-build-info`, `-version`, and a help alias `-?` in addition to argparse's default `-h/--help` (the original documents `-help, -?`). Accept the single-dash spellings (`-theme`, `-e`, `-p`) the original documents; argparse supports single-dash long options. To wire `-?`, add it via `parser.add_argument("-?", action="help", ...)` (or intercept it in `argv` before parsing).
  - `-version`/`-build-info` → print and exit 0.
  - Create `os.pipe()`; set the write end inheritable (`os.set_inheritable(w, True)`); resolve the theme; build strace argv.
  - Launch strace with `asyncio.create_subprocess_exec("strace", *args, pass_fds=(w,))`, close `w` in the parent, wrap the read end in an `asyncio.StreamReader`.
  - Build `default_model(primary_pid=attach_pid)`; run the Textual app (Task 23). Monitor strace: if it exits non-zero **and** `model.next_index == 0`, read strace stderr's first line and surface `strace: <line>` as the error, exit non-zero.
  - On app exit, SIGTERM strace.
- `__main__.py`: `from strace_ui.cli import main; main()`.

- [ ] **Step 4: Run argv tests to verify pass.**

- [ ] **Step 5: MANUAL VERIFICATION CHECKLIST**

With `strace` and `man` installed, run `strace-ui ping -c3 localhost` and confirm against the original (`@superpowers:verification-before-completion`):
- [ ] Two bordered panes appear; syscalls stream into the left list; golden-ratio split.
- [ ] Arrow/`j`/`k` move selection; `g`/`G` jump top/bottom; `d`/`u` page by full height; selection stays centered.
- [ ] Detail pane shows header (pid/time/duration), schema arg names, struct trees, result, raw line.
- [ ] `Tab` switches focus; in detail focus `j/k/g/G` scroll the detail pane.
- [ ] `f` opens the filter editor; typing + Enter filters; emacs keys (`C-a/e/w`, `M-f/b`) work; `Esc` cancels.
- [ ] `/` starts a regex filter; `%` cycles family presets; `h`/`H` hide/show-only selected syscall; `p`/`P` filter/exclude pid; `Alt-f` clears.
- [ ] `x` cycles auto/hex/str; buffers render as hexdump in hex/auto for binary; `m` toggles the man page (loads async).
- [ ] `F` follows the selected FD; `<`/`>` jump prev/next on same FD; `^` jumps to FD origin.
- [ ] IPs in FD annotations resolve to hostnames after a moment.
- [ ] `F1`/`?` shows the help modal; any key closes it; `Ctrl-c` quits and strace is terminated.
- [ ] `-theme Gruvbox_dark` (and a few others) changes colors; `-p <pid>` attaches; `-e trace=%net` restricts; a bad `-e` exits with a `strace:` error message.

- [ ] **Step 6: Commit**

```bash
git add src/strace_ui/cli.py src/strace_ui/__main__.py tests/test_cli_args.py
git commit -m "feat: CLI, strace launch via /dev/fd pipe, error handling"
```

---

### Task 25: README and final polish

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`** — usage (`strace-ui ping localhost`, `-p`, `-e`, `-theme`), the strace flags it issues, keybindings table (from `help_content`), prerequisites (`strace`, `man`), install (`pipx install .`).

- [ ] **Step 2: Full regression** — `pytest -v` (all green) and one more manual smoke run.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with usage, keybindings, prerequisites"
```

---

## Done

All pure logic is TDD-covered and matches the OCaml original; the Textual shell reproduces the layout, keybindings, and async effects, verified manually against the reference. The package installs as `strace-ui`.
