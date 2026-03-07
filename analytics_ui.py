from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class AnalyticsPanel(QWidget):
    refreshRequested = Signal(int, int)  # trend_days, tag_days

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Trend window"))
        self.trend_days = QSpinBox()
        self.trend_days.setRange(3, 90)
        self.trend_days.setValue(14)
        self.trend_days.setSuffix(" days")
        controls.addWidget(self.trend_days)

        controls.addWidget(QLabel("Top tags window"))
        self.tag_days = QSpinBox()
        self.tag_days.setRange(7, 180)
        self.tag_days.setValue(30)
        self.tag_days.setSuffix(" days")
        controls.addWidget(self.tag_days)

        self.refresh_btn = QPushButton("Refresh analytics")
        self.refresh_btn.setToolTip("Refresh dashboard metrics and trend summaries.")
        controls.addWidget(self.refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        metrics_group = QGroupBox("Summary")
        metrics_form = QFormLayout(metrics_group)
        self.lbl_completed_today = QLabel("0")
        self.lbl_completed_week = QLabel("0")
        self.lbl_overdue = QLabel("0")
        self.lbl_no_due = QLabel("0")
        self.lbl_inbox = QLabel("0")
        self.lbl_active_archived = QLabel("0 / 0")
        self.lbl_projects = QLabel("0")
        metrics_form.addRow("Completed today", self.lbl_completed_today)
        metrics_form.addRow("Completed this week", self.lbl_completed_week)
        metrics_form.addRow("Overdue open", self.lbl_overdue)
        metrics_form.addRow("Open with no due date", self.lbl_no_due)
        metrics_form.addRow("Inbox unprocessed", self.lbl_inbox)
        metrics_form.addRow("Active open / Archived", self.lbl_active_archived)
        metrics_form.addRow("Projects stalled/blocked/no-next", self.lbl_projects)
        root.addWidget(metrics_group)

        lists = QHBoxLayout()
        self.trend_list = QListWidget()
        self.trend_list.setToolTip("Completion trend per day.")
        self.trend_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.trend_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tags_list = QListWidget()
        self.tags_list.setToolTip("Most active tags among recent completions.")
        self.tags_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tags_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lists.addWidget(self.trend_list, 1)
        lists.addWidget(self.tags_list, 1)
        root.addLayout(lists, 1)

        self.refresh_btn.clicked.connect(self._emit_refresh)

    def _emit_refresh(self):
        self.refreshRequested.emit(int(self.trend_days.value()), int(self.tag_days.value()))

    def set_analytics_data(self, data: dict):
        payload = data or {}

        self.lbl_completed_today.setText(str(int(payload.get("completed_today") or 0)))
        self.lbl_completed_week.setText(str(int(payload.get("completed_this_week") or 0)))
        self.lbl_overdue.setText(str(int(payload.get("overdue_open") or 0)))
        self.lbl_no_due.setText(str(int(payload.get("open_no_due") or 0)))
        self.lbl_inbox.setText(str(int(payload.get("inbox_unprocessed") or 0)))
        self.lbl_active_archived.setText(
            f"{int(payload.get('active_open') or 0)} / {int(payload.get('archived_count') or 0)}"
        )
        self.lbl_projects.setText(
            f"{int(payload.get('project_stalled') or 0)} / "
            f"{int(payload.get('project_blocked') or 0)} / "
            f"{int(payload.get('project_no_next') or 0)}"
        )

        self.trend_list.clear()
        for row in payload.get("trend") or []:
            day = str(row.get("date") or "")
            count = int(row.get("count") or 0)
            self.trend_list.addItem(QListWidgetItem(f"{day}: {count} completed"))

        self.tags_list.clear()
        for row in payload.get("top_tags") or []:
            tag = str(row.get("tag") or "")
            count = int(row.get("count") or 0)
            self.tags_list.addItem(QListWidgetItem(f"{tag}: {count}"))
