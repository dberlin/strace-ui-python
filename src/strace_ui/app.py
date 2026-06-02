"""app: Textual App for strace_ui.

Holds the Model, dispatches Actions, and manages the two-pane layout.
Handles background strace reading, man-page fetching, and reverse DNS.
"""
from __future__ import annotations

import asyncio
import os
import socket
from asyncio import StreamReader, StreamReaderProtocol
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.events import Key
from textual.widgets import Static

from strace_ui.model import (
    Model, Focus,
    apply_action,
    AddLine, SelectUp, SelectDown, SelectTop, SelectBottom,
    JumpToFilteredIndex,
    SetFilter, HideSelected, ShowOnlySelected,
    FilterSelectedPid, ExcludeSelectedPid, CyclePresetFilter,
    FilterEdit, ToggleHelp, ToggleRenderMode, ToggleManPage,
    SetManPage, SetDnsEntry, ToggleFocus,
    FollowFd, JumpFdPrev, JumpFdNext, JumpFdOrigin,
)
from strace_ui import filter_editor as FE
from strace_ui import schema as schema_mod
from strace_ui.display_utils import extract_ip_addresses
from strace_ui.render import render_help_modal
from strace_ui.themes import Theme
from strace_ui.widgets import SyscallListWidget, DetailWidget


# ---------------------------------------------------------------------------
# HelpOverlay
# ---------------------------------------------------------------------------

class HelpOverlay(Static):
    """Overlay widget that renders the help modal panel.

    Sits in a top CSS layer; its ``display`` is toggled to show/hide it.
    """

    DEFAULT_CSS = """
    HelpOverlay {
        layer: overlay;
        width: 60;
        height: auto;
        offset-x: 50%;
        offset-y: 50%;
        margin-left: -30;
        margin-top: -12;
        dock: none;
        display: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", markup=False, **kwargs)

    def refresh_content(self, theme: Theme, width: int, height: int) -> None:
        """Re-render the help panel with the given dimensions."""
        panel = render_help_modal(theme=theme, width=width, height=height)
        self.update(panel)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class StraceUiApp(App):
    """The main Textual application for strace_ui.

    Pass strace_argv=None to run without launching strace (for testing).
    """

    # Disable default bindings that would interfere with our key handling
    BINDINGS = []

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
        layers: base overlay;
    }
    #main-horizontal {
        height: 1fr;
        layout: horizontal;
        layer: base;
    }
    #list-pane {
        width: 40;
        min-width: 10;
        height: 100%;
    }
    #detail-pane {
        width: 1fr;
        height: 100%;
    }
    """

    def __init__(
        self,
        model: Model,
        theme: Theme,
        strace_argv: Optional[list[str]] = None,
        write_fd: Optional[int] = None,
        read_fd: Optional[int] = None,
    ):
        super().__init__()
        self.model = model
        self.ui_theme = theme  # avoid clash with Textual's built-in .theme attribute
        self._strace_argv = strace_argv
        self._write_fd = write_fd
        self._read_fd = read_fd
        self._strace_proc: Optional[asyncio.subprocess.Process] = None
        self._man_inflight: set[str] = set()
        self._dns_inflight: set[str] = set()
        # Cache of the last-rendered detail "key"; lets us skip the (expensive)
        # detail re-render when nothing the detail pane shows has changed —
        # e.g. when new syscalls are appended without moving the selection.
        self._detail_key: object = object()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-horizontal"):
            yield SyscallListWidget(app_ref=self, id="list-pane")
            yield DetailWidget(app_ref=self, id="detail-pane")
        yield HelpOverlay(id="help-overlay")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Set up theme colours and start the strace reader if needed."""
        self._apply_theme()
        self._refresh_widgets()
        if self._strace_argv is not None:
            self.run_worker(self._strace_reader_worker(), name="strace-reader", exit_on_error=False)

    def on_unmount(self) -> None:
        """Kill strace on exit."""
        self._kill_strace()

    def on_resize(self, event: object) -> None:
        """Re-render the detail pane on resize (its layout is width-dependent)."""
        self._refresh_widgets(force_detail=True)

    # ------------------------------------------------------------------
    # Theme helpers
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """Set Textual CSS variables from our theme so borders use theme colours.

        We update the app's CSS dynamically to apply our custom colour palette.
        """
        # Theme colours are applied via Rich rendering — no Textual CSS override needed.
        # The CSS in CLASS_CSS handles layout; colours come from our render functions.
        pass

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, action: object) -> None:
        """Apply action to the model, refresh widgets, check side effects."""
        self.model = apply_action(self.model, action)
        self._refresh_widgets()
        self._check_effects()

    def _detail_render_key(self) -> object:
        """A cheap value capturing everything the detail pane renders from.

        When this is unchanged between dispatches we can skip the (expensive)
        detail re-render. Appending syscalls that don't move the selection
        leaves this unchanged, so a high-volume trace no longer re-renders the
        detail pane on every line (which was starving keyboard input).
        """
        m = self.model
        sel = m.get_selected()
        if sel is None:
            return (None,)
        return (
            sel.index,
            m.render_mode,
            m.show_man_page,
            m.focus,
            m.man_page_cache.get(sel.syscall_name),
            tuple(sorted(m.dns_cache.items())),
        )

    def _refresh_widgets(self, *, force_detail: bool = False) -> None:
        try:
            list_widget = self.query_one(SyscallListWidget)
            # Set border chrome (filter text, position, edit state) BEFORE the
            # content refresh so it paints in the same frame — setting it inside
            # render() would lag the border one keystroke behind the content.
            list_widget.update_chrome()
            list_widget.refresh()
        except Exception:
            pass
        try:
            detail_widget = self.query_one(DetailWidget)
            key = self._detail_render_key()
            if force_detail or key != self._detail_key:
                self._detail_key = key
                detail_widget.update_detail()
        except Exception:
            pass
        try:
            overlay = self.query_one(HelpOverlay)
            show = self.model.show_help
            if show:
                overlay.refresh_content(
                    theme=self.ui_theme,
                    width=self.size.width,
                    height=self.size.height,
                )
            overlay.display = show
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Side effects
    # ------------------------------------------------------------------

    def _check_effects(self) -> None:
        """After a model change, trigger man-page fetches and DNS lookups."""
        model = self.model
        selected = model.get_selected()
        if selected is None:
            return

        # Man page
        if model.show_man_page:
            name = selected.syscall_name
            if name not in model.man_page_cache and name not in self._man_inflight:
                self._man_inflight.add(name)
                # Determine detail pane width for MANWIDTH
                try:
                    detail_widget = self.query_one(DetailWidget)
                    detail_width = max(40, detail_widget.size.width - 3)
                except Exception:
                    detail_width = 80
                self.run_worker(
                    self._fetch_man_page(name, detail_width),
                    name=f"man-{name}",
                    exit_on_error=False,
                )

        # Reverse DNS
        ips = extract_ip_addresses(selected.args_raw)
        for ip in ips:
            if ip not in model.dns_cache and ip not in self._dns_inflight:
                self._dns_inflight.add(ip)
                self.run_worker(
                    self._fetch_dns(ip),
                    name=f"dns-{ip}",
                    exit_on_error=False,
                )

    async def _fetch_man_page(self, name: str, detail_width: int) -> None:
        """Fetch and cache a man page entry for syscall `name`."""
        info = schema_mod.lookup(name)
        section = 2
        if info is not None and hasattr(info, "man_section") and info.man_section:
            section = info.man_section

        env = {**os.environ, "MANWIDTH": str(max(40, detail_width - 2))}
        try:
            proc = await asyncio.create_subprocess_exec(
                "man", "--nj", str(section), name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            stdout_bytes, _ = await proc.communicate()
            if proc.returncode == 0 and stdout_bytes:
                content = stdout_bytes.decode("utf-8", errors="replace")
            else:
                content = f"Could not load man page for {name}"
        except Exception:
            content = f"Could not load man page for {name}"
        finally:
            self._man_inflight.discard(name)

        self.dispatch(SetManPage(name, content))

    async def _fetch_dns(self, ip: str) -> None:
        """Reverse-DNS lookup for `ip`."""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            hostname = result[0]
        except Exception:
            hostname = ip
        finally:
            self._dns_inflight.discard(ip)

        self.dispatch(SetDnsEntry(ip, hostname))

    # ------------------------------------------------------------------
    # Strace reader
    # ------------------------------------------------------------------

    async def _strace_reader_worker(self) -> None:
        """Launch strace and read its output line by line into the model."""
        assert self._strace_argv is not None
        assert self._write_fd is not None
        assert self._read_fd is not None

        write_fd = self._write_fd
        read_fd = self._read_fd

        try:
            proc = await asyncio.create_subprocess_exec(
                "strace",
                *self._strace_argv,
                stderr=asyncio.subprocess.PIPE,
                pass_fds=(write_fd,),
            )
        except Exception as exc:
            # strace not found or failed to start
            try:
                os.close(write_fd)
            except OSError:
                pass
            try:
                os.close(read_fd)
            except OSError:
                pass
            self.notify(f"Failed to start strace: {exc}", severity="error")
            return

        self._strace_proc = proc

        # Close the write end in the parent — EOF when strace exits
        try:
            os.close(write_fd)
        except OSError:
            pass

        # Wrap the read fd in an asyncio StreamReader
        reader = StreamReader()
        protocol = StreamReaderProtocol(reader)
        loop = asyncio.get_running_loop()
        try:
            await loop.connect_read_pipe(lambda: protocol, os.fdopen(read_fd, "rb", buffering=0))
        except Exception:
            try:
                os.close(read_fd)
            except OSError:
                pass
            return

        # Read lines and dispatch AddLine actions
        while True:
            try:
                line_bytes = await reader.readline()
            except Exception:
                break
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
            if line:
                self.dispatch(AddLine(line))

        # Wait for strace to exit
        try:
            await proc.wait()
        except Exception:
            pass

        # If strace failed before producing output, surface the error
        if proc.returncode != 0 and self.model.next_index == 0:
            stderr_line = ""
            if proc.stderr is not None:
                try:
                    stderr_bytes = await proc.stderr.read(4096)
                    stderr_line = stderr_bytes.decode("utf-8", errors="replace").splitlines()[0] if stderr_bytes else ""
                except Exception:
                    pass
            msg = f"strace: {stderr_line}" if stderr_line else "strace exited with an error"
            self.notify(msg, severity="error")

    def _kill_strace(self) -> None:
        if self._strace_proc is not None:
            try:
                self._strace_proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def on_key(self, event: Key) -> None:
        """Handle all keyboard input."""
        key = event.key
        char = event.character

        model = self.model

        # 1. Ctrl+C → quit
        if key == "ctrl+c":
            self.exit()
            return

        # 2. F1 or "?" → toggle help
        if key == "f1" or char == "?":
            self.dispatch(ToggleHelp())
            return

        # 3. Help is showing: any key dismisses it
        if model.show_help:
            self.dispatch(ToggleHelp())
            return

        # 4. Tab / Shift+Tab → toggle focus
        if key in ("tab", "shift+tab"):
            self.dispatch(ToggleFocus())
            return

        # 5. Filter editing mode
        if FE.is_editing(model.filter_editor):
            fe_action = self._map_filter_key(key, char)
            if fe_action is not None:
                self.dispatch(FilterEdit(fe_action))
            return

        # 6. Normal mode commands
        if char == "f":
            self.dispatch(FilterEdit(FE.Start()))
            return
        if char == "/":
            self.dispatch(FilterEdit(FE.StartRegex()))
            return
        if char == "%":
            self.dispatch(CyclePresetFilter())
            return
        if char == "h":
            self.dispatch(HideSelected())
            return
        if char == "H":
            self.dispatch(ShowOnlySelected())
            return
        if char == "p":
            self.dispatch(FilterSelectedPid())
            return
        if char == "P":
            self.dispatch(ExcludeSelectedPid())
            return
        if char == "x":
            self.dispatch(ToggleRenderMode())
            return
        if char == "m":
            self.dispatch(ToggleManPage())
            return
        if char == "F":
            self.dispatch(FollowFd())
            return
        if char == "<":
            self.dispatch(JumpFdPrev())
            return
        if char == ">":
            self.dispatch(JumpFdNext())
            return
        if char == "^":
            self.dispatch(JumpFdOrigin())
            return

        # Alt+f → clear filter
        if key == "alt+f":
            self.dispatch(SetFilter(""))
            return

        # 7. Navigation
        focus = model.focus
        if char == "j" or key == "down":
            if focus == Focus.SYSCALL_LIST:
                self.dispatch(SelectDown())
            else:
                self._detail_scroll_down()
            return
        if char == "k" or key == "up":
            if focus == Focus.SYSCALL_LIST:
                self.dispatch(SelectUp())
            else:
                self._detail_scroll_up()
            return
        if char == "g":
            if focus == Focus.SYSCALL_LIST:
                self.dispatch(SelectTop())
            else:
                self._detail_scroll_home()
            return
        if char == "G":
            if focus == Focus.SYSCALL_LIST:
                self.dispatch(SelectBottom())
            else:
                self._detail_scroll_end()
            return

        # 8. Page up/down
        # d/ctrl+d/pagedown → page down
        if char == "d" or key in ("ctrl+d", "pagedown"):
            if focus == Focus.SYSCALL_LIST:
                list_height = self._list_height()
                fc = model.filtered_count()
                next_idx = min(fc - 1, model.selected_index() + list_height)
                self.dispatch(JumpToFilteredIndex(next_idx))
            else:
                self._detail_scroll_half_down()
            return
        # u/ctrl+u/pageup → page up
        if char == "u" or key in ("ctrl+u", "pageup"):
            if focus == Focus.SYSCALL_LIST:
                list_height = self._list_height()
                next_idx = max(0, model.selected_index() - list_height)
                self.dispatch(JumpToFilteredIndex(next_idx))
            else:
                self._detail_scroll_half_up()
            return

    # ------------------------------------------------------------------
    # Filter key mapping
    # ------------------------------------------------------------------

    def _map_filter_key(self, key: str, char: Optional[str]) -> Optional[object]:
        """Map a key event to a filter editor action, or None to ignore."""
        if key == "enter":
            return FE.Submit()
        if key == "escape":
            return FE.Cancel()
        if key == "backspace":
            return FE.Backspace()
        if key == "delete":
            return FE.DeleteForward()
        if key == "left":
            return FE.MoveLeft()
        if key == "right":
            return FE.MoveRight()
        if key == "home":
            return FE.MoveToStart()
        if key == "end":
            return FE.MoveToEnd()
        if key == "ctrl+a":
            return FE.MoveToStart()
        if key == "ctrl+e":
            return FE.MoveToEnd()
        if key == "ctrl+b":
            return FE.MoveLeft()
        if key == "ctrl+f":
            return FE.MoveRight()
        if key == "ctrl+d":
            return FE.DeleteForward()
        if key == "ctrl+k":
            return FE.KillToEnd()
        if key == "ctrl+u":
            return FE.KillToStart()
        if key == "ctrl+w":
            return FE.KillWordBackward()
        if key in ("alt+f", "alt+F"):
            return FE.MoveWordForward()
        if key in ("alt+b", "alt+B"):
            return FE.MoveWordBackward()
        # Single printable character
        if char is not None and len(char) == 1 and char.isprintable():
            return FE.Key(char)
        return None

    # ------------------------------------------------------------------
    # Detail pane scroll helpers
    # ------------------------------------------------------------------

    def _get_detail(self) -> Optional[DetailWidget]:
        try:
            return self.query_one(DetailWidget)
        except Exception:
            return None

    def _detail_scroll_down(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_down_line()

    def _detail_scroll_up(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_up_line()

    def _detail_scroll_home(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_to_top()

    def _detail_scroll_end(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_to_end()

    def _detail_scroll_half_down(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_half_down()

    def _detail_scroll_half_up(self) -> None:
        d = self._get_detail()
        if d:
            d.scroll_half_up()

    # ------------------------------------------------------------------
    # List height helper
    # ------------------------------------------------------------------

    def _list_height(self) -> int:
        try:
            lw = self.query_one(SyscallListWidget)
            return max(1, lw.size.height - 2)
        except Exception:
            return 20


# ---------------------------------------------------------------------------
# Module-level run() function (called from cli.py)
# ---------------------------------------------------------------------------

def run(
    model: Model,
    theme: Theme,
    strace_argv: list[str],
    write_fd: int,
    read_fd: int,
) -> int:
    """Construct and run the app; return an exit code."""
    app = StraceUiApp(
        model=model,
        theme=theme,
        strace_argv=strace_argv,
        write_fd=write_fd,
        read_fd=read_fd,
    )
    result = app.run()
    return 0 if result is None else int(result)
