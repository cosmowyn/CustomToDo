from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPointF, QSettings
from PySide6.QtWidgets import QListWidget

from gantt_ui import ROW_HEIGHT
import main as main_module
from main import MainWindow
from workspace_profiles import WorkspaceProfileManager


def _build_window(tmp_path, qapp, monkeypatch):
    QSettings().setValue("ui/onboarding_completed", True)
    monkeypatch.setattr(
        main_module.QSystemTrayIcon,
        "isSystemTrayAvailable",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        MainWindow,
        "_install_optional_global_capture_hotkey",
        lambda self: None,
    )
    manager = WorkspaceProfileManager(base_dir=str(tmp_path / "workspace-data"))
    workspace = manager.create_workspace(
        "Selection Sync Test",
        db_path=str(tmp_path / "selection-sync.sqlite3"),
        inherit_current_state=False,
    )
    manager.set_current_workspace(str(workspace["id"]))
    window = MainWindow(manager, str(workspace["id"]))
    window.show()
    qapp.processEvents()
    return window


def test_active_task_selection_stays_synchronized_across_views(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        parent_id = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A1", parent_id=parent_id)
        child_one = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A2", parent_id=parent_id)
        child_two = int(window.model.last_added_task_id())

        window.relationships_dock.show()
        window.focus_dock.show()
        qapp.processEvents()

        window._focus_task_by_id(child_one)
        qapp.processEvents()
        assert window.relationships_panel.active_task_label.text() == "Child A1"
        assert "Status:" in window.relationships_panel.meta_label.text()
        assert window.relationships_panel.active_task_label.font().bold()
        assert "Child A1" in window.focus_panel.current_task.text()
        assert "Child A1" in window._active_task_label.text()
        assert window.details_panel.task_id() == child_one

        window._focus_task_by_id(child_two)
        qapp.processEvents()
        assert window.relationships_panel.active_task_label.text() == "Child A2"
        assert "Child A2" in window.focus_panel.current_task.text()
        assert "Child A2" in window._active_task_label.text()
        assert window.details_panel.task_id() == child_two
    finally:
        window.close()
        qapp.processEvents()


def test_relationship_inspector_navigation_updates_main_selection(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        parent_id = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A1", parent_id=parent_id)
        child_one = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A2", parent_id=parent_id)
        child_two = int(window.model.last_added_task_id())

        window.relationships_dock.show()
        window._focus_task_by_id(child_two)
        qapp.processEvents()

        window.relationships_panel.tabs.setCurrentIndex(1)
        qapp.processEvents()

        sibling_list = window.relationships_panel.findChild(
            QListWidget,
            "RelationshipsList_siblings",
        )
        assert sibling_list is not None
        assert sibling_list.count() >= 1
        sibling_list.setCurrentRow(0)
        sibling_list.setFocus()
        window.relationships_panel.focus_btn.click()
        qapp.processEvents()

        assert window._selected_task_id() == child_one
        assert window.details_panel.task_id() == child_one
        assert window.relationships_panel.active_task_label.text() == "Child A1"
    finally:
        window.close()
        qapp.processEvents()


def test_project_timeline_selection_stays_synchronized_with_main_selection(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        parent_id = int(window.model.last_added_task_id())
        window.model.set_task_start_date(parent_id, "2026-03-10")
        window.model.set_task_due_date(parent_id, "2026-03-20")

        assert window.model.add_task_with_values("Child A1", parent_id=parent_id)
        child_one = int(window.model.last_added_task_id())
        window.model.set_task_start_date(child_one, "2026-03-11")
        window.model.set_task_due_date(child_one, "2026-03-14")

        assert window.model.add_task_with_values("Child A2", parent_id=parent_id)
        child_two = int(window.model.last_added_task_id())
        window.model.set_task_start_date(child_two, "2026-03-15")
        window.model.set_task_due_date(child_two, "2026-03-18")

        window.project_dock.show()
        window._focus_task_by_id(child_one)
        qapp.processEvents()

        assert window.project_panel.timeline_widget.selected_uid == f"task:{child_one}"

        window.project_panel.timeline_widget.emit_chart_selection(f"task:{child_two}")
        qapp.processEvents()

        assert window._selected_task_id() == child_two
        assert window.details_panel.task_id() == child_two
        assert window.project_panel.timeline_widget.selected_uid == f"task:{child_two}"
    finally:
        window.close()
        qapp.processEvents()


def test_project_panel_reuses_dashboard_for_same_project_selection(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A1", parent_id=project_id)
        child_one = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A2", parent_id=project_id)
        child_two = int(window.model.last_added_task_id())

        fetch_calls = 0
        original_fetch = window.model.fetch_project_dashboard

        def counted_fetch(task_id: int):
            nonlocal fetch_calls
            fetch_calls += 1
            return original_fetch(task_id)

        monkeypatch.setattr(window.model, "fetch_project_dashboard", counted_fetch)

        window.project_dock.show()
        qapp.processEvents()

        window._focus_task_by_id(child_one)
        qapp.processEvents()
        first_fetch_count = fetch_calls
        assert first_fetch_count >= 1
        assert window.project_panel._current_project_id == project_id

        window._focus_task_by_id(child_two)
        qapp.processEvents()
        assert fetch_calls == first_fetch_count
        assert window.project_panel.timeline_widget.selected_uid == f"task:{child_two}"
        assert window._selected_task_id() == child_two
    finally:
        window.close()
        qapp.processEvents()


def test_project_timeline_can_create_task_directly_in_main_window(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        window.model.set_task_start_date(project_id, "2026-03-10")
        window.model.set_task_due_date(project_id, "2026-03-20")

        window.project_dock.show()
        window._focus_task_by_id(project_id)
        window.project_panel.tabs.setCurrentWidget(window.project_panel.timeline_tab_page)
        qapp.processEvents()

        window.project_panel.timeline_widget.create_task_at(
            None,
            date(2026, 3, 16),
        )
        qapp.processEvents()

        new_id = window.model.last_added_task_id()
        assert new_id is not None
        details = window.model.task_details(int(new_id))
        assert details is not None
        assert details["description"] == "New task"
        assert details["start_date"] == "2026-03-16"
        assert details["due_date"] == "2026-03-16"
        assert details["parent_id"] == project_id
        assert window._selected_task_id() == int(new_id)
        assert window.project_panel.timeline_widget.selected_uid == f"task:{int(new_id)}"
    finally:
        window.close()
        qapp.processEvents()


def test_project_timeline_can_archive_created_task_from_cockpit(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        window.model.set_task_start_date(project_id, "2026-03-10")
        window.model.set_task_due_date(project_id, "2026-03-20")

        window.project_dock.show()
        window._focus_task_by_id(project_id)
        qapp.processEvents()

        window.project_panel.timeline_widget.create_task_at(
            None,
            date(2026, 3, 16),
        )
        qapp.processEvents()

        new_id = int(window.model.last_added_task_id())
        window.project_panel.timeline_widget.select_item("task", new_id)
        window.project_panel.timeline_widget.emit_chart_selection(f"task:{new_id}")
        qapp.processEvents()

        window.project_panel.archive_timeline_task_btn.click()
        qapp.processEvents()

        archived_task = window.db.fetch_task_by_id(new_id)
        assert archived_task is not None
        assert str(archived_task.get("archived_at") or "").strip()
        assert all(
            int(row.get("item_id") or 0) != new_id
            for row in window.project_panel.timeline_widget.rows
            if str(row.get("kind") or "") == "task"
        )

        window.model.undo_stack.undo()
        qapp.processEvents()
        restored_task = window.db.fetch_task_by_id(new_id)
        assert restored_task is not None
        assert not str(restored_task.get("archived_at") or "").strip()

        window.model.undo_stack.redo()
        qapp.processEvents()
        rearchived_task = window.db.fetch_task_by_id(new_id)
        assert rearchived_task is not None
        assert str(rearchived_task.get("archived_at") or "").strip()
    finally:
        window.close()
        qapp.processEvents()


def test_archiving_project_root_from_cockpit_removes_project_context(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        window.model.set_task_start_date(project_id, "2026-03-10")
        window.model.set_task_due_date(project_id, "2026-03-20")
        assert window.model.add_task_with_values("Child A1", parent_id=project_id)

        window.project_dock.show()
        window._focus_task_by_id(project_id)
        qapp.processEvents()

        window.project_panel.archive_project_btn.click()
        qapp.processEvents()

        assert int(project_id) not in {
            int(row.get("id") or 0) for row in window.model.list_project_candidates()
        }
        assert window.model.fetch_project_dashboard(project_id) is None
        assert window.project_panel.project_combo.findData(project_id) == -1
    finally:
        window.close()
        qapp.processEvents()


def test_project_timeline_vertical_reorder_updates_task_tree_and_undo(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        window.model.set_task_start_date(project_id, "2026-03-10")
        window.model.set_task_due_date(project_id, "2026-03-20")

        assert window.model.add_task_with_values("Child A1", parent_id=project_id)
        child_one = int(window.model.last_added_task_id())
        window.model.set_task_start_date(child_one, "2026-03-11")
        window.model.set_task_due_date(child_one, "2026-03-12")

        assert window.model.add_task_with_values("Child A2", parent_id=project_id)
        child_two = int(window.model.last_added_task_id())
        window.model.set_task_start_date(child_two, "2026-03-13")
        window.model.set_task_due_date(child_two, "2026-03-14")

        assert window.model.add_task_with_values("Child A3", parent_id=project_id)
        child_three = int(window.model.last_added_task_id())
        window.model.set_task_start_date(child_three, "2026-03-15")
        window.model.set_task_due_date(child_three, "2026-03-16")

        window.project_dock.show()
        window._focus_task_by_id(project_id)
        window.project_panel.tabs.setCurrentWidget(window.project_panel.timeline_tab_page)
        qapp.processEvents()

        row_index = window.project_panel.timeline_widget.row_index_for_uid(
            f"task:{child_one}"
        )
        assert row_index >= 0

        window.project_panel.timeline_widget.finalize_row_reorder(
            f"task:{child_three}",
            QPointF(0.0, float(row_index * ROW_HEIGHT) + 1.0),
        )
        qapp.processEvents()

        assert window.model.sibling_order(project_id) == [
            child_three,
            child_one,
            child_two,
        ]
        assert window._selected_task_id() == child_three
        assert window.project_panel.timeline_widget.selected_uid == f"task:{child_three}"

        window.model.undo_stack.undo()
        qapp.processEvents()
        assert window.model.sibling_order(project_id) == [
            child_one,
            child_two,
            child_three,
        ]

        window.model.undo_stack.redo()
        qapp.processEvents()
        assert window.model.sibling_order(project_id) == [
            child_three,
            child_one,
            child_two,
        ]
    finally:
        window.close()
        qapp.processEvents()


def test_details_auto_save_on_selection_change_preserves_new_focus(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        parent_id = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A1", parent_id=parent_id)
        child_one = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A2", parent_id=parent_id)
        child_two = int(window.model.last_added_task_id())

        window._focus_task_by_id(child_one)
        qapp.processEvents()

        window.details_panel.tags.setFocus()
        window.details_panel.tags.setText("alpha, beta")
        qapp.processEvents()

        window._focus_task_by_id(child_two)
        qapp.processEvents()

        saved_details = window.model.task_details(child_one)
        assert saved_details is not None
        assert saved_details["tags"] == ["alpha", "beta"]
        assert window._selected_task_id() == child_two
        assert window.details_panel.task_id() == child_two
    finally:
        window.close()
        qapp.processEvents()


def test_project_profile_auto_save_keeps_active_task_selected(
    tmp_path,
    qapp,
    monkeypatch,
):
    window = _build_window(tmp_path, qapp, monkeypatch)
    try:
        assert window.model.add_task_with_values("Project A")
        project_id = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Child A1", parent_id=project_id)
        child_id = int(window.model.last_added_task_id())

        window.project_dock.show()
        window._focus_task_by_id(child_id)
        qapp.processEvents()

        window.project_panel.objective_edit.setFocus()
        window.project_panel.objective_edit.setPlainText("Ship a fictional launch")
        window.view.setFocus()
        qapp.processEvents()

        dashboard = window.model.fetch_project_dashboard(project_id)
        profile = dashboard.get("profile") or {}
        assert profile.get("objective") == "Ship a fictional launch"
        assert window._selected_task_id() == child_id
        assert window.details_panel.task_id() == child_id
    finally:
        window.close()
        qapp.processEvents()
