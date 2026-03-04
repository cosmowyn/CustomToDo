from __future__ import annotations

from datetime import date
from PySide6.QtCore import Signal, Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QCheckBox, QLabel,
    QSpinBox, QDateEdit, QPushButton
)


class FilterPanel(QWidget):
    """
    Advanced filter controls (no search text here; search lives in the main bar).
    Emits changed() on any modification.
    """
    changed = Signal()

    def __init__(self, statuses: list[str], parent=None):
        super().__init__(parent)

        self._statuses = statuses

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- Status group (multi-select)
        g_status = QGroupBox("Status")
        v_status = QVBoxLayout(g_status)

        self.chk_all_status = QCheckBox("All")
        self.chk_all_status.setChecked(True)
        self.chk_all_status.stateChanged.connect(self._on_all_status_changed)
        v_status.addWidget(self.chk_all_status)

        self.status_checks = []
        for s in statuses:
            cb = QCheckBox(s)
            cb.setChecked(True)
            cb.stateChanged.connect(self._emit_changed)
            self.status_checks.append(cb)
            v_status.addWidget(cb)

        root.addWidget(g_status)

        # --- Priority group
        g_prio = QGroupBox("Priority range")
        h_prio = QHBoxLayout(g_prio)

        self.prio_min = QSpinBox()
        self.prio_min.setRange(1, 5)
        self.prio_min.setValue(1)
        self.prio_min.valueChanged.connect(self._emit_changed)

        self.prio_max = QSpinBox()
        self.prio_max.setRange(1, 5)
        self.prio_max.setValue(5)
        self.prio_max.valueChanged.connect(self._emit_changed)

        h_prio.addWidget(QLabel("Min"))
        h_prio.addWidget(self.prio_min)
        h_prio.addSpacing(10)
        h_prio.addWidget(QLabel("Max"))
        h_prio.addWidget(self.prio_max)

        root.addWidget(g_prio)

        # --- Due range group
        g_due = QGroupBox("Due date range")
        v_due = QVBoxLayout(g_due)

        self.chk_due_range = QCheckBox("Enable due range")
        self.chk_due_range.setChecked(False)
        self.chk_due_range.stateChanged.connect(self._emit_changed)
        v_due.addWidget(self.chk_due_range)

        row1 = QHBoxLayout()
        self.due_from = QDateEdit()
        self.due_from.setCalendarPopup(True)
        self.due_from.setDisplayFormat("dd-MMM-yyyy")
        self.due_from.setDate(QDate.currentDate())
        self.due_from.dateChanged.connect(self._emit_changed)

        row1.addWidget(QLabel("From"))
        row1.addWidget(self.due_from)
        v_due.addLayout(row1)

        row2 = QHBoxLayout()
        self.due_to = QDateEdit()
        self.due_to.setCalendarPopup(True)
        self.due_to.setDisplayFormat("dd-MMM-yyyy")
        self.due_to.setDate(QDate.currentDate().addDays(30))
        self.due_to.dateChanged.connect(self._emit_changed)

        row2.addWidget(QLabel("To"))
        row2.addWidget(self.due_to)
        v_due.addLayout(row2)

        root.addWidget(g_due)

        # --- Toggles
        g_flags = QGroupBox("Options")
        v_flags = QVBoxLayout(g_flags)

        self.chk_hide_done = QCheckBox("Hide Done")
        self.chk_hide_done.stateChanged.connect(self._emit_changed)

        self.chk_overdue_only = QCheckBox("Overdue only")
        self.chk_overdue_only.stateChanged.connect(self._emit_changed)

        self.chk_show_children = QCheckBox("Show children of matching parents")
        self.chk_show_children.setChecked(True)
        self.chk_show_children.stateChanged.connect(self._emit_changed)

        v_flags.addWidget(self.chk_hide_done)
        v_flags.addWidget(self.chk_overdue_only)
        v_flags.addWidget(self.chk_show_children)

        root.addWidget(g_flags)

        # --- Reset
        self.btn_reset = QPushButton("Reset filters")
        self.btn_reset.clicked.connect(self.reset)
        root.addWidget(self.btn_reset)

        root.addStretch(1)

    def _emit_changed(self, *_):
        self.changed.emit()

    def _on_all_status_changed(self, state: int):
        checked = (state == Qt.CheckState.Checked.value)
        for cb in self.status_checks:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self.changed.emit()

    # ---------- Read current filter state ----------
    def status_allowed(self) -> set[str] | None:
        # If all selected, return None (meaning no restriction)
        vals = {cb.text() for cb in self.status_checks if cb.isChecked()}
        if len(vals) == len(self.status_checks):
            return None
        return vals

    def priority_range(self) -> tuple[int | None, int | None]:
        # Always enabled; treated as restriction only if not full range
        pmin = int(self.prio_min.value())
        pmax = int(self.prio_max.value())
        if pmin == 1 and pmax == 5:
            return None, None
        return pmin, pmax

    def due_range(self) -> tuple[date | None, date | None]:
        if not self.chk_due_range.isChecked():
            return None, None
        d1 = self.due_from.date().toPython()
        d2 = self.due_to.date().toPython()
        return d1, d2

    def hide_done(self) -> bool:
        return self.chk_hide_done.isChecked()

    def overdue_only(self) -> bool:
        return self.chk_overdue_only.isChecked()

    def show_children_of_matches(self) -> bool:
        return self.chk_show_children.isChecked()

    # ---------- Reset ----------
    def reset(self):
        self.chk_all_status.setChecked(True)

        self.prio_min.setValue(1)
        self.prio_max.setValue(5)

        self.chk_due_range.setChecked(False)
        self.due_from.setDate(QDate.currentDate())
        self.due_to.setDate(QDate.currentDate().addDays(30))

        self.chk_hide_done.setChecked(False)
        self.chk_overdue_only.setChecked(False)
        self.chk_show_children.setChecked(True)

        self.changed.emit()