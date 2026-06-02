"""widgets: Textual widgets for the strace_ui application.

SyscallListWidget — renders the scrollable syscall list using Rich renderables.
DetailWidget     — scrollable detail pane showing render_detail output.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text
from rich.style import Style

from textual.widget import Widget
from textual.widgets import Static
from textual.containers import VerticalScroll
from textual.app import RenderResult

from strace_ui.render import render_syscall_row_text, render_detail, render_filter_label
from strace_ui.model import Model, Focus
from strace_ui.themes import Theme

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# SyscallListWidget
# ---------------------------------------------------------------------------

class SyscallListWidget(Widget):
    """Renders the scrollable syscall list.

    Does NOT own a scrollbar — it renders exactly `height` rows via a
    computed scroll_offset so the selection stays centred.
    """

    DEFAULT_CSS = """
    SyscallListWidget {
        border: round $primary;
        border-title-align: left;
    }
    """

    def __init__(self, app_ref: "StraceUiApp", **kwargs):
        super().__init__(**kwargs)
        self._app_ref = app_ref

    def render(self) -> RenderResult:
        model: Model = self._app_ref.model
        theme: Theme = self._app_ref.ui_theme
        width = self.size.width
        # Account for border (2 cols) - inner width
        inner_width = max(1, width - 2)
        height = self.size.height
        # Account for border (2 rows)
        inner_height = max(1, height - 2)

        fc = model.filtered_count()

        # Update border title with focus hint
        focus_hint = "" if model.focus == Focus.SYSCALL_LIST else " <tab>"
        filter_label = render_filter_label(
            model.filter_editor,
            current_filter=model.syscall_filter,
            theme=theme,
            max_chars=max(10, inner_width - 20),
        )
        # Position indicator
        if fc > 0:
            pos_str = f"{model.selected_index() + 1}/{fc}"
        else:
            pos_str = "0/0"

        self.border_title = f"Syscalls{focus_hint}"
        self.border_subtitle = f"{pos_str}"

        if fc == 0:
            msg = Text("Waiting for syscalls...", style=Style(color=theme.dim))
            return msg

        sel_idx = model.selected_index()
        # Centre the selection in the visible window
        scroll_offset = max(0, min(sel_idx - inner_height // 2, max(0, fc - inner_height)))

        selected_line = model.get_selected()
        selected_pid = selected_line.pid if selected_line is not None else -1

        rows: list[Text] = []
        for i in range(scroll_offset, min(fc, scroll_offset + inner_height)):
            line = model.get_filtered(i)
            if line is None:
                rows.append(Text(" " * inner_width))
                continue
            sid = model.pid_map.short_id(line.pid)
            short_id = sid if sid is not None else 0
            pid_width = model.pid_map.display_width()
            row_text = render_syscall_row_text(
                line,
                theme=theme,
                width=inner_width,
                short_id=short_id,
                pid_width=pid_width,
                selected_pid=selected_pid,
                is_selected=(i == sel_idx),
            )
            rows.append(row_text)

        # Pad to fill the pane height
        while len(rows) < inner_height:
            rows.append(Text(" " * inner_width))

        return Group(*rows)


# ---------------------------------------------------------------------------
# DetailWidget
# ---------------------------------------------------------------------------

class DetailWidget(VerticalScroll):
    """Scrollable detail pane.

    Contains a single Static whose content is updated via update_detail().
    """

    DEFAULT_CSS = """
    DetailWidget {
        border: round $primary;
        border-title-align: left;
    }
    DetailWidget Static {
        width: 100%;
    }
    """

    def __init__(self, app_ref: "StraceUiApp", **kwargs):
        super().__init__(**kwargs)
        self._app_ref = app_ref
        self._static = Static("", markup=False)

    def compose(self):
        yield self._static

    def update_detail(self) -> None:
        """Refresh the detail content from the current model state."""
        app = self._app_ref
        model: Model = app.model
        theme: Theme = app.ui_theme

        # Inner width: subtract borders (2) and scrollbar (1)
        width = max(20, self.size.width - 3)

        # Focus hint
        focus_hint = "" if model.focus == Focus.DETAIL_PANE else " <tab>"
        render_hint = f"x:{model.render_mode.to_short_string()} m:man"
        self.border_title = f"Details{focus_hint}"
        self.border_subtitle = render_hint

        selected_line = model.get_selected()
        if selected_line is None:
            self._static.update(
                Text("No syscall selected", style=Style(color=theme.dim))
            )
            return

        man_page_content = model.man_page_cache.get(selected_line.syscall_name)

        content = render_detail(
            selected_line,
            theme=theme,
            fd_tracker=model.fd_tracker,
            dns_cache=model.dns_cache,
            render_mode=model.render_mode,
            show_man_page=model.show_man_page,
            man_page_content=man_page_content,
            width=width,
            pid_map=model.pid_map,
        )
        self._static.update(content)

    def scroll_down_line(self) -> None:
        self.scroll_down(animate=False)

    def scroll_up_line(self) -> None:
        self.scroll_up(animate=False)

    def scroll_to_top(self) -> None:
        self.scroll_home(animate=False)

    def scroll_to_end(self) -> None:
        self.scroll_end(animate=False)

    def scroll_half_down(self) -> None:
        half = max(1, (self.size.height - 2) // 2)
        self.scroll_relative(y=half, animate=False)

    def scroll_half_up(self) -> None:
        half = max(1, (self.size.height - 2) // 2)
        self.scroll_relative(y=-half, animate=False)
