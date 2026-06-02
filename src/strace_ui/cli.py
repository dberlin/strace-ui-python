"""cli: command-line interface for strace_ui.

Parses arguments (mirroring the OCaml command flags), sets up the pipe,
launches the Textual app, and handles early strace failure.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from strace_ui.themes import THEMES, get_theme, default_theme_name
from strace_ui.model import default_model


# ---------------------------------------------------------------------------
# build_strace_args
# ---------------------------------------------------------------------------

def build_strace_args(
    *,
    write_fd: int,
    trace_expr: Optional[str],
    attach_pid: Optional[int],
    program: list[str],
) -> list[str]:
    """Build the strace argument list.

    Fixed flags: -ttt -T -f -x -yy -v -s 1024 -o /dev/fd/<write_fd>
    Then optionally: -e <trace_expr>
    Then either: -p <pid>  OR  -- <program...>
    Raises SystemExit if neither attach_pid nor program is provided.
    """
    args = [
        "-ttt", "-T", "-f", "-x", "-yy", "-v",
        "-s", "1024",
        "-o", f"/dev/fd/{write_fd}",
    ]

    if trace_expr is not None:
        args += ["-e", trace_expr]

    if attach_pid is not None:
        args += ["-p", str(attach_pid)]
    elif program:
        args += ["--"] + list(program)
    else:
        raise SystemExit("Must specify either -p PID or a program to trace")

    return args


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    """Parse arguments and run the application."""
    parser = argparse.ArgumentParser(
        prog="strace-ui",
        description="strace-ui — interactive strace viewer",
        add_help=True,
    )

    # -? as help alias (single-dash long option style)
    parser.add_argument(
        "-?",
        action="help",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "program",
        nargs=argparse.REMAINDER,
        metavar="PROGRAM",
        help="Program to trace (and its arguments)",
    )

    parser.add_argument(
        "-e", "--expr",
        dest="trace_expr",
        metavar="EXPR",
        default=None,
        help="Trace expression passed to strace (e.g. trace=%%net)",
    )

    parser.add_argument(
        "-p", "--pid",
        dest="attach_pid",
        type=int,
        metavar="PID",
        default=None,
        help="Attach to an existing process",
    )

    # Theme: accept both -theme and --theme (single-dash long-option style for OCaml compat)
    theme_choices = sorted(THEMES.keys())
    parser.add_argument(
        "-theme", "--theme",
        dest="theme",
        metavar="THEME",
        default=default_theme_name(),
        choices=theme_choices,
        help=f"Color theme ({', '.join(theme_choices)})",
    )

    parser.add_argument(
        "-version", "--version",
        dest="show_version",
        action="store_true",
        help="Print version and exit",
    )

    parser.add_argument(
        "-build-info", "--build-info",
        dest="show_build_info",
        action="store_true",
        help="Print build info and exit",
    )

    ns = parser.parse_args(argv)

    if ns.show_version or ns.show_build_info:
        print("strace-ui 0.1.0 (Python port)")
        return 0

    # Strip leading '--' sentinel that argparse.REMAINDER sometimes inserts
    program_args = ns.program
    if program_args and program_args[0] == "--":
        program_args = program_args[1:]

    # Resolve theme
    try:
        theme = get_theme(ns.theme)
    except KeyError:
        print(f"Unknown theme: {ns.theme!r}", file=sys.stderr)
        return 1

    # Create the pipe
    read_fd, write_fd = os.pipe()
    os.set_inheritable(write_fd, True)

    # Build model
    model = default_model(primary_pid=ns.attach_pid)

    # Build strace args (may raise SystemExit on missing target)
    try:
        strace_argv = build_strace_args(
            write_fd=write_fd,
            trace_expr=ns.trace_expr,
            attach_pid=ns.attach_pid,
            program=program_args,
        )
    except SystemExit as exc:
        # Clean up fds before exiting
        os.close(read_fd)
        os.close(write_fd)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Import here to avoid heavy imports at module load time
    from strace_ui.app import run as run_app

    return run_app(
        model=model,
        theme=theme,
        strace_argv=strace_argv,
        write_fd=write_fd,
        read_fd=read_fd,
    )
