"""render: Rich renderables for strace_ui.

Converts model data + a Theme into Rich renderables (Text, Group, Panel).
Port of OCaml strace_ui_app.ml render functions (lines 704-1353),
hexdump_view.ml, and filter_editor.ml render_label.

All functions are pure (no Textual, no I/O).
"""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from rich.style import Style
from rich.console import Group
from rich.panel import Panel

from strace_ui.themes import Theme
from strace_ui import parser, value, display_utils, schema
from strace_ui.model import RenderMode, is_fd_return_type, buffer_meaningful_length
from strace_ui.fd_tracker import FdTracker
from strace_ui.pid_map import PidMap
from strace_ui import filter as F


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _style(theme: Theme, fg: str, *, bg: Optional[str] = None, bold: bool = False) -> Style:
    return Style(color=fg, bgcolor=(bg or theme.bg), bold=bold)


# ---------------------------------------------------------------------------
# render_syscall_row_text
# ---------------------------------------------------------------------------

def render_syscall_row_text(
    line: parser.ParsedLine,
    *,
    theme: Theme,
    width: int,
    short_id: int,
    pid_width: int,
    selected_pid: int,
    is_selected: bool = False,
) -> Text:
    """Render a single syscall list row as a Rich Text of exactly `width` columns.

    Port of OCaml render_syscall_line (lines 724-827).
    """
    bg = theme.highlight if is_selected else theme.bg

    # --- PID column ---
    if short_id == 0:
        pid_str = " " * pid_width
    else:
        pid_str = str(short_id).rjust(pid_width)

    pid_color = theme.fg if line.pid == selected_pid else theme.dim

    # --- syscall name ---
    name = line.syscall_name

    # --- result column (width 6) ---
    result_width = 6

    def _truncate_result(s: str, color: str) -> tuple[str, Style, Optional[str], Optional[Style]]:
        """Return (main_str, main_style, suffix_str_or_None, suffix_style_or_None)."""
        if len(s) > result_width:
            return (
                s[:result_width - 1],
                _style(theme, color, bg=bg),
                ">",
                _style(theme, theme.dim, bg=bg),
            )
        return s, _style(theme, color, bg=bg), None, None

    result = line.result
    if isinstance(result, parser.ValueResult):
        v = display_utils.strip_fd_annotations(result.value).lstrip()
        # Strip parenthetical annotations like "0 (Timeout)" -> "0"
        if " " in v:
            num_part, rest = v.split(" ", 1)
            if rest.lstrip().startswith("("):
                v = num_part
        color = theme.yellow if is_fd_return_type(syscall_name=name, args_raw=line.args_raw) else theme.green
        r_main, r_main_style, r_suf, r_suf_style = _truncate_result(v, color)
    elif isinstance(result, parser.ErrorResult):
        r_main, r_main_style, r_suf, r_suf_style = _truncate_result(result.errno, theme.red)
    elif isinstance(result, (parser.Unfinished, parser.Resumed)):
        r_main, r_main_style = "...", _style(theme, theme.yellow, bg=bg)
        r_suf, r_suf_style = None, None
    elif isinstance(result, parser.Signal):
        r_main, r_main_style = "SIG", _style(theme, theme.yellow, bg=bg)
        r_suf, r_suf_style = None, None
    elif isinstance(result, parser.Exit):
        r_main, r_main_style = "EXIT", _style(theme, theme.dim, bg=bg)
        r_suf, r_suf_style = None, None
    else:
        r_main, r_main_style = "?", _style(theme, theme.dim, bg=bg)
        r_suf, r_suf_style = None, None

    result_str = r_main + (r_suf or "")
    result_display_len = len(result_str)

    # --- compact args, truncated to fit ---
    compact = display_utils.compact_args_raw(line.args_raw)
    # overhead: pid_width + 1 (space) + len(name) + 1 ("(") + 1 (")") + 1 (space) + result_width
    overhead = pid_width + 1 + len(name) + 1 + 1 + 1 + result_width
    max_args = max(0, width - overhead)
    if len(compact) > max_args:
        if max_args <= 3:
            compact = ""
        else:
            compact = compact[:max_args - 3] + "..."

    # --- Assemble the Text ---
    # Compute: left = pid + " " + name + "(" + compact + ")"
    left_str = pid_str + " " + name + "(" + compact + ")"
    gap = max(1, width - len(left_str) - result_display_len)

    # Hard-crop or pad to exactly `width`
    # We build a plain string to measure, then assemble styled Text
    full_plain = left_str + " " * gap + result_str
    crop = len(full_plain) - width
    if crop > 0:
        # Trim from result side: shorten gap first
        gap = max(0, gap - crop)
        crop -= max(0, gap)  # remaining after gap shrunk (won't go below 0 since gap starts >=1)

    row = Text(no_wrap=True, overflow="fold")
    # pid portion
    row.append(pid_str, style=_style(theme, pid_color, bg=bg))
    row.append(" ", style=Style(bgcolor=bg))
    row.append(name, style=_style(theme, theme.accent, bg=bg, bold=True))
    row.append("(" + compact + ")", style=_style(theme, theme.fg, bg=bg))
    # gap
    actual_gap = max(1, width - len(pid_str) - 1 - len(name) - len("(" + compact + ")") - result_display_len)
    row.append(" " * actual_gap, style=Style(bgcolor=bg))
    # result
    row.append(r_main, style=r_main_style)
    if r_suf is not None and r_suf_style is not None:
        row.append(r_suf, style=r_suf_style)

    # Crop or pad to exactly `width`
    current_len = len(row.plain)
    if current_len < width:
        row.append(" " * (width - current_len), style=Style(bgcolor=bg))
    elif current_len > width:
        row = row[:width]

    return row


# ---------------------------------------------------------------------------
# hexdump_lines_text
# ---------------------------------------------------------------------------

def hexdump_lines_text(
    decoded: str,
    *,
    theme: Theme,
    bytes_per_line: int = 16,
) -> list[Text]:
    """Render hexdump of `decoded` (chars 0-255) as a list of Rich Text lines.

    Port of hexdump_view.ml render (lines 12-78).
    """
    n = len(decoded)
    offset_digits = 8 if n > 0xFFFF else 4
    group_size = 8 if bytes_per_line > 8 else bytes_per_line

    lines: list[Text] = []
    offset = 0

    while offset < n:
        line = Text()

        # Offset prefix
        if offset_digits == 4:
            offset_str = f"{offset:04x} "
        else:
            offset_str = f"{offset:08x} "
        line.append(offset_str, style=_style(theme, theme.dim))

        # Hex bytes
        hex_parts: list[str] = []
        for i in range(bytes_per_line):
            if offset + i < n:
                hex_parts.append(f"{ord(decoded[offset + i]):02x} ")
            else:
                hex_parts.append("   ")
            # Extra space after each group boundary (except at end)
            if (i + 1) % group_size == 0 and i + 1 < bytes_per_line:
                hex_parts.append(" ")
        hex_str = "".join(hex_parts)
        line.append(hex_str, style=_style(theme, theme.fg))

        # Separator
        line.append("│", style=_style(theme, theme.dim))

        # ASCII gutter
        for i in range(bytes_per_line):
            if offset + i < n:
                c = decoded[offset + i]
                n_ord = ord(c)
                if 32 <= n_ord <= 126:
                    # printable
                    line.append(c, style=_style(theme, theme.fg))
                elif c == "\n":
                    line.append("n", style=_style(theme, theme.teal))
                elif c == "\r":
                    line.append("r", style=_style(theme, theme.teal))
                elif c == "\t":
                    line.append("t", style=_style(theme, theme.teal))
                elif n_ord < 16:
                    line.append(f"{n_ord:x}", style=_style(theme, theme.blue))
                else:
                    line.append(".", style=_style(theme, theme.dim))
            else:
                line.append(" ", style=_style(theme, theme.fg))

        # Trailing separator
        line.append("│", style=_style(theme, theme.dim))

        lines.append(line)
        offset += bytes_per_line

    return lines


# ---------------------------------------------------------------------------
# render_value_tree_text
# ---------------------------------------------------------------------------

def render_value_tree_text(
    parsed_value: value.Value,
    *,
    theme: Theme,
    render_string: Optional[Callable[[str], list[Text]]] = None,
) -> list[Text]:
    """Render a parsed Value as a list of Rich Text lines (tree view).

    Port of OCaml tree_views (lines 842-887) via value.fold_tree.
    The plain text of each returned Text must match value.to_lines exactly.
    """
    if render_string is None:
        def render_string(s: str) -> list[Text]:
            return [Text('"' + s + '"', style=_style(theme, theme.fg))]

    lines: list[Text] = []

    def emit(t: Text) -> None:
        lines.append(t)

    def _text(s: str) -> Text:
        return Text(s, style=_style(theme, theme.fg))

    def _dim(s: str) -> Text:
        return Text(s, style=_style(theme, theme.dim))

    def _concat(*parts: Text) -> Text:
        result = Text()
        for p in parts:
            result.append_text(p)
        return result

    def _indent_view(indent: str, v: Text) -> Text:
        if not indent:
            return v
        return _concat(_dim(indent), v)

    def _prefix_view(prefix: str) -> Text:
        return _dim(prefix)

    def render_atom_fn(indent: str, s: str) -> Text:
        return _indent_view(indent, _text(s))

    def render_string_fn(s: str) -> list[Text]:
        return render_string(s)  # type: ignore[misc]

    def render_call_fn(indent: str, name: str, arg: str) -> Text:
        return _indent_view(indent, _text(f"{name}({arg})"))

    def render_prefix_fn(indent: str, prefix: str, label: str) -> Text:
        return _indent_view(indent, _concat(_prefix_view(prefix), _text(label)))

    def render_prefix_with_value_fn(indent: str, prefix: str, key: str, val: str) -> Text:
        return _indent_view(indent, _concat(_prefix_view(prefix), _text(f"{key} = {val}")))

    def render_prefix_with_multi_fn(
        emit_fn: Callable[[Text], None],
        indent: str,
        child_indent: str,
        prefix: str,
        key: str,
        views: list[Text],
    ) -> None:
        if not views:
            return
        if len(views) == 1:
            single = views[0]
            if not key:
                emit_fn(_indent_view(indent, _concat(_prefix_view(prefix), single)))
            else:
                label = _concat(_prefix_view(prefix), _text(f"{key} = "), single)
                emit_fn(_indent_view(indent, label))
        elif not key:
            # multiple, empty key: first inline with prefix, rest at child_indent
            emit_fn(_indent_view(indent, _concat(_prefix_view(prefix), views[0])))
            for v in views[1:]:
                emit_fn(_indent_view(child_indent, v))
        else:
            # Struct field: label on own line, all content below
            emit_fn(_indent_view(indent, _concat(_prefix_view(prefix), _text(f"{key} ="))))
            for v in views:
                emit_fn(_indent_view(child_indent, v))

    value.fold_tree(
        parsed_value,
        emit=emit,
        render_atom=render_atom_fn,
        render_string=render_string_fn,
        render_call=render_call_fn,
        render_prefix=render_prefix_fn,
        render_prefix_with_value=render_prefix_with_value_fn,
        render_prefix_with_multi=render_prefix_with_multi_fn,
    )

    return lines


# ---------------------------------------------------------------------------
# render_detail helpers
# ---------------------------------------------------------------------------

def _render_result_text(
    result: parser.Result,
    *,
    theme: Theme,
    value_color: Optional[str] = None,
) -> Text:
    """Port of OCaml render_result (lines 704-722)."""
    if value_color is None:
        value_color = theme.green

    if isinstance(result, parser.ValueResult):
        t = Text()
        t.append(f"= {result.value}", style=_style(theme, value_color))
        return t
    elif isinstance(result, parser.ErrorResult):
        t = Text()
        t.append(f"= -1 {result.errno}", style=_style(theme, theme.red))
        t.append(f" ({result.description})", style=_style(theme, theme.dim))
        return t
    elif isinstance(result, parser.Unfinished):
        return Text("<unfinished>", style=_style(theme, theme.yellow))
    elif isinstance(result, parser.Resumed):
        return Text("<resumed>", style=_style(theme, theme.yellow))
    elif isinstance(result, parser.Signal):
        return Text(result.text, style=_style(theme, theme.yellow))
    elif isinstance(result, parser.Exit):
        return Text(result.text, style=_style(theme, theme.dim))
    else:
        return Text("?", style=_style(theme, theme.dim))


def _section_header(label: str, *, theme: Theme) -> Text:
    """Render a yellow bold section header."""
    return Text(label, style=_style(theme, theme.yellow, bold=True))


def _render_buffer_value(
    *,
    theme: Theme,
    arg_raw: str,
    meaningful_bytes: int,
    render_mode: RenderMode,
    width: int,
) -> tuple[bool, object]:
    """Port of OCaml render_buffer_value (lines 916-968).

    Returns (is_hexdump, renderable).
    """
    # Strip surrounding quotes
    content = arg_raw
    if content.startswith('"'):
        content = content[1:]
    has_trailing_ellipsis = arg_raw.endswith('"...')
    if content.endswith('"...'):
        content = content[:-4]
    elif content.endswith('"'):
        content = content[:-1]

    if render_mode.use_hexdump(escaped_content=content):
        meaningful_part, trailing_part = display_utils.split_escaped_at_byte(
            content, meaningful_bytes
        )
        meaningful_decoded = display_utils.decode_strace_escapes(meaningful_part)
        trailing_decoded = display_utils.decode_strace_escapes(trailing_part)
        total_bytes = len(meaningful_decoded) + len(trailing_decoded)
        bpl = display_utils.hexdump_bytes_per_line(width - 1, total_bytes)

        meaningful_views = hexdump_lines_text(meaningful_decoded, theme=theme, bytes_per_line=bpl)
        trailing_views = hexdump_lines_text(trailing_decoded, theme=theme, bytes_per_line=bpl)
        # trailing in dim — we just render them differently but keep the same structure
        all_views = meaningful_views + trailing_views
        return True, Group(*all_views)
    else:
        meaningful_part, trailing_part = display_utils.split_escaped_at_byte(
            content, meaningful_bytes
        )
        t = Text()
        t.append('"' + meaningful_part, style=_style(theme, theme.fg))
        if trailing_part:
            t.append(trailing_part, style=_style(theme, theme.dim))
        t.append('"...' if has_trailing_ellipsis else '"', style=_style(theme, theme.fg))
        return False, t


def _render_arg_value(
    *,
    theme: Theme,
    render_mode: RenderMode,
    width: int,
    name_label_len: int,
    is_buffer: bool,
    line: parser.ParsedLine,
    arg_index: int,
    args: list[str],
    arg_raw: str,
) -> tuple[bool, object]:
    """Port of OCaml render_arg_value (lines 1017-1088).

    Returns (is_hexdump, renderable).
    """
    if is_buffer:
        meaningful_bytes = buffer_meaningful_length(
            syscall_name=line.syscall_name,
            arg_index=arg_index,
            args=args,
            result=line.result,
        )
    else:
        meaningful_bytes = None

    if meaningful_bytes is not None and is_buffer:
        return _render_buffer_value(
            theme=theme,
            arg_raw=arg_raw,
            meaningful_bytes=meaningful_bytes,
            render_mode=render_mode,
            width=width,
        )

    # Possibly hexdump without meaningful_bytes
    if is_buffer:
        escaped_content = arg_raw
        if escaped_content.startswith('"'):
            escaped_content = escaped_content[1:]
        if escaped_content.endswith('"'):
            escaped_content = escaped_content[:-1]
    else:
        escaped_content = ""

    if is_buffer and render_mode.use_hexdump(escaped_content=escaped_content):
        content = display_utils.decode_strace_escapes(escaped_content)
        bpl = display_utils.hexdump_bytes_per_line(width - 1, len(content))
        views = hexdump_lines_text(content, theme=theme, bytes_per_line=bpl)
        return True, Group(*views)

    if arg_raw.startswith("{") or arg_raw.startswith("["):
        def render_str_views(s: str) -> list[Text]:
            if render_mode.use_hexdump(escaped_content=s):
                decoded = display_utils.decode_strace_escapes(s)
                bpl = display_utils.hexdump_bytes_per_line(width - 7, len(decoded))
                return hexdump_lines_text(decoded, theme=theme, bytes_per_line=bpl)
            return [Text(f'"{s}"', style=_style(theme, theme.fg))]

        parsed = value.parse(arg_raw)
        views = render_value_tree_text(parsed, theme=theme, render_string=render_str_views)
        return True, Group(*views)

    # Plain string / atom: wrap if needed
    wrap_width = max(20, width - name_label_len - 1)
    if len(arg_raw) <= wrap_width:
        return False, Text(arg_raw, style=_style(theme, theme.fg))
    wrapped = display_utils.wrap_string(arg_raw, wrap_width)
    if not wrapped:
        return False, Text(arg_raw, style=_style(theme, theme.fg))
    texts = [Text(w, style=_style(theme, theme.fg)) for w in wrapped]
    return False, Group(*texts)


def _render_detail_header(
    line: parser.ParsedLine,
    *,
    theme: Theme,
    schema_info,
    pid_map: PidMap,
) -> Group:
    """Port of OCaml render_detail_header (lines 971-1015)."""
    import datetime
    ts = datetime.datetime.fromtimestamp(line.timestamp)
    time_str = ts.strftime("%H:%M:%S.%f")

    pid_str = str(line.pid)
    short_id = pid_map.short_id(line.pid) or 0

    name_line = Text()
    name_line.append(line.syscall_name, style=_style(theme, theme.accent, bold=True))
    name_line.append(f"  pid {pid_str} (#{short_id})  {time_str}", style=_style(theme, theme.fg))
    if line.duration is not None:
        name_line.append(f"  {line.duration:.6f}s", style=_style(theme, theme.fg))

    parts: list = [name_line]

    summary = pid_map.summary(line.pid)
    if summary is not None:
        parts.append(Text(summary, style=_style(theme, theme.fg)))

    if schema_info is not None:
        parts.append(Text(schema_info.brief, style=_style(theme, theme.dim)))
        for sig in schema_info.signatures:
            parts.append(Text(sig.c_signature, style=_style(theme, theme.dim)))
    else:
        parts.append(Text("Unknown syscall", style=_style(theme, theme.dim)))

    parts.append(Text("", style=_style(theme, theme.fg)))

    return Group(*parts)


def _render_detail_args(
    line: parser.ParsedLine,
    *,
    theme: Theme,
    render_mode: RenderMode,
    width: int,
    fd_tracker: FdTracker,
    dns_cache: dict,
    best_sig,
) -> Group:
    """Port of OCaml render_detail_args (lines 1090-1168)."""
    args = parser.split_args(line.args_raw)
    arg_specs = list(best_sig.args) if best_sig is not None else []

    parts: list = [_section_header("Arguments", theme=theme)]

    for i, arg_raw in enumerate(args):
        arg_raw = arg_raw.strip()
        spec = arg_specs[i] if i < len(arg_specs) else None

        if spec is not None:
            name_label = Text(f"{spec.name}: ", style=_style(theme, theme.blue))
        else:
            name_label = Text(f"arg{i}: ", style=_style(theme, theme.dim))

        is_fd = spec.arg_type.is_file_descriptor() if spec is not None else False
        if is_fd:
            arg_raw = display_utils.resolve_ips_in_string(arg_raw, dns_cache)

        is_buffer = arg_raw.startswith('"')

        is_hexdump, value_renderable = _render_arg_value(
            theme=theme,
            render_mode=render_mode,
            width=width,
            name_label_len=len(name_label.plain),
            is_buffer=is_buffer,
            line=line,
            arg_index=i,
            args=args,
            arg_raw=arg_raw,
        )

        if is_hexdump:
            parts.append(name_label)
            parts.append(value_renderable)
        else:
            combined = Text()
            combined.append_text(name_label)
            if isinstance(value_renderable, Text):
                combined.append_text(value_renderable)
            else:
                parts.append(combined)
                parts.append(value_renderable)
                combined = None  # type: ignore[assignment]
            if combined is not None:
                parts.append(combined)

        if is_fd:
            fd_num = parser.extract_fd_number(arg_raw)
            if fd_num is not None:
                origin = fd_tracker.lookup(pid=line.pid, fd_number=fd_num)
                if origin is not None:
                    parts.append(Text(
                        f"    ↳ fd {fd_num} from: {origin.summary} (index #{origin.syscall_index})",
                        style=_style(theme, theme.dim),
                    ))

    parts.append(Text("", style=_style(theme, theme.fg)))
    return Group(*parts)


def _render_detail_result(
    line: parser.ParsedLine,
    *,
    theme: Theme,
    best_sig,
    dns_cache: dict,
) -> Group:
    """Port of OCaml render_detail_result (lines 1171-1204)."""
    is_fd = is_fd_return_type(syscall_name=line.syscall_name, args_raw=line.args_raw)

    result = line.result
    if is_fd and isinstance(result, parser.ValueResult):
        result = parser.ValueResult(
            display_utils.resolve_ips_in_string(result.value, dns_cache)
        )

    value_color = theme.yellow if is_fd else theme.green
    result_text = _render_result_text(result, theme=theme, value_color=value_color)

    parts: list = [_section_header("Result", theme=theme), result_text]

    if best_sig is not None and best_sig.return_type.is_file_descriptor():
        fd_num = parser.extract_return_int(line.result)
        if fd_num is not None and fd_num >= 0:
            parts.append(Text(f"  (new file descriptor {fd_num})", style=_style(theme, theme.dim)))

    parts.append(Text("", style=_style(theme, theme.fg)))
    return Group(*parts)


def _render_detail_raw(line: parser.ParsedLine, *, theme: Theme) -> Group:
    """Port of OCaml render_detail_raw (lines 1207-1213)."""
    return Group(
        _section_header("Raw", theme=theme),
        Text(line.raw_line, style=_style(theme, theme.fg)),
        Text("", style=_style(theme, theme.fg)),
    )


def _render_detail_man(
    *,
    theme: Theme,
    show_man_page: bool,
    man_page_content: Optional[str],
    schema_info,
) -> Optional[Group]:
    """Port of OCaml render_detail_man (lines 1215-1243).

    Returns None if not shown (equivalent to View.none).
    """
    if not show_man_page:
        return None

    if schema_info is None:
        return Group(
            _section_header("Man Page", theme=theme),
            Text("No man page available for this syscall", style=_style(theme, theme.dim)),
        )

    name = schema_info.name
    if man_page_content is not None:
        man_lines = [
            Text(l, style=_style(theme, theme.fg))
            for l in man_page_content.splitlines()
        ]
        return Group(
            _section_header(f"Man Page: {name}", theme=theme),
            *man_lines,
            Text("", style=_style(theme, theme.fg)),
        )
    else:
        return Group(
            _section_header("Man Page", theme=theme),
            Text(f"Loading man page for {name}...", style=_style(theme, theme.dim)),
            Text("", style=_style(theme, theme.fg)),
        )


# ---------------------------------------------------------------------------
# render_detail
# ---------------------------------------------------------------------------

def render_detail(
    line: parser.ParsedLine,
    *,
    theme: Theme,
    fd_tracker: FdTracker,
    dns_cache: dict,
    render_mode: RenderMode,
    show_man_page: bool,
    man_page_content: Optional[str],
    width: int,
    pid_map: PidMap,
) -> Group:
    """Render the detail pane for a syscall line.

    Port of OCaml render_detail (lines 1246-1278).
    """
    schema_info = schema.lookup(line.syscall_name)
    actual_args = parser.split_args(line.args_raw)
    best_sig = None
    if schema_info is not None:
        best_sig = schema_info.best_signature(arg_count=len(actual_args))

    header = _render_detail_header(line, theme=theme, schema_info=schema_info, pid_map=pid_map)
    args_section = _render_detail_args(
        line,
        theme=theme,
        render_mode=render_mode,
        width=width,
        fd_tracker=fd_tracker,
        dns_cache=dns_cache,
        best_sig=best_sig,
    )
    result_section = _render_detail_result(line, theme=theme, best_sig=best_sig, dns_cache=dns_cache)
    raw_section = _render_detail_raw(line, theme=theme)
    man_section = _render_detail_man(
        theme=theme,
        show_man_page=show_man_page,
        man_page_content=man_page_content,
        schema_info=schema_info,
    )

    parts: list = [header, args_section, result_section, raw_section]
    if man_section is not None:
        parts.append(man_section)

    return Group(*parts)


# ---------------------------------------------------------------------------
# HELP_CONTENT and render_help_modal
# ---------------------------------------------------------------------------

HELP_CONTENT: list[tuple[list[str], str]] = [
    (["F1", "?"], "Toggle this help"),
    (["Tab"], "Switch focus between list and details"),
    (["f"], "Edit filter expression"),
    (["/"], "Grep (start regex filter)"),
    (["%"], "Cycle family presets"),
    (["h"], "Hide selected syscall"),
    (["H"], "Show only selected syscall"),
    (["p"], "Filter to selected PID"),
    (["P"], "Exclude selected PID"),
    (["x"], "Cycle display mode (auto/hex/str)"),
    (["m"], "Toggle man page"),
    (["d", "u"], "Page down / up"),
    (["g", "G"], "Jump to top / bottom"),
    (["F"], "Follow selected FD"),
    (["<", ">"], "Jump to prev / next syscall on same FD"),
    (["^"], "Jump to FD origin (open/socket/etc.)"),
    (["Alt-f"], "Clear filter"),
    (["Ctrl-c"], "Quit"),
]


def render_help_modal(*, theme: Theme, width: int, height: int) -> Panel:
    """Render the keyboard shortcuts help modal.

    Port of OCaml render_help_modal (lines 1307-1353).
    Returns a Rich Panel renderable.
    """
    # Calculate max key width to align descriptions
    max_key_width = 0
    for keys, _ in HELP_CONTENT:
        w = sum(len(k) for k in keys) + 3 * (len(keys) - 1)  # " / " between keys
        max_key_width = max(max_key_width, w)

    rows: list[Text] = []
    for keys, desc in HELP_CONTENT:
        row = Text()
        for j, k in enumerate(keys):
            if j > 0:
                row.append(" / ", style=_style(theme, theme.dim))
            row.append(k, style=_style(theme, theme.key_hint, bold=True))
        key_width = sum(len(k) for k in keys) + 3 * (len(keys) - 1)
        padding = max(0, max_key_width + 2 - key_width)
        row.append(" " * padding, style=Style(bgcolor=theme.bg))
        row.append(desc, style=_style(theme, theme.fg))
        rows.append(row)

    title_text = Text("Keyboard Shortcuts", style=_style(theme, theme.accent, bold=True))
    empty = Text("", style=_style(theme, theme.fg))
    close_text = Text("Esc to close", style=_style(theme, theme.dim))

    content = Group(title_text, empty, *rows, empty, close_text)

    return Panel(
        content,
        border_style=Style(color=theme.accent, bgcolor=theme.bg),
        style=Style(bgcolor=theme.bg),
    )


# ---------------------------------------------------------------------------
# render_filter_label
# ---------------------------------------------------------------------------

def render_filter_label(
    editor_state,
    *,
    current_filter: list,
    theme: Theme,
    max_chars: int,
) -> Text:
    """Render the filter label with optional editing cursor.

    Port of OCaml filter_editor.ml render_label (lines 52-150).
    `editor_state` is filter_editor.EditState | None.
    """
    from strace_ui import filter_editor as FE

    if editor_state is not None and isinstance(editor_state, FE.EditState):
        buf = editor_state.buf
        cursor = editor_state.cursor

        prefix_len = 3  # " f:"
        available = max_chars - prefix_len

        # Total display length: buffer text + 1 trailing slot for cursor at end
        total_display_len = len(buf) + 1

        before_cursor = buf[:cursor]
        if cursor < len(buf):
            cursor_char = buf[cursor]
            after_cursor = buf[cursor + 1:] + " "
        else:
            cursor_char = " "
            after_cursor = ""

        if total_display_len > available:
            buf_len = len(buf)
            cols_for_sides = available - 1
            right_content_len = (buf_len - cursor) if cursor < buf_len else 0
            half = cols_for_sides // 2
            right_cols = min(right_content_len, max(half, cols_for_sides - cursor))
            left_cols = cols_for_sides - right_cols

            window_start = cursor - left_cols
            if window_start > 0:
                before_cursor = "…" + buf[window_start + 1:cursor]
            else:
                before_cursor = buf[:cursor]

            if cursor < buf_len:
                cursor_char = buf[cursor]
            else:
                cursor_char = " "

            if cursor < buf_len and right_cols > 0:
                after_start = cursor + 1
                after_text_len = buf_len - after_start
                if after_text_len + 1 <= right_cols:
                    after_cursor = buf[after_start:] + " "
                elif right_cols <= 1:
                    after_cursor = "…"
                else:
                    after_cursor = buf[after_start:after_start + right_cols - 1] + "…"
            else:
                after_cursor = ""

        text_style = _style(theme, theme.fg)
        cursor_style = Style(color=theme.bg, bgcolor=theme.accent)

        result = Text()
        result.append(" f", style=_style(theme, theme.key_hint, bold=True))
        result.append(":", style=_style(theme, theme.fg, bold=True))
        result.append(before_cursor, style=text_style)
        result.append(cursor_char, style=cursor_style)
        result.append(after_cursor, style=text_style)
        return result
    else:
        # Not editing — show current filter display string
        filter_str = F.to_display_string(current_filter)
        # Truncate if too long: max_chars - 3 chars for " f:"
        avail = max_chars - 3
        if len(filter_str) > avail:
            filter_str = filter_str[:avail - 1] + "…"

        result = Text()
        result.append(" f", style=_style(theme, theme.key_hint, bold=True))
        result.append(f":{filter_str} ", style=_style(theme, theme.fg, bold=True))
        return result
