# strace-ui (Python port) — Design

**Date:** 2026-06-02
**Status:** Approved (pending spec review)
**Source project:** `/home/dannyb/sources/strace_ui` (OCaml, Bonsai/OxCaml)
**Target:** A Python reimplementation that supports all the same functionality as the original. No OCaml.

## 1. Goal & Constraints

Reimplement `strace-ui` — an interactive terminal UI over `strace` — in Python, preserving **all** functionality of the OCaml original. The original shells out to `strace`, parses its output, tracks file-descriptor provenance, renders structured values and hexdumps, and presents a two-pane TUI with rich filtering and keyboard navigation.

Decisions made during brainstorming:

- **Language / UI framework:** Python + [Textual](https://textual.textualize.io/) (which brings Rich for styled rendering). Matches the existing directory name `strace-ui-python`.
- **Themes:** Ship all ~18 color themes listed in the original's CLI help (Catppuccin Mocha/Macchiato/Frappe/Latte, VSCode dark/light, Gruvbox dark/light, Dracula, Kanagawa, Tokyo Night dark/light, Monokai, Bluloco, Solarized dark/light, Terminal-16, Terminal-16-inverted). Default: Mocha.
- **Testing:** TDD on the pure logic (parser, value parser, fd tracker, filter, schema, display/hexdump math, pid map, reducer). The live TUI is verified manually.
- **Packaging:** pip-installable CLI with a `strace-ui` console-script entry point.

Runtime prerequisites (same as original): `strace` and `man` available on `PATH`.

## 2. Guiding Principle: preserve the Elm-style architecture

The OCaml app is built on Bonsai, an Elm-style framework: an immutable `Model`, an `Action` variant type, and a pure reducer `apply_action_pure : Model.t -> Action.t -> Model.t`, with a separate render pass that reads the model. **We preserve this exact shape in Python.** This keeps the entire core logic pure and independently testable, and makes the port a near-mechanical translation rather than a redesign.

- **Pure core** — no I/O, no Textual imports. Direct translations of the OCaml modules. Fully unit-tested.
- **Textual shell** — owns the terminal; holds the `Model`; dispatches `Action`s on keypress; runs async tasks (strace reader, man-page fetch, reverse-DNS); re-renders widgets when the model changes.

## 3. Module Map (OCaml → Python)

```
strace_ui/
  parser.py        # strace_parser.ml
  value.py         # strace_value.ml
  display_utils.py # display_utils.ml
  fd_tracker.py    # fd_tracker.ml
  filter.py        # syscall_filter.ml
  schema.py        # syscall_schema.ml
  pid_map.py       # pid_map.ml
  model.py         # Model + Action + apply_action (the pure reducer; includes virtual-list state)
  themes.py        # ~18 theme palettes (role-based)
  render.py        # Rich renderables: syscall row, detail pane, hexdump, value tree, help modal
  widgets.py       # custom virtual-scrolling list widget + detail scroller (Textual)
  app.py           # Textual App: layout, keybindings, async effects, startup/shutdown
  cli.py           # argparse entry point, strace invocation, error handling
  __main__.py
tests/             # pytest, one file per pure module
pyproject.toml     # console_scripts: strace-ui = strace_ui.cli:main
```

### 3.1 `parser.py` (← strace_parser.ml)

Data types:

- `Result` — a tagged union (use a small class hierarchy or tagged dataclass): `Value(str)`, `Error(errno, description)`, `Unfinished`, `Resumed(Result)`, `Signal(str)`, `Exit(str)`.
- `ParsedLine` — dataclass `{index:int, pid:int, timestamp:float, syscall_name:str, args_raw:str, result:Result, duration:float|None, raw_line:str}`.

Functions (semantics must match OCaml exactly):

- `parse_line(index, line) -> ParsedLine | None` — strip leading whitespace; parse `pid`, whitespace, float `timestamp`, whitespace, then dispatch among: signal line (`---` → `Signal`, name `<<signal>>`), exit line (`+++` → `Exit`, name `<<exit>>`), resumed line (`<... NAME resumed> ...`), normal syscall (`name(args) = result <dur>`). Returns `None` on parse failure.
- Result parsing: `= -1 ERRNO (desc)` → `Error`; `<unfinished ...>` → `Unfinished`; otherwise `= VALUE` → `Value`, with a trailing `<float>` duration extracted from the value string via `extract_duration_from_value`.
- Arg extraction: collect chars up to the matching close paren, tracking paren depth and skipping over quoted strings (with backslash escapes). Unfinished calls have args ending in `<unfinished ...>` (stripped).
- Resumed line: split remaining text on `") = "` to separate trailing args from the result; result is wrapped `Resumed(actual)`.
- `merge_resumed(original, resumed) -> ParsedLine` — concatenate `args_raw` (dropping a trailing comma on the left, joining with `, `), take the resumed result (unwrapping `Resumed`), take resumed duration, append raw lines with ` ... `.
- `split_args(raw) -> list[str]` — top-level split on `,` (via `display_utils.split_top_level`), stripped; empty input → `[]`.
- `extract_fd_number(arg) -> int | None` — leading integer before `<`; `AT_FDCWD` → `None`; else integer-or-None.
- `extract_return_int(result) -> int | None` — for `Value`: integer before `<`, or `0x...` hex, or integer before first space, or whole; else `None`.

### 3.2 `value.py` (← strace_value.ml)

- `Value` tree: `Atom(str)`, `String(str)` (quoted), `Struct(list[(key, Value)])`, `Array(list[Value])`, `Call(name, arg)`.
- `parse(s) -> Value` — recursive: quoted string → `String`; `{...}` → `Struct` (top-level `,` split, each `key=value` via first `=`, value recursively parsed; bare field → `(field, Atom(""))`); `[...]` → `Array`; `name(arg)` (non-empty name, ends `)`) → `Call`; else `Atom`.
- `fold_tree(...)` — the generic walk with the same callback set the OCaml uses: `render_atom`, `render_string`, `render_call`, `render_prefix`, `render_prefix_with_value`, `render_prefix_with_multi`, `emit`. Tree prefixes `├─`/`╰─` with child indents `│ `/`  `. Struct/array nesting recurses; scalar leaves use the prefix-with-value path; quoted strings use the multi-line path.
- `to_lines(t, render_string=...) -> list[str]` — text rendering used in tests; default renders strings as `"..."`.

### 3.3 `display_utils.py` (← display_utils.ml)

Pure helpers, all semantics matched:

- `decode_strace_escapes(s)` — `\n \t \r \\ \" \0`, `\xNN` hex, else literal. (strace invoked with `-x`.)
- `hexdump_bytes_per_line(width, total_bytes)` — the offset-digit / group math; pick the largest multiple-of-8 that fits, capped to what the data needs.
- `split_escaped_at_byte(s, byte_count)` — split an escaped string at a logical byte boundary (counting `\xNN` and `\c` as one byte each).
- `strip_fd_annotations(arg)` — `3</path>` → `3` (only when the prefix looks numeric / `-` / `AT_FDCWD`).
- `wrap_string(s, width)` — hard char-boundary wrap.
- `extract_ip_addresses(s)` — scan for `d.d.d.d` with octets ≤ 255; dedup + sort.
- `resolve_ips_in_string(s, dns_cache)` — replace cached IPs with hostnames.
- `split_top_level(s, on)` — split on a delimiter ignoring nested `()[]{}` and quoted strings (backslash-escape aware).
- `compact_args_raw(args_raw)` — top-level split, strip fd annotations on each, rejoin `, `.

Hexdump *rendering* (the `hexdump_view.ml` styled output — offset column, hex bytes in groups, ASCII gutter with colored escapes) lives in `render.py`; the pure column math lives here.

### 3.4 `fd_tracker.py` (← fd_tracker.ml)

- `FdId` — `{source_pid, fd_number, generation}`, hashable/orderable (used as dict key and in sorted dedup).
- `FdOrigin` — `{syscall_index, syscall_name, summary}`.
- `FdTracker` — immutable-style state: `fd_tables: dict[pid, dict[fd_number, FdId]]`, `generation_counters: dict[(pid, fd_number), int]`, `origins: dict[FdId, FdOrigin]`, `parent_pid: dict[child, parent]`. Each mutation returns a new tracker (or uses copy-on-write semantics matching the OCaml persistent maps).
- Constant sets: `fd_creating_syscalls` (open/openat/socket/accept/accept4/dup/dup2/dup3/epoll_create/epoll_create1/eventfd2/timerfd_create/signalfd4/inotify_init1), `fd_pair_syscalls` (pipe/pipe2/socketpair), `fd_closing_syscalls` (close), `fork_syscalls` (clone/clone3/fork/vfork).
- `update(tracker, line) -> FdTracker` — only on successful `Value` results:
  - fd-creating: derive return fd; build a per-syscall `summary` (open/openat show the quoted path; dup* show `(args) = fd`; else `(args)`); if the slot is occupied, bump generation first (implicit close, e.g. dup2); record new `FdId` + origin in the source pid's table.
  - fd-pair: on return 0, extract fd numbers from the bracket arg (`extract_fd_pair`, depth-aware), record each like above.
  - fork: record `parent_pid[child]=pid`, copy the parent's fd table to the child, and copy the parent's generation counters into the child's `(child, fd)` keys.
  - close: bump the generation counter for `(pid, fd)` and remove from the table.
- `resolve_fd(tracker, pid, fd_number) -> FdId | None`.
- `resolve_fd_or_default(tracker, pid, fd_number) -> FdId | None` — if not in table: return `None` if it was ever tracked (counter exists), else synthesize generation-0 (pre-trace fd).
- `lookup_origin`, `parent_pid`, `lookup(tracker, pid, fd_number)`.

### 3.5 `filter.py` (← syscall_filter.ml)

- `Term` union: `IncludeFamily(Family)`, `IncludeSyscall(str)`, `ExcludeSyscall(str)`, `FilterPid(int)`, `ExcludePid(int)`, `FilterFd(fd_number, generation|None)`, `FilterRelatedPid(int)`, `Regex(compiled)`. A filter is a list of terms.
- `parse(s) -> list[Term]` — tokenize with special handling of `/regex/` (may contain spaces; closing `/` unescaped); plain tokens split on space. Token grammar: `!pid:N`, `pid:N`, `rel:N`, `fd:N` / `fd:N.G`, `%family` (matched against known families), `-name`/`!name` → exclude, `+name`/`name` → include. Invalid regex → literal (escaped). Empty regex dropped.
- `to_normalized_string` / `to_display_string` (`all` when empty).
- `passes(filter, info, fd_tracker) -> bool` where `info = {syscall_name, pid, fd_ids, raw_line}`:
  - no terms → pass-all.
  - inclusions present → name must match some include (family or exact); otherwise base = included.
  - exclusions subtract by name.
  - pid constraints: `FilterPid` (equal), `ExcludePid` (not equal), `FilterRelatedPid` (`is_related` via fork ancestry both directions).
  - fd constraints: every `FilterFd` must match some `fd_id` (number, and generation if specified).
  - regex constraints: every `Regex` must match `raw_line`.
  - result = `included and not excluded and pid_ok and fd_ok and regex_ok`.
- Helpers: `add_exclusion`, `add_inclusion`, `add_pid_filter`, `add_pid_exclusion`, `is_ancestor`, `is_related`.
- Regex engine: Python `re`. (OCaml uses RE2; document this substitution — patterns used here are simple; `re` is acceptable and we normalize/escape on parse failure.)

### 3.6 `schema.py` (← syscall_schema.ml)

- `ArgType` enum (File_descriptor, Path, Pointer, Int, Unsigned_int, Size, Offset, Flags, String, Struct, Sockaddr, Buffer, Pid, Signal, Mode, Other(str)), with `is_file_descriptor`.
- `ReturnType` enum (File_descriptor, Int, Ssize, Pointer, Void, Pid, Off), with `is_file_descriptor`.
- `Signature {c_signature, args: list[ArgSpec], return_type}`; `ArgSpec {name, arg_type}`.
- `SyscallInfo {name, signatures, brief, man_section}` with `best_signature(arg_count)` (exact arg-count match, else the signature with the most args).
- `KNOWN_SYSCALLS: dict[str, SyscallInfo]` — port the 119-entry generated table verbatim (arg names/types, C signatures, briefs, man sections).
- `Family` enum (All, Desc, File, Memory, Network, Process, Signal, Ipc) with `to_display_string` (`all`, `%desc`, `%file`, `%memory`, `%net`, `%process`, `%signal`, `%ipc`) and `includes(syscall_name)` using the exact membership lists from the original.
- `lookup(name) -> SyscallInfo | None`.

### 3.7 `pid_map.py` (← pid_map.ml)

- `PidInfo {cmdline, thread_name, is_thread}`.
- `PidMap {pid_to_short, next_id, infos}` with `register`, `short_id`, `display_width`, `info`, `set_info`, `summary` (`thread: NAME (cmdline)` when a thread, else cmdline).
- The procfs resolver (`resolve_pid_info_via_procfs`) reads `/proc/<pid>/cmdline`, `comm`, and `status` (Tgid) — this lives in `app.py`/`model.py` wiring (it touches the filesystem) but is a plain function injected into the model, matching the OCaml `resolve_pid_info` field.

### 3.8 `model.py` (← strace_ui_app.ml reducer + virtual_list.ml)

- **Virtual-list state** (← virtual_list.ml): `all_items` (list), `filtered_indices` (list of indices into all_items), `selected_index`. Operations: `append(item, passes)`, `set_item`, `refilter(passes)` (rebuild indices; preserve selection by finding the highest filtered index whose raw index ≤ previous selection's raw index), `apply_action` (Select_up/Down/Top/Bottom/Jump_to_filtered_index), plus `total_count`, `filtered_count`, `get_filtered`, `get_raw`, `get_selected`, `selected_raw_index`. Render windowing (`scroll_offset = clamp(selected - height/2, 0, count-height)`) lives in `widgets.py`.
- **RenderMode** enum: Auto / Hexdump / String, with `cycle`, `to_short_string`, and `should_hexdump_in_auto` (decode escapes, true if any byte > 127 or non-printable non-whitespace).
- **Focus** enum: Syscall_list / Detail_pane.
- **Model** dataclass: `syscall_list` (virtual-list state), `fd_tracker`, `syscall_filter`, `render_mode`, `next_index`, `show_man_page`, `man_page_cache`, `dns_cache`, `focus`, `show_help`, `filter_editor`, `pending_syscalls: dict[pid, idx]`, `resolved_fds: dict[index, list[FdId]]`, `pid_map`, `resolve_pid_info`.
- **Action** union: `AddLine`, `Select_up/Down/Top/Bottom`, `Jump_to_index`, `Set_filter`, `Hide_selected`, `Show_only_selected`, `Filter_selected_pid`, `Exclude_selected_pid`, `Cycle_preset_filter`, `Filter_edit(filter_editor_action)`, `Toggle_help`, `Toggle_render_mode`, `Toggle_man_page`, `Set_man_page`, `Set_dns_entry`, `Toggle_focus`, `Jump_to_filtered_index`, `Follow_fd`, `Jump_fd_prev`, `Jump_fd_next`, `Jump_fd_origin`.
- **`apply_action(model, action) -> model`** — faithful translation, including the subtle bits:
  - `AddLine`: parse; register pid (and resolve pid info on first sight); branch on result kind. **Unfinished** → resolve fds against current tracker, append, record pending index. **Resumed** → find matching pending, `merge_resumed`, set item, resolve fds before+after `fd_tracker.update`, dedup, store, run `re_resolve_child_fds`, clear pending. **Normal** → resolve before+after update, dedup, store, append. Increment `next_index` even on parse failure.
  - `re_resolve_child_fds` — after a fork/clone resolves, re-resolve fds for already-appended child-pid lines that had empty resolved fds.
  - filter actions rebuild the filtered list via `refilter`.
  - `Cycle_preset_filter` cycles `"" → %desc → %file → %memory → %net → %process → %signal → %ipc → ""`.
  - `Follow_fd` / `Jump_fd_prev` / `Jump_fd_next` / `Jump_fd_origin` use `fd_follow_filter` (`rel:PID fd:N.G`) and `find_filtered_index_matching_filter`.
- **Pure helpers** ported here: `is_fd_return_type`, `extract_fd_numbers`, `resolve_fds`, `passes_filter`, `fd_follow_filter`, `find_filtered_index_matching_filter`, `buffer_meaningful_length`.

### 3.9 `filter_editor` (← filter_editor.ml)

The in-place filter line editor with emacs keybindings. Pure state `{buf, cursor} | None` and `apply_action(state, current_filter, action) -> (state, submitted_filter_str | None)`. Actions: Start, Start_regex, Key(c), Backspace, Delete_forward, Move_left/right, Move_to_start/end, Kill_to_end/start, Kill_word_backward, Move_word_forward/backward, Submit, Cancel. Submit normalizes the buffer through `filter.normalize`. The scrolling/ellipsis label rendering (`render_label`) is reproduced in `render.py`. Lives as `filter_editor.py` (pure) + render hook. (Tested.)

### 3.10 `render.py`, `widgets.py`, `app.py`, `cli.py` (← strace_ui_app.ml shell + bin/main.ml)

- `render.py` — Rich renderables: `render_syscall_line` (pid short-id column, colored name, compacted/truncated args, truncated result with fd-vs-value coloring, fill), `render_detail` (header with time/pid/duration/signatures/brief, args section with schema names + tree/hexdump/buffer rendering + fd-origin lines, result section, raw section, man section), the styled `hexdump` renderer, the value-tree renderer, the help modal, and the filter-editor label.
- `widgets.py` — a custom Textual widget for the virtual list (renders only the visible window from the model) and the detail-pane scroller. Two bordered panes with titles/hints; help overlay.
- `app.py` — the Textual `App`: builds layout from terminal size (golden-ratio split, `min(50, …)` list cap), binds keys to actions (full set above + filter-edit mode capturing keys while editing), holds the `Model`, and re-renders on change. Async effects via Textual workers / asyncio:
  - **strace reader**: read lines from the pipe, dispatch `AddLine`.
  - **man-page fetch** on selection/`show_man_page` change for uncached syscalls: `man --nj <section> <name>` with `MANWIDTH` env, → `Set_man_page`.
  - **reverse-DNS** for unresolved IPs in the selected line's args: `gethostbyaddr` in a thread executor, → `Set_dns_entry`.
- `cli.py` — argparse mirroring the original flags: positional `PROGRAM ...`, `-e EXPR`, `-p PID`, `-theme THEME`, `-build-info`, `-version`, `-help`/`-?`, and `--` for the program. Build the strace argv: `-ttt -T -f -x -yy -v -s 1024 -o /dev/fd/<write>` (+ `-e`/`-p`/`-- prog`). Create `os.pipe()`, mark the write end inheritable, pass it as `/dev/fd/N`, close it in the parent. On exit, SIGTERM strace. If strace exits non-zero with no output produced, surface its first stderr line as the error and exit non-zero.

## 4. Data Flow Summary

1. `cli.py` parses flags → builds strace argv + the `/dev/fd` pipe → launches the Textual app with the initial `Model` (seeded with `primary_pid` when `-p`).
2. Async strace reader → `AddLine` actions → `apply_action` updates pid_map / fd_tracker / resolved_fds / virtual list (handling unfinished/resumed merge + post-fork fd re-resolution).
3. Keypresses → actions → `apply_action` (selection, filtering, focus, render mode, man toggle, fd navigation).
4. Selection changes trigger async man-page + reverse-DNS effects → `Set_man_page` / `Set_dns_entry`.
5. Render reads the model into the two panes; help is an overlay.
6. Exit SIGTERMs strace; early strace failure → error + non-zero exit.

## 5. Themes

The OCaml app sources colors from the `bonsai_term_catppuccin` dependency via role names (Text, Crust, Surface1, Mauve, Green, Red, Yellow, Overlay0, Blue, Teal, Peach). `themes.py` provides a `Theme` with the 11 roles the app uses — `fg, bg, highlight, accent, green, red, yellow, dim, blue, teal, key_hint` — and a registry of all ~18 flavors mapping each to role hex values, reconstructed from each palette's canonical colors (this color data is the one element not present in the OCaml *repo*, since it lived in a dependency). Default flavor: Mocha. `-theme` accepts the documented names.

## 6. Testing Plan (TDD)

pytest, one module per pure unit, written test-first:

- `test_parser.py` — normal/error/unfinished/resumed/signal/exit lines; duration extraction; nested parens & quoted/escaped strings in args; `merge_resumed`; `split_args`; `extract_fd_number`; `extract_return_int`.
- `test_value.py` — atoms, quoted strings, nested structs/arrays, calls, bare fields; `to_lines` tree shape (`├─`/`╰─`).
- `test_display_utils.py` — escape decoding incl. `\xNN`; `hexdump_bytes_per_line` math at various widths/sizes; `split_escaped_at_byte`; `strip_fd_annotations`; `wrap_string`; `extract_ip_addresses`; `split_top_level` nesting/quotes.
- `test_fd_tracker.py` — open/socket creation; dup2 implicit close generation bump; pipe/socketpair pairs; fork inheritance + generation copy; close bumps generation; `resolve_fd_or_default` pre-trace synth vs closed `None`; origins.
- `test_filter.py` — every term kind; family includes; inclusion/exclusion interaction; `rel:` ancestry both directions; `fd:N` and `fd:N.G`; regex; normalize round-trip.
- `test_schema.py` — `best_signature` exact/fallback; `Family.includes` membership; `lookup`.
- `test_pid_map.py` — register/short_id/display_width/summary (thread vs process).
- `test_model.py` — `apply_action` for AddLine across unfinished→resumed merge, fork → child fd re-resolution, filtered-list refilter selection preservation, preset cycling, follow-fd / jump-fd navigation, render-mode cycling.
- `test_filter_editor.py` — insertion, deletion, word motions/kills, kill-to-start/end, submit normalization, cancel.

Test fixtures seeded from real `strace` output captured locally (e.g. `strace -ttt -T -f -x -yy -v -s 1024 ping localhost`).

The live TUI (layout, scrolling feel, colors, key handling) is verified manually against the original.

## 7. Out of Scope (YAGNI)

- The `schema_generator` tool — not present in the OCaml repo; we port its generated output, not the generator.
- `-build-info` / `-version` are implemented but report the Python port's version metadata, not OCaml build info.
- Exact RE2 semantics — we use Python's `re`; filter regexes here are simple, and invalid patterns fall back to literal matching as in the original.

## 8. Known Behavioral Substitutions (documented, intentional)

- **Regex engine:** RE2 → Python `re`.
- **Theme colors:** reconstructed from canonical palettes (the OCaml values lived in a dependency, not the repo).
- **Version strings:** report the port's version.

All other behavior — parsing, fd tracking, filtering, rendering layout, keybindings, strace invocation, async man/DNS effects — is intended to match the original exactly.
