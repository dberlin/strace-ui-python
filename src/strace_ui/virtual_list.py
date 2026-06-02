"""Virtual list with a filtered view and a selected index.

Port of OCaml virtual_list.ml (State module). Like the original (a mutable
``Vec`` inside a ``Box``), ``all_items`` and ``filtered_indices`` are a shared
backing store: ``append`` and ``set_item`` mutate them in place in O(1) and
return a new wrapper. The model is forward-only (we never revert to an earlier
version), so sharing is safe and avoids the O(n^2) blow-up that copying the
lists on every appended syscall caused under high-volume traces. ``refilter``
(triggered only by a user filter change) rebuilds ``filtered_indices`` fresh.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class VirtualList(Generic[T]):
    """State of a virtual list with a filtered view and a selected index.

    Fields
    ------
    all_items       : every item ever appended (in insertion order).
    filtered_indices: indices into all_items that pass the current filter.
    selected_index  : position in the *filtered* view that is currently selected.
    """

    all_items: List[T]
    filtered_indices: List[int]
    selected_index: int

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def create(cls) -> "VirtualList[T]":
        """Return an empty VirtualList."""
        return cls(all_items=[], filtered_indices=[], selected_index=0)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def total_count(self) -> int:
        return len(self.all_items)

    def filtered_count(self) -> int:
        return len(self.filtered_indices)

    def get_filtered(self, i: int) -> Optional[T]:
        """Return the item at filtered position *i*, or None if out of range."""
        if 0 <= i < self.filtered_count():
            return self.all_items[self.filtered_indices[i]]
        return None

    def get_raw(self, i: int) -> T:
        """Return the item at raw (all_items) position *i*."""
        return self.all_items[i]

    def get_selected(self) -> Optional[T]:
        """Return the currently selected item, or None if the list is empty."""
        return self.get_filtered(self.selected_index)

    def selected_raw_index(self) -> Optional[int]:
        """Return the raw index of the selected item, or None if out of range."""
        if 0 <= self.selected_index < len(self.filtered_indices):
            return self.filtered_indices[self.selected_index]
        return None

    # ------------------------------------------------------------------
    # Mutations (return new instances; copy lists where needed)
    # ------------------------------------------------------------------

    def append(self, item: T, *, passes_filter: bool) -> "VirtualList[T]":
        """Append *item* in O(1) (shared backing). If it passes the filter, record its index."""
        self.all_items.append(item)
        if passes_filter:
            self.filtered_indices.append(len(self.all_items) - 1)
        fc = len(self.filtered_indices)
        new_sel = min(self.selected_index, max(0, fc - 1))
        return VirtualList(
            all_items=self.all_items,
            filtered_indices=self.filtered_indices,
            selected_index=new_sel,
        )

    def set_item(self, idx: int, item: T) -> "VirtualList[T]":
        """Replace the item at raw index *idx* in O(1) (shared backing)."""
        self.all_items[idx] = item
        return VirtualList(
            all_items=self.all_items,
            filtered_indices=self.filtered_indices,
            selected_index=self.selected_index,
        )

    def refilter(self, passes: Callable[[T], bool]) -> "VirtualList[T]":
        """Rebuild filtered_indices using *passes*.

        Preserves the selection as closely as possible: finds the highest
        filtered position whose raw index is <= the previously selected raw
        index (i.e. the line at or just before the old selection that now
        passes the filter).
        """
        prev_raw = self.selected_raw_index()
        new_filtered = [i for i, item in enumerate(self.all_items) if passes(item)]
        length = len(new_filtered)
        if prev_raw is None:
            new_sel = 0
        else:
            best = 0
            for i, raw_idx in enumerate(new_filtered):
                if raw_idx <= prev_raw:
                    best = i
            new_sel = min(best, max(0, length - 1))
        return VirtualList(
            all_items=self.all_items,
            filtered_indices=new_filtered,
            selected_index=new_sel,
        )

    # ------------------------------------------------------------------
    # Selection actions (share list objects; only selected_index changes)
    # ------------------------------------------------------------------

    def _with_sel(self, new_sel: int) -> "VirtualList[T]":
        return VirtualList(
            all_items=self.all_items,
            filtered_indices=self.filtered_indices,
            selected_index=new_sel,
        )

    def select_up(self) -> "VirtualList[T]":
        return self._with_sel(max(0, self.selected_index - 1))

    def select_down(self) -> "VirtualList[T]":
        return self._with_sel(min(self.filtered_count() - 1, self.selected_index + 1))

    def select_top(self) -> "VirtualList[T]":
        return self._with_sel(0)

    def select_bottom(self) -> "VirtualList[T]":
        return self._with_sel(max(0, self.filtered_count() - 1))

    def jump_to_filtered_index(self, idx: int) -> "VirtualList[T]":
        return self._with_sel(max(0, min(self.filtered_count() - 1, idx)))
