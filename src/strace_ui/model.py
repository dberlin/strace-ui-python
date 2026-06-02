"""model: faithful Python port of the Elm-style reducer in OCaml strace_ui_app.ml.

Covers:
  - RenderMode, Focus (lines 6-54)
  - Helper functions: is_fd_return_type, extract_fd_numbers, buffer_meaningful_length
    (lines 124-187, 889-913)
  - Model dataclass, Action union (lines 56-122)
  - resolve_fds, passes_filter, fd_follow_filter, find_filtered_index_matching_filter,
    re_resolve_child_fds, update_filter_from_selected (lines 189-316)
  - resolve_pid_info_via_procfs, default_model (lines 607-660)
  - apply_action reducer (lines 318-605)
"""
from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from typing import Callable, Optional

from strace_ui import parser
from strace_ui import schema
from strace_ui import filter as F
from strace_ui import filter_editor as FE
from strace_ui.fd_tracker import FdTracker, FdId
from strace_ui.pid_map import PidMap, PidInfo
from strace_ui.virtual_list import VirtualList
from strace_ui.display_utils import decode_strace_escapes, strip_fd_annotations


# ---------------------------------------------------------------------------
# Char.is_print equivalent — OCaml considers bytes 32..126 printable
# ---------------------------------------------------------------------------

def _is_print(c: str) -> bool:
    """Mirror OCaml Char.is_print: bytes 32-126 inclusive are printable."""
    n = ord(c)
    return 32 <= n <= 126


# ---------------------------------------------------------------------------
# RenderMode (OCaml lines 6-47)
# ---------------------------------------------------------------------------

class RenderMode(enum.Enum):
    AUTO = "auto"
    HEXDUMP = "hexdump"
    STRING = "string"

    def cycle(self) -> "RenderMode":
        """AUTO → HEXDUMP → STRING → AUTO"""
        _next = {
            RenderMode.AUTO: RenderMode.HEXDUMP,
            RenderMode.HEXDUMP: RenderMode.STRING,
            RenderMode.STRING: RenderMode.AUTO,
        }
        return _next[self]

    def to_short_string(self) -> str:
        _map = {
            RenderMode.AUTO: "auto",
            RenderMode.HEXDUMP: "hex",
            RenderMode.STRING: "str",
        }
        return _map[self]

    @staticmethod
    def should_hexdump_in_auto(escaped_content: str) -> bool:
        """Return True if decoded content contains non-text bytes.

        Port of OCaml: decode escapes, check each char for n>127 or
        (not printable and not in \\n\\r\\t ).
        """
        decoded = decode_strace_escapes(escaped_content)
        for c in decoded:
            n = ord(c)
            if n > 127:
                return True
            if (not _is_print(c)
                    and c != "\n"
                    and c != "\r"
                    and c != "\t"
                    and c != " "):
                return True
        return False

    def use_hexdump(self, *, escaped_content: str) -> bool:
        """Return True when hexdump rendering should be used for this content."""
        if self is RenderMode.HEXDUMP:
            return True
        if self is RenderMode.STRING:
            return False
        # AUTO
        return RenderMode.should_hexdump_in_auto(escaped_content)


# ---------------------------------------------------------------------------
# Focus (OCaml lines 49-54)
# ---------------------------------------------------------------------------

class Focus(enum.Enum):
    SYSCALL_LIST = "syscall_list"
    DETAIL_PANE = "detail_pane"


# ---------------------------------------------------------------------------
# is_fd_return_type (OCaml lines 126-137)
# ---------------------------------------------------------------------------

def is_fd_return_type(*, syscall_name: str, args_raw: str) -> bool:
    """Return True if the syscall returns a file descriptor."""
    info = schema.lookup(syscall_name)
    if info is None:
        return False
    sig = info.best_signature(arg_count=len(parser.split_args(args_raw)))
    return sig.return_type.is_file_descriptor()


# ---------------------------------------------------------------------------
# extract_fd_numbers (OCaml lines 139-187)
# ---------------------------------------------------------------------------

def extract_fd_numbers(line: parser.ParsedLine) -> list[int]:
    """Extract all FD numbers referenced in a parsed syscall line.

    Checks both argument positions (via schema) and the return value.
    Port of OCaml lines 139-187.
    """
    args = parser.split_args(line.args_raw)
    info = schema.lookup(line.syscall_name)
    arg_fds: list[int] = []

    if info is not None:
        sig = info.best_signature(arg_count=len(args))
        for i, spec in enumerate(sig.args):
            if spec.arg_type.is_file_descriptor():
                if i < len(args):
                    s = args[i].strip()
                    if s.startswith("["):
                        # Bracket notation like [3, 4] from pipe/socketpair
                        inside = s.lstrip("[").rstrip("]")
                        for part in inside.split(","):
                            fd = parser.extract_fd_number(part.strip())
                            if fd is not None:
                                arg_fds.append(fd)
                    else:
                        fd = parser.extract_fd_number(s)
                        if fd is not None:
                            arg_fds.append(fd)
    else:
        # No schema: try first arg
        if args:
            fd = parser.extract_fd_number(args[0].strip())
            if fd is not None:
                arg_fds.append(fd)

    # Return value fds
    return_fds: list[int] = []
    if is_fd_return_type(syscall_name=line.syscall_name, args_raw=line.args_raw):
        r = parser.extract_return_int(line.result)
        if r is not None and r >= 0:
            return_fds.append(r)

    return arg_fds + return_fds


# ---------------------------------------------------------------------------
# buffer_meaningful_length (OCaml lines 891-913)
# ---------------------------------------------------------------------------

def buffer_meaningful_length(
    *,
    syscall_name: str,
    arg_index: int,
    args: list[str],
    result,
) -> Optional[int]:
    """Return the meaningful byte count for a buffer argument, or None.

    Port of OCaml lines 891-913.
    """
    def return_int() -> Optional[int]:
        return parser.extract_return_int(result)

    def arg_int(i: int) -> Optional[int]:
        if i >= len(args):
            return None
        try:
            return int(strip_fd_annotations(args[i]).strip())
        except (ValueError, TypeError):
            return None

    # Match (syscall_name, arg_index)
    if syscall_name in ("read", "pread64") and arg_index == 1:
        return return_int()
    if syscall_name in ("readlink", "readlinkat") and arg_index == 1:
        return return_int()
    if syscall_name == "recvfrom" and arg_index == 1:
        return return_int()
    if syscall_name == "recvmsg" and arg_index == 1:
        return return_int()
    if syscall_name == "getrandom" and arg_index == 0:
        return return_int()
    if syscall_name == "getcwd" and arg_index == 0:
        return return_int()
    if syscall_name in ("write", "pwrite64") and arg_index == 1:
        return arg_int(2)
    if syscall_name == "sendto" and arg_index == 1:
        return arg_int(2)
    if syscall_name == "sendmsg" and arg_index == 1:
        return arg_int(2)
    return None


# ---------------------------------------------------------------------------
# Model dataclass (OCaml lines 56-87)
# ---------------------------------------------------------------------------

@dataclass
class Model:
    """App state — port of OCaml Model.t."""
    syscall_list: VirtualList
    fd_tracker: FdTracker
    syscall_filter: list          # list[F.Term]
    render_mode: RenderMode
    next_index: int
    show_man_page: bool
    man_page_cache: dict          # dict[str, str]
    dns_cache: dict               # dict[str, str]
    focus: Focus
    show_help: bool
    filter_editor: object         # FE.EditorState (EditState | None)
    pending_syscalls: dict        # dict[int, int]  pid → raw_index in syscall_list
    resolved_fds: dict            # dict[int, list[FdId]]  parsed_index → fd_ids
    pid_map: PidMap
    resolve_pid_info: Callable    # pid → PidInfo | None

    # Convenience delegates
    def selected_index(self) -> int:
        return self.syscall_list.selected_index

    def filtered_count(self) -> int:
        return self.syscall_list.filtered_count()

    def get_filtered(self, i: int):
        return self.syscall_list.get_filtered(i)

    def get_selected(self):
        return self.syscall_list.get_selected()


# ---------------------------------------------------------------------------
# Action union — frozen dataclasses (OCaml lines 89-122)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AddLine:
    line: str

@dataclass(frozen=True)
class SelectUp:
    pass

@dataclass(frozen=True)
class SelectDown:
    pass

@dataclass(frozen=True)
class SelectTop:
    pass

@dataclass(frozen=True)
class SelectBottom:
    pass

@dataclass(frozen=True)
class JumpToIndex:
    index: int

@dataclass(frozen=True)
class SetFilter:
    filter_str: str

@dataclass(frozen=True)
class HideSelected:
    pass

@dataclass(frozen=True)
class ShowOnlySelected:
    pass

@dataclass(frozen=True)
class FilterSelectedPid:
    pass

@dataclass(frozen=True)
class ExcludeSelectedPid:
    pass

@dataclass(frozen=True)
class CyclePresetFilter:
    pass

@dataclass(frozen=True)
class FilterEdit:
    action: object  # FE.Action

@dataclass(frozen=True)
class ToggleHelp:
    pass

@dataclass(frozen=True)
class ToggleRenderMode:
    pass

@dataclass(frozen=True)
class ToggleManPage:
    pass

@dataclass(frozen=True)
class SetManPage:
    name: str
    content: str

@dataclass(frozen=True)
class SetDnsEntry:
    ip: str
    hostname: str

@dataclass(frozen=True)
class ToggleFocus:
    pass

@dataclass(frozen=True)
class JumpToFilteredIndex:
    idx: int

@dataclass(frozen=True)
class FollowFd:
    pass

@dataclass(frozen=True)
class JumpFdPrev:
    pass

@dataclass(frozen=True)
class JumpFdNext:
    pass

@dataclass(frozen=True)
class JumpFdOrigin:
    pass


# ---------------------------------------------------------------------------
# resolve_fds (OCaml lines 191-195)
# ---------------------------------------------------------------------------

def resolve_fds(
    line: parser.ParsedLine,
    *,
    fd_tracker: FdTracker,
) -> list[FdId]:
    """Resolve all FD numbers in *line* to FdId values via the tracker."""
    result = []
    for n in extract_fd_numbers(line):
        fid = fd_tracker.resolve_fd_or_default(pid=line.pid, fd_number=n)
        if fid is not None:
            result.append(fid)
    return result


# ---------------------------------------------------------------------------
# passes_filter (OCaml lines 236-250)
# ---------------------------------------------------------------------------

def passes_filter(
    line: parser.ParsedLine,
    syscall_filter: list,
    fd_tracker: FdTracker,
    resolved_fds: dict,
) -> bool:
    """Return True if *line* passes *syscall_filter*."""
    fd_ids = resolved_fds.get(line.index)
    if fd_ids is None:
        fd_ids = resolve_fds(line, fd_tracker=fd_tracker)
    return F.passes(
        syscall_filter,
        F.SyscallInfo(
            syscall_name=line.syscall_name,
            pid=line.pid,
            fd_ids=fd_ids,
            raw_line=line.raw_line,
        ),
        fd_tracker=fd_tracker,
    )


# ---------------------------------------------------------------------------
# fd_follow_filter (OCaml lines 254-267)
# ---------------------------------------------------------------------------

def fd_follow_filter(model: Model, line: parser.ParsedLine):
    """Build the fd-follow filter for a line, or None if no fd present."""
    fd_ids = model.resolved_fds.get(line.index) or []
    if fd_ids:
        first = fd_ids[0]
        return F.parse(f"rel:{line.pid} fd:{first.fd_number}.{first.generation}")
    fd_numbers = extract_fd_numbers(line)
    if fd_numbers:
        return F.parse(f"rel:{line.pid} fd:{fd_numbers[0]}")
    return None


# ---------------------------------------------------------------------------
# find_filtered_index_matching_filter (OCaml lines 271-291)
# ---------------------------------------------------------------------------

def find_filtered_index_matching_filter(
    model: Model,
    flt: list,
    frm: int,
    direction: int,
) -> int:
    """Scan from frm+direction for a line matching flt; return frm if none found."""
    filtered_count = model.filtered_count()
    i = frm + direction
    while 0 <= i < filtered_count:
        candidate = model.get_filtered(i)
        if candidate is not None:
            if passes_filter(candidate, flt, model.fd_tracker, model.resolved_fds):
                return i
        i += direction
    return frm


# ---------------------------------------------------------------------------
# re_resolve_child_fds (OCaml lines 200-234)
# ---------------------------------------------------------------------------

_FORK_SYSCALLS = frozenset({"clone", "clone3", "fork", "vfork"})


def re_resolve_child_fds(
    syscall_list: VirtualList,
    fd_tracker: FdTracker,
    resolved_fds: dict,
    line: parser.ParsedLine,
) -> dict:
    """After a fork/clone, re-resolve fds for any child syscalls already in the list.

    Returns a new resolved_fds dict (copy-on-write semantics).
    Port of OCaml lines 200-234.
    """
    if line.syscall_name not in _FORK_SYSCALLS:
        return resolved_fds

    child = parser.extract_return_int(line.result)
    if child is None or child <= 0:
        return resolved_fds

    new_resolved = dict(resolved_fds)
    total = syscall_list.total_count()
    for i in range(total):
        item = syscall_list.get_raw(i)
        if item.pid == child:
            existing = new_resolved.get(item.index)
            if not existing:  # None or empty list
                fd_ids = resolve_fds(item, fd_tracker=fd_tracker)
                new_resolved[item.index] = fd_ids
    return new_resolved


# ---------------------------------------------------------------------------
# update_filter_from_selected (OCaml lines 298-316)
# ---------------------------------------------------------------------------

def update_filter_from_selected(model: Model, f: Callable) -> Model:
    """Apply *f* to (current_filter, selected_line) and refilter.

    Port of OCaml lines 298-316.
    """
    sel = model.get_selected()
    if sel is None:
        return model
    new_filter = f(model.syscall_filter, sel)
    new_list = model.syscall_list.refilter(
        lambda ln: passes_filter(ln, new_filter, model.fd_tracker, model.resolved_fds)
    )
    return dataclasses.replace(
        model,
        syscall_filter=new_filter,
        syscall_list=new_list,
    )


# ---------------------------------------------------------------------------
# resolve_pid_info_via_procfs (OCaml lines 607-632)
# ---------------------------------------------------------------------------

def resolve_pid_info_via_procfs(pid: int) -> Optional[PidInfo]:
    """Read process info from /proc/{pid}; return None on any error."""
    try:
        proc_dir = f"/proc/{pid}"
        with open(f"{proc_dir}/cmdline", "rb") as f:
            raw = f.read()
        cmdline = raw.replace(b"\x00", b" ").rstrip(b" ").rstrip(b"\x00").decode("utf-8", errors="replace").rstrip()
        with open(f"{proc_dir}/comm") as f:
            thread_name = f.read().rstrip()
        with open(f"{proc_dir}/status") as f:
            status_text = f.read()
        # Find Tgid line
        tgid = None
        for status_line in status_text.splitlines():
            if status_line.startswith("Tgid:"):
                rest = status_line[len("Tgid:"):].strip()
                try:
                    tgid = int(rest)
                except ValueError:
                    pass
                break
        is_thread = (tgid != pid) if tgid is not None else False
        if not cmdline:
            cmdline = thread_name
        return PidInfo(cmdline=cmdline, thread_name=thread_name, is_thread=is_thread)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# default_model (OCaml lines 634-660)
# ---------------------------------------------------------------------------

def default_model(
    primary_pid: Optional[int] = None,
    resolve_pid_info: Callable = resolve_pid_info_via_procfs,
) -> Model:
    """Build a fresh Model, optionally registering a primary PID."""
    pid_map = PidMap.empty()
    if primary_pid is not None:
        pid_map = pid_map.register(primary_pid)
        info = resolve_pid_info(primary_pid)
        if info is not None:
            pid_map = pid_map.set_info(primary_pid, info)

    return Model(
        syscall_list=VirtualList.create(),
        fd_tracker=FdTracker.empty(),
        syscall_filter=[],
        render_mode=RenderMode.AUTO,
        next_index=0,
        show_man_page=False,
        man_page_cache={},
        dns_cache={},
        focus=Focus.SYSCALL_LIST,
        show_help=False,
        filter_editor=None,
        pending_syscalls={},
        resolved_fds={},
        pid_map=pid_map,
        resolve_pid_info=resolve_pid_info,
    )


# ---------------------------------------------------------------------------
# apply_action reducer (OCaml lines 318-605)
# ---------------------------------------------------------------------------

def apply_action(model: Model, action: object) -> Model:
    """Apply *action* to *model* and return a new Model.

    Faithful port of OCaml apply_action_pure (lines 318-605).
    """
    # ---- AddLine -----------------------------------------------------------
    if isinstance(action, AddLine):
        parsed = parser.parse_line(model.next_index, action.line)
        if parsed is None:
            return dataclasses.replace(model, next_index=model.next_index + 1)

        # Register pid (new pid → try to resolve info)
        is_new_pid = model.pid_map.short_id(parsed.pid) is None
        pid_map = model.pid_map.register(parsed.pid)
        if is_new_pid:
            info = model.resolve_pid_info(parsed.pid)
            if info is not None:
                pid_map = pid_map.set_info(parsed.pid, info)
        model = dataclasses.replace(model, pid_map=pid_map)

        # Branch on result type
        if isinstance(parsed.result, parser.Unfinished):
            # Record as pending; resolve fds with current tracker (before update)
            fd_ids = resolve_fds(parsed, fd_tracker=model.fd_tracker)
            resolved = {**model.resolved_fds, parsed.index: fd_ids}
            new_list = model.syscall_list.append(
                parsed,
                passes_filter=passes_filter(
                    parsed, model.syscall_filter, model.fd_tracker, resolved
                ),
            )
            pending_idx = new_list.total_count() - 1
            pending = {**model.pending_syscalls, parsed.pid: pending_idx}
            return dataclasses.replace(
                model,
                syscall_list=new_list,
                pending_syscalls=pending,
                resolved_fds=resolved,
                next_index=model.next_index + 1,
            )

        elif isinstance(parsed.result, parser.Resumed):
            if parsed.pid in model.pending_syscalls:
                # Merge with the pending unfinished call
                pending_idx = model.pending_syscalls[parsed.pid]
                original = model.syscall_list.get_raw(pending_idx)
                merged = parser.merge_resumed(original, parsed)
                new_list = model.syscall_list.set_item(pending_idx, merged)

                fd_ids_before = resolve_fds(merged, fd_tracker=model.fd_tracker)
                new_tracker = model.fd_tracker.update(merged)
                fd_ids_after = resolve_fds(merged, fd_tracker=new_tracker)
                fd_ids = sorted(set(fd_ids_before + fd_ids_after))

                resolved = {**model.resolved_fds, merged.index: fd_ids}
                resolved = re_resolve_child_fds(new_list, new_tracker, resolved, merged)

                pending = {k: v for k, v in model.pending_syscalls.items() if k != parsed.pid}
                return dataclasses.replace(
                    model,
                    syscall_list=new_list,
                    fd_tracker=new_tracker,
                    pending_syscalls=pending,
                    resolved_fds=resolved,
                    next_index=model.next_index + 1,
                )
            else:
                # No matching pending; treat as normal completed (use parsed)
                fd_ids_before = resolve_fds(parsed, fd_tracker=model.fd_tracker)
                new_tracker = model.fd_tracker.update(parsed)
                fd_ids_after = resolve_fds(parsed, fd_tracker=new_tracker)
                fd_ids = sorted(set(fd_ids_before + fd_ids_after))
                resolved = {**model.resolved_fds, parsed.index: fd_ids}
                new_list = model.syscall_list.append(
                    parsed,
                    passes_filter=passes_filter(
                        parsed, model.syscall_filter, new_tracker, resolved
                    ),
                )
                resolved = re_resolve_child_fds(new_list, new_tracker, resolved, parsed)
                return dataclasses.replace(
                    model,
                    syscall_list=new_list,
                    fd_tracker=new_tracker,
                    resolved_fds=resolved,
                    next_index=model.next_index + 1,
                )

        else:
            # Normal completed syscall
            fd_ids_before = resolve_fds(parsed, fd_tracker=model.fd_tracker)
            new_tracker = model.fd_tracker.update(parsed)
            fd_ids_after = resolve_fds(parsed, fd_tracker=new_tracker)
            fd_ids = sorted(set(fd_ids_before + fd_ids_after))
            resolved = {**model.resolved_fds, parsed.index: fd_ids}
            new_list = model.syscall_list.append(
                parsed,
                passes_filter=passes_filter(
                    parsed, model.syscall_filter, new_tracker, resolved
                ),
            )
            return dataclasses.replace(
                model,
                syscall_list=new_list,
                fd_tracker=new_tracker,
                resolved_fds=resolved,
                next_index=model.next_index + 1,
            )

    # ---- Navigation --------------------------------------------------------
    elif isinstance(action, SelectUp):
        return dataclasses.replace(model, syscall_list=model.syscall_list.select_up())
    elif isinstance(action, SelectDown):
        return dataclasses.replace(model, syscall_list=model.syscall_list.select_down())
    elif isinstance(action, SelectTop):
        return dataclasses.replace(model, syscall_list=model.syscall_list.select_top())
    elif isinstance(action, SelectBottom):
        return dataclasses.replace(model, syscall_list=model.syscall_list.select_bottom())

    elif isinstance(action, JumpToIndex):
        # Find the filtered position of the line with raw index == action.index
        target = model.selected_index()
        for i in range(model.filtered_count()):
            line = model.get_filtered(i)
            if line is not None and line.index == action.index:
                target = i
        return dataclasses.replace(
            model,
            syscall_list=model.syscall_list.jump_to_filtered_index(target),
        )

    elif isinstance(action, SetFilter):
        new_filter = F.parse(action.filter_str)
        new_list = model.syscall_list.refilter(
            lambda ln: passes_filter(ln, new_filter, model.fd_tracker, model.resolved_fds)
        )
        return dataclasses.replace(model, syscall_filter=new_filter, syscall_list=new_list)

    elif isinstance(action, HideSelected):
        return update_filter_from_selected(
            model,
            lambda flt, line: F.add_exclusion(flt, syscall_name=line.syscall_name),
        )

    elif isinstance(action, ShowOnlySelected):
        return update_filter_from_selected(
            model,
            lambda flt, line: F.add_inclusion(flt, syscall_name=line.syscall_name),
        )

    elif isinstance(action, FilterSelectedPid):
        return update_filter_from_selected(
            model,
            lambda flt, line: F.add_pid_filter(flt, pid=line.pid),
        )

    elif isinstance(action, ExcludeSelectedPid):
        return update_filter_from_selected(
            model,
            lambda flt, line: F.add_pid_exclusion(flt, pid=line.pid),
        )

    elif isinstance(action, CyclePresetFilter):
        # Cycle: "" → %desc → %file → %memory → %net → %process → %signal → %ipc → ""
        families = [f for f in schema.Family if f != schema.Family.ALL]
        presets = [""] + [f.to_display_string() for f in families]
        current = F.to_normalized_string(model.syscall_filter)
        try:
            idx = presets.index(current)
        except ValueError:
            idx = -1
        next_str = presets[(idx + 1) % len(presets)]
        return apply_action(model, SetFilter(next_str))

    elif isinstance(action, FilterEdit):
        new_editor, submitted = FE.apply_action(
            model.filter_editor, model.syscall_filter, action.action
        )
        model2 = dataclasses.replace(model, filter_editor=new_editor)
        if submitted is not None:
            return apply_action(model2, SetFilter(submitted))
        return model2

    elif isinstance(action, ToggleHelp):
        return dataclasses.replace(model, show_help=not model.show_help)

    elif isinstance(action, ToggleRenderMode):
        return dataclasses.replace(model, render_mode=model.render_mode.cycle())

    elif isinstance(action, ToggleManPage):
        return dataclasses.replace(model, show_man_page=not model.show_man_page)

    elif isinstance(action, SetManPage):
        return dataclasses.replace(
            model, man_page_cache={**model.man_page_cache, action.name: action.content}
        )

    elif isinstance(action, SetDnsEntry):
        return dataclasses.replace(
            model, dns_cache={**model.dns_cache, action.ip: action.hostname}
        )

    elif isinstance(action, ToggleFocus):
        new_focus = (
            Focus.DETAIL_PANE
            if model.focus is Focus.SYSCALL_LIST
            else Focus.SYSCALL_LIST
        )
        return dataclasses.replace(model, focus=new_focus)

    elif isinstance(action, JumpToFilteredIndex):
        return dataclasses.replace(
            model,
            syscall_list=model.syscall_list.jump_to_filtered_index(action.idx),
        )

    elif isinstance(action, FollowFd):
        sel = model.get_selected()
        if sel is None:
            return model
        flt = fd_follow_filter(model, sel)
        if flt is not None:
            filter_str = F.to_normalized_string(flt)
        else:
            filter_str = f"rel:{sel.pid}"
        return apply_action(model, SetFilter(filter_str))

    elif isinstance(action, JumpFdPrev):
        sel = model.get_selected()
        if sel is None:
            return model
        flt = fd_follow_filter(model, sel)
        if flt is None:
            return model
        target = find_filtered_index_matching_filter(model, flt, model.selected_index(), -1)
        return dataclasses.replace(
            model,
            syscall_list=model.syscall_list.jump_to_filtered_index(target),
        )

    elif isinstance(action, JumpFdNext):
        sel = model.get_selected()
        if sel is None:
            return model
        flt = fd_follow_filter(model, sel)
        if flt is None:
            return model
        target = find_filtered_index_matching_filter(model, flt, model.selected_index(), 1)
        return dataclasses.replace(
            model,
            syscall_list=model.syscall_list.jump_to_filtered_index(target),
        )

    elif isinstance(action, JumpFdOrigin):
        sel = model.get_selected()
        if sel is None:
            return model
        fd_ids = model.resolved_fds.get(sel.index) or []
        if not fd_ids:
            return model
        fid = fd_ids[0]
        origin = model.fd_tracker.lookup_origin(fid)
        if origin is None:
            return model
        return apply_action(model, JumpToIndex(origin.syscall_index))

    # Unknown action — return unchanged
    return model
