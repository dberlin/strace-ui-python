"""pid_map — faithful Python port of pid_map.ml.

Tracks the set of PIDs seen in a trace and assigns each a compact
integer "short id" used for display alignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PidInfo:
    """Metadata attached to a PID once it is known."""

    cmdline: str
    thread_name: str
    is_thread: bool


@dataclass(frozen=True)
class PidMap:
    """Immutable mapping from PID to short sequential id plus optional metadata.

    All mutating methods return a *new* PidMap; the original is unchanged.
    """

    pid_to_short: dict  # dict[int, int]
    next_id: int
    infos: dict  # dict[int, PidInfo]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls) -> "PidMap":
        return cls(pid_to_short={}, next_id=0, infos={})

    # ------------------------------------------------------------------
    # Mutators (return new instances)
    # ------------------------------------------------------------------

    def register(self, pid: int) -> "PidMap":
        """Return a new PidMap with *pid* recorded, or *self* if already known."""
        if pid in self.pid_to_short:
            return self
        new_map = {**self.pid_to_short, pid: self.next_id}
        return PidMap(pid_to_short=new_map, next_id=self.next_id + 1, infos=self.infos)

    def set_info(self, pid: int, pid_info: PidInfo) -> "PidMap":
        """Return a new PidMap with *pid_info* stored for *pid*."""
        new_infos = {**self.infos, pid: pid_info}
        return PidMap(pid_to_short=self.pid_to_short, next_id=self.next_id, infos=new_infos)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def short_id(self, pid: int) -> Optional[int]:
        """Return the short id for *pid*, or None if not registered."""
        return self.pid_to_short.get(pid)

    def display_width(self) -> int:
        """Number of digits needed to display the largest short id."""
        max_id = self.next_id - 1
        if max_id < 0:
            return 1
        return max(1, len(str(max_id)))

    def info(self, pid: int) -> Optional[PidInfo]:
        """Return the PidInfo for *pid*, or None if not set."""
        return self.infos.get(pid)

    def summary(self, pid: int) -> Optional[str]:
        """Human-readable one-line summary for *pid*, or None if unknown."""
        pid_info = self.infos.get(pid)
        if pid_info is None:
            return None
        if pid_info.is_thread:
            return f"thread: {pid_info.thread_name} ({pid_info.cmdline})"
        return pid_info.cmdline
