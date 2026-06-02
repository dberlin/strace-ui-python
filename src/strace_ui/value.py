"""value: faithful Python port of OCaml strace_value.ml.

Parsed representation of strace value syntax.  Strace outputs structured values
like ``{sa_family=AF_INET, sin_port=htons(0)}`` which we parse into a tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strace_ui.display_utils import split_top_level


# ---------------------------------------------------------------------------
# Tagged-union dataclasses
# ---------------------------------------------------------------------------

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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Struct):
            return NotImplemented
        return self.fields == other.fields

    def __hash__(self) -> int:
        return hash(tuple(self.fields))


@dataclass(frozen=True)
class Array:
    elems: list  # list[Value]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Array):
            return NotImplemented
        return self.elems == other.elems

    def __hash__(self) -> int:
        return hash(tuple(self.elems))


Value = Atom | String | Struct | Call | Array


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_struct_or_array(v: Value) -> bool:
    return isinstance(v, (Struct, Array))


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def parse(s: str) -> Value:
    """Parse a strace value string into a tree (port of strace_value.ml lines 20-78)."""
    s = s.strip()
    if not s:
        return Atom("")

    if s.startswith('"'):
        # Strip ONE leading and ONE trailing quote.
        content = s
        if content.startswith('"'):
            content = content[1:]
        if content.endswith('"'):
            content = content[:-1]
        return String(content)

    if s.startswith('{'):
        # Struct: {key=value, key=value, ...}
        inner = s
        if inner.startswith('{'):
            inner = inner[1:]
        if inner.endswith('}'):
            inner = inner[:-1]
        inner = inner.strip()
        raw_fields = split_top_level(inner, ",")
        parsed_fields: list[tuple[str, Value]] = []
        for field in raw_fields:
            field = field.strip()
            if not field:
                continue
            eq_pos = field.find('=')
            if eq_pos != -1:
                key = field[:eq_pos].strip()
                val = field[eq_pos + 1:].strip()
                parsed_fields.append((key, parse(val)))
            else:
                parsed_fields.append((field, Atom("")))
        return Struct(parsed_fields)

    if s.startswith('['):
        # Array: [elem, elem, ...]
        inner = s
        if inner.startswith('['):
            inner = inner[1:]
        if inner.endswith(']'):
            inner = inner[:-1]
        inner = inner.strip()
        if not inner:
            return Array([])
        elems_raw = split_top_level(inner, ",")
        return Array([parse(e.strip()) for e in elems_raw])

    # Check for function call: name(args)
    paren_pos = s.find('(')
    if paren_pos != -1:
        name = s[:paren_pos]
        rest = s[paren_pos + 1:]
        if name.strip() and rest.strip().endswith(')'):
            arg = rest.strip()
            if arg.endswith(')'):
                arg = arg[:-1]
            arg = arg.strip()
            return Call(name.strip(), arg)

    return Atom(s)


# ---------------------------------------------------------------------------
# fold_tree
# ---------------------------------------------------------------------------

def fold_tree(
    t: Value,
    *,
    emit: Callable[[str], None],
    render_atom: Callable[..., str],
    render_string: Callable[[str], list[str]],
    render_call: Callable[..., str],
    render_prefix: Callable[..., str],
    render_prefix_with_value: Callable[..., str],
    render_prefix_with_multi: Callable[..., None],
) -> None:
    """Generic tree fold — port of strace_value.ml lines 91-159."""

    def walk(indent: str, node: Value) -> None:
        if isinstance(node, Atom):
            emit(render_atom(indent, node.value))

        elif isinstance(node, String):
            for view in render_string(node.value):
                emit(view)

        elif isinstance(node, Call):
            emit(render_call(indent, node.name, node.arg))

        elif isinstance(node, Struct):
            n = len(node.fields)
            for i, (key, value) in enumerate(node.fields):
                is_last = i == n - 1
                prefix = "╰─" if is_last else "├─"
                child_indent_suffix = "  " if is_last else "│ "
                if _is_struct_or_array(value):
                    emit(render_prefix(indent, prefix, key))
                    walk(indent + child_indent_suffix, value)
                else:
                    if isinstance(value, Atom) and value.value == "":
                        emit(render_prefix(indent, prefix, key))
                    elif isinstance(value, Atom):
                        emit(render_prefix_with_value(indent, prefix, key, value.value))
                    elif isinstance(value, String):
                        views = render_string(value.value)
                        render_prefix_with_multi(
                            emit,
                            indent,
                            indent + child_indent_suffix,
                            prefix,
                            key,
                            views,
                        )
                    elif isinstance(value, Call):
                        emit(render_prefix_with_value(
                            indent, prefix, key, f"{value.name}({value.arg})"
                        ))
                    # Struct/Array already handled above; unreachable here

        elif isinstance(node, Array):
            n = len(node.elems)
            for i, elem in enumerate(node.elems):
                is_last = i == n - 1
                prefix = "╰─" if is_last else "├─"
                child_indent_suffix = "  " if is_last else "│ "
                label = f"[{i}]"
                if _is_struct_or_array(elem):
                    emit(render_prefix(indent, prefix, label))
                    walk(indent + child_indent_suffix, elem)
                else:
                    if isinstance(elem, Atom):
                        emit(render_prefix(indent, prefix, elem.value))
                    elif isinstance(elem, String):
                        views = render_string(elem.value)
                        render_prefix_with_multi(
                            emit,
                            indent,
                            indent + child_indent_suffix,
                            prefix,
                            "",
                            views,
                        )
                    elif isinstance(elem, Call):
                        emit(render_prefix(
                            indent, prefix, f"{elem.name}({elem.arg})"
                        ))
                    # Struct/Array already handled above; unreachable here

    walk("", t)


# ---------------------------------------------------------------------------
# to_lines
# ---------------------------------------------------------------------------

def _render_prefix_with_multi(
    emit: Callable[[str], None],
    indent: str,
    child_indent: str,
    prefix: str,
    key: str,
    views: list[str],
) -> None:
    """Port of strace_value.ml lines 174-189."""
    if not views:
        return
    if len(views) == 1:
        single = views[0]
        if not key:
            emit(indent + prefix + single)
        else:
            emit(indent + prefix + key + " = " + single)
    elif not key:
        # multiple, empty key: first inline, rest at child_indent
        emit(indent + prefix + views[0])
        for line in views[1:]:
            emit(child_indent + line)
    else:
        emit(indent + prefix + key + " =")
        for line in views:
            emit(child_indent + line)


def to_lines(
    t: Value,
    render_string: Callable[[str], list[str]] | None = None,
) -> list[str]:
    """Render a parsed value as an expectree-like list of strings.

    Port of strace_value.ml lines 163-191.
    """
    if render_string is None:
        render_string = lambda s: ['"' + s + '"']

    lines: list[str] = []

    fold_tree(
        t,
        emit=lines.append,
        render_atom=lambda indent, s: indent + s,
        render_string=render_string,
        render_call=lambda indent, name, arg: indent + f"{name}({arg})",
        render_prefix=lambda indent, prefix, label: indent + prefix + label,
        render_prefix_with_value=lambda indent, prefix, key, value: (
            indent + prefix + key + " = " + value
        ),
        render_prefix_with_multi=_render_prefix_with_multi,
    )

    return lines
