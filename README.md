# strace-ui

An interactive terminal UI for [`strace`](https://strace.io/), built with [Textual](https://textual.textualize.io/).

This is a Python port of [janestreet/strace_ui](https://github.com/janestreet/strace_ui) (originally OCaml). It reproduces the original's functionality: it shells out to `strace`, parses its output, tracks file-descriptor provenance, renders structured values and hexdumps, and presents a two-pane TUI with rich filtering and keyboard navigation.

```
┌────────────────────────────────────────────────────────────────────────────┐
│╭ Syscalls ───────────── f:all ╮╭ Details <tab> ──────────────── x:auto m:man ╮│
││  execve("/usr/bin/ping",...) 0││ recvmsg  pid 7 (#0)  15:04:20.358  0.00015s ││
││  openat(AT_FDCWD, "/lib6...) 3││ Receive a message from a socket            ││
││  read(3, "\x7fELF\x02\x0...)832││ Arguments                                  ││
││  socket(AF_INET, SOCK_DG...) 3││ sockfd: 3<PING:[140199664]>                ││
││  recvmsg(3, {msg_name={s...)64││   ↳ fd 3 from: socket(AF_INET, SOCK_DGRAM) ││
│╰───────────────────────── 12/13 ╯│ msg: ├─msg_name ...                       ││
└────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- `strace` on your `PATH` (the UI shells out to it)
- `man` on your `PATH` (for the in-app man-page pane)

## Installation

```bash
pipx install .          # from a checkout
# or
pip install .
```

This installs a `strace-ui` console script.

For development:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Usage

Invoke it roughly like you'd invoke `strace`:

```bash
strace-ui ping localhost
strace-ui -p 12345 -e '!futex'
strace-ui -theme Gruvbox_dark -- ls -la
```

Under the hood it runs `strace` with these arguments:

```
strace -ttt -T -f -x -yy -v -s 1024 -o /dev/fd/N [-e EXPR] [-p PID | -- PROGRAM ...]
```

(`-o /dev/fd/N` writes to an inherited pipe, which makes `strace` always prefix PIDs — even for single-process traces.)

### Options

| Flag | Description |
|------|-------------|
| `PROGRAM ...` | Program (and args) to run under strace |
| `-e EXPR` | Trace expression passed to strace (e.g. `trace=%net`) |
| `-p PID` | Attach to an existing process |
| `-theme THEME` | Color theme (see below) |
| `-version` | Print version and exit |
| `-build-info` | Print build info and exit |
| `-h`, `--help`, `-?` | Show help |

Long and single-dash spellings are accepted (`-theme` and `--theme`, `-e` and `--expr`, etc.).

### Themes

18 themes are available (default `Catppuccin_Mocha`):

`Catppuccin_Mocha`, `Catppuccin_Macchiato`, `Catppuccin_Frappe`, `Catppuccin_Latte`, `Vscode_dark`, `Vscode_light`, `Gruvbox_dark`, `Gruvbox_light`, `Dracula`, `Kanagawa`, `Tokyo_night_dark`, `Tokyo_night_light`, `Monokai`, `Bluloco`, `Solarized_dark`, `Solarized_light`, `Terminal_16`, `Terminal_16_inverted`.

## Features

- **Smart parsing** — associates `<unfinished ...>` calls with their eventual `<... resumed>` completion across interleaved multi-process output.
- **Structured values** — parses and renders structs/arrays as trees, and binary buffers as hexdumps (with meaningful-vs-trailing byte shading).
- **FD provenance** — tracks where each file descriptor came from (across `dup`, `pipe`, and `fork`/`clone`), and lets you follow or jump between all syscalls referencing a given FD. Press `F` to follow the selected FD.
- **Reverse DNS** — resolves IP addresses in FD annotations to hostnames, so `read(18<TCP:[10.0.0.1:80->10.0.0.2:443]>, ...)` shows `read(18<TCP:[foo:80->bar:443]>, ...)`.
- **Powerful filtering** — `-e` controls what strace captures; you can also filter the captured list dynamically (press `f`, `/`, or `%`).
- **Man pages** — press `m` to view the selected syscall's man page inline.

### Filter expression language

Type a filter with `f` (or `/` to start a regex). Terms are space-separated:

| Term | Meaning |
|------|---------|
| `%net` `%file` `%desc` `%memory` `%process` `%signal` `%ipc` | Include a syscall family |
| `read` `+open` | Include a syscall by name |
| `-write` `!futex` | Exclude a syscall by name |
| `pid:1234` / `!pid:1234` | Only / exclude a PID |
| `rel:1234` | PIDs related to 1234 (via fork graph) |
| `fd:3` / `fd:3.2` | Syscalls referencing FD 3 (optionally generation 2) |
| `/regex/` | Raw-line regex match |

## Keyboard shortcuts

Press `F1` or `?` in-app for this list.

| Key | Action |
|-----|--------|
| `F1` / `?` | Toggle help |
| `Tab` | Switch focus between list and details |
| `f` | Edit filter expression |
| `/` | Grep (start regex filter) |
| `%` | Cycle family presets |
| `h` | Hide selected syscall |
| `H` | Show only selected syscall |
| `p` | Filter to selected PID |
| `P` | Exclude selected PID |
| `x` | Cycle display mode (auto / hex / str) |
| `m` | Toggle man page |
| `j` / `k`, `↓` / `↑` | Move selection (or scroll details when focused) |
| `d` / `u`, `PgDn` / `PgUp` | Page down / up |
| `g` / `G` | Jump to top / bottom |
| `F` | Follow selected FD |
| `<` / `>` | Jump to prev / next syscall on the same FD |
| `^` | Jump to FD origin (open/socket/etc.) |
| `Alt-f` | Clear filter |
| `Ctrl-c` | Quit |

The filter editor supports emacs-style motions: `Ctrl-a/e/b/f/d/k/u/w`, `Alt-f/Alt-b`, arrows, `Home`/`End`.

## Architecture

The port preserves the original's Elm-style design: an immutable `Model`, an `Action` union, and a pure `apply_action(model, action) -> model` reducer, with a separate render pass.

- **Pure core** (no I/O, no Textual) — `parser`, `value`, `display_utils`, `fd_tracker`, `filter`, `filter_editor`, `schema`, `pid_map`, `virtual_list`, and the `model` reducer. Fully unit-tested.
- **Textual shell** — `widgets`, `app`, `cli`: owns the terminal, holds the model, dispatches actions on keypresses, and runs async tasks (strace reader, man-page fetch, reverse-DNS).

## License

See the upstream project for license terms.
