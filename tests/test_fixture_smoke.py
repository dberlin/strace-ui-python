"""Smoke test: feed real captured strace output through the full pure pipeline.

These fixtures were captured with the exact strace flags strace-ui uses
(`strace -ttt -T -f -x -yy -v -s 1024 -o FILE -- CMD`). Feeding every line
through the reducer guards against parser crashes and reducer invariants
breaking on real-world output (including multi-process / fork traces).
"""

from __future__ import annotations

import pathlib

import pytest

from strace_ui.model import AddLine, apply_action, default_model

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES = sorted(FIXTURE_DIR.glob("*.txt"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_real_strace_feeds_without_error(fixture: pathlib.Path):
    """Every line parses and the filtered count never exceeds the total."""
    model = default_model(resolve_pid_info=lambda pid: None)
    line_count = 0
    for raw in fixture.read_text().splitlines():
        if not raw:
            continue
        line_count += 1
        model = apply_action(model, AddLine(raw))

    total = model.syscall_list.total_count()
    filtered = model.syscall_list.filtered_count()
    assert filtered <= total
    # These fixtures are well-formed real output: every non-empty line should parse.
    assert total == line_count, f"{fixture.name}: {total}/{line_count} lines parsed"


def test_fixtures_present():
    """Guard against the fixtures directory going missing."""
    assert FIXTURES, "no strace fixtures found under tests/fixtures/"
