from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Set

from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex


def _parse_iso_date(s: str | None) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


class TaskFilterProxyModel(QSortFilterProxyModel):
    """
    Recursive tree filtering for TaskTreeModel.
    Keeps parents when children match (recursive filtering enabled).
    Optionally keeps children of matching parents (show_children_of_matches).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(True)

        self._search_text = ""
        self._status_allowed: Optional[Set[str]] = None  # None = all
        self._priority_min: Optional[int] = None
        self._priority_max: Optional[int] = None
        self._due_from: Optional[date] = None
        self._due_to: Optional[date] = None
        self._hide_done = False
        self._overdue_only = False
        self._show_children_of_matches = True

    # ---------- Public setters ----------
    def set_search_text(self, text: str):
        t = (text or "").strip().lower()
        if t != self._search_text:
            self._search_text = t
            self.invalidateFilter()

    def set_status_allowed(self, statuses: Optional[Set[str]]):
        # None = all
        if statuses is not None and len(statuses) == 0:
            statuses = None
        if statuses != self._status_allowed:
            self._status_allowed = statuses
            self.invalidateFilter()

    def set_priority_range(self, pmin: Optional[int], pmax: Optional[int]):
        if pmin is not None:
            pmin = int(pmin)
        if pmax is not None:
            pmax = int(pmax)
        if (pmin, pmax) != (self._priority_min, self._priority_max):
            self._priority_min, self._priority_max = pmin, pmax
            self.invalidateFilter()

    def set_due_range(self, dfrom: Optional[date], dto: Optional[date]):
        if (dfrom, dto) != (self._due_from, self._due_to):
            self._due_from, self._due_to = dfrom, dto
            self.invalidateFilter()

    def set_hide_done(self, hide: bool):
        hide = bool(hide)
        if hide != self._hide_done:
            self._hide_done = hide
            self.invalidateFilter()

    def set_overdue_only(self, overdue: bool):
        overdue = bool(overdue)
        if overdue != self._overdue_only:
            self._overdue_only = overdue
            self.invalidateFilter()

    def set_show_children_of_matches(self, enabled: bool):
        enabled = bool(enabled)
        if enabled != self._show_children_of_matches:
            self._show_children_of_matches = enabled
            self.invalidateFilter()

    # ---------- Status ----------
    def is_filter_active(self) -> bool:
        if self._search_text:
            return True
        if self._status_allowed is not None:
            return True
        if self._priority_min is not None or self._priority_max is not None:
            return True
        if self._due_from is not None or self._due_to is not None:
            return True
        if self._hide_done:
            return True
        if self._overdue_only:
            return True
        # show_children_of_matches doesn't activate a filter by itself
        return False

    # ---------- Filtering ----------
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        sm = self.sourceModel()
        if sm is None:
            return True

        idx0 = sm.index(source_row, 0, source_parent)
        if not idx0.isValid():
            return True

        node = idx0.internalPointer()
        task = getattr(node, "task", None)
        if not isinstance(task, dict):
            return True

        # Hard filters (always apply even when showing children of matches)
        if not self._passes_hard_filters(task):
            return False

        # If no search text, only hard filters matter
        if not self._search_text:
            return True

        # Search match for this node?
        if self._matches_search(task):
            return True

        # Optionally show children of matching parents (search only)
        if self._show_children_of_matches and self._ancestor_matches_search(source_parent):
            return True

        return False

    def _passes_hard_filters(self, task: dict) -> bool:
        status = str(task.get("status") or "")
        if self._hide_done and status == "Done":
            return False

        if self._status_allowed is not None and status not in self._status_allowed:
            return False

        try:
            prio = int(task.get("priority") or 0)
        except Exception:
            prio = 0

        if self._priority_min is not None and prio < self._priority_min:
            return False
        if self._priority_max is not None and prio > self._priority_max:
            return False

        due = _parse_iso_date(task.get("due_date"))
        today = date.today()

        if self._overdue_only:
            # overdue requires due date and not done
            if due is None:
                return False
            if due >= today:
                return False

        if self._due_from is not None:
            if due is None or due < self._due_from:
                return False

        if self._due_to is not None:
            if due is None or due > self._due_to:
                return False

        return True

    def _matches_search(self, task: dict) -> bool:
        q = self._search_text
        if not q:
            return True

        parts = []

        # Core fields
        parts.append(str(task.get("description") or ""))
        parts.append(str(task.get("status") or ""))
        parts.append(str(task.get("due_date") or ""))
        parts.append(str(task.get("priority") or ""))
        parts.append(str(task.get("last_update") or ""))

        # Custom values
        custom = task.get("custom") or {}
        if isinstance(custom, dict):
            for v in custom.values():
                if v is not None:
                    parts.append(str(v))

        hay = " ".join(parts).lower()
        return q in hay

    def _ancestor_matches_search(self, source_parent: QModelIndex) -> bool:
        # Walk upwards: if any ancestor matches search, keep this row
        sm = self.sourceModel()
        p = source_parent
        while p.isValid():
            node = p.internalPointer()
            task = getattr(node, "task", None)
            if isinstance(task, dict):
                if self._matches_search(task):
                    return True
            p = p.parent()
        return False