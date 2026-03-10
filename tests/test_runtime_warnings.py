from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QSettings, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

import main as main_module
from db import Database
from delegates import DateEditorWithClear, SmartDelegate
from main import MainWindow, TaskTreeView
from model import TaskTreeModel
from workspace_profiles import WorkspaceProfileManager


def _workspace_manager(tmp_path):
    manager = WorkspaceProfileManager(base_dir=str(tmp_path / "workspace-data"))
    workspace = manager.create_workspace(
        "Runtime Warnings Test",
        db_path=str(tmp_path / "runtime-warnings.sqlite3"),
        inherit_current_state=False,
    )
    manager.set_current_workspace(str(workspace["id"]))
    return manager, str(workspace["id"])


@contextmanager
def _capture_qt_messages():
    messages: list[str] = []

    def _handler(_msg_type, _context, message):
        messages.append(str(message))

    previous = qInstallMessageHandler(_handler)
    try:
        yield messages
    finally:
        qInstallMessageHandler(previous)


def _column_index_for_key(model, key: str) -> int:
    for column in range(model.columnCount()):
        if str(model.column_key(column)) == str(key):
            return column
    raise AssertionError(f"Column '{key}' not found")


def _active_editor_root(view: TaskTreeView, qapp) -> QWidget | None:
    qapp.processEvents()
    for widget in view.viewport().findChildren(QWidget):
        if bool(widget.property("_delegate_editor_root")):
            return widget
    return None


def test_main_window_skips_tray_when_no_icon_is_available(tmp_path, qapp, monkeypatch):
    QSettings().setValue("ui/onboarding_completed", True)

    class FakeTrayIcon:
        created = False

        @staticmethod
        def isSystemTrayAvailable():
            return True

        def __init__(self, *_args, **_kwargs):
            FakeTrayIcon.created = True

    monkeypatch.setattr(main_module, "QSystemTrayIcon", FakeTrayIcon)
    monkeypatch.setattr(MainWindow, "_install_optional_global_capture_hotkey", lambda self: None)
    monkeypatch.setattr(MainWindow, "_resolved_tray_icon", lambda self: None)

    manager, workspace_id = _workspace_manager(tmp_path)
    window = MainWindow(manager, workspace_id)
    try:
        assert FakeTrayIcon.created is False
        assert window._tray_icon is None
    finally:
        window.close()
        qapp.processEvents()


def test_main_window_resolved_tray_icon_uses_qstyle_fallback(tmp_path, qapp, monkeypatch):
    QSettings().setValue("ui/onboarding_completed", True)
    monkeypatch.setattr(main_module.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    monkeypatch.setattr(MainWindow, "_install_optional_global_capture_hotkey", lambda self: None)

    manager, workspace_id = _workspace_manager(tmp_path)
    window = MainWindow(manager, workspace_id)
    try:
        window.setWindowIcon(QIcon())
        window.model.current_window_icon = lambda: QIcon()
        icon = window._resolved_tray_icon()
        assert icon is not None
        assert icon.isNull() is False
    finally:
        window.close()
        qapp.processEvents()


def test_delegate_selection_change_commits_without_ownership_warning(tmp_path, qapp):
    QSettings().setValue("ui/onboarding_completed", True)
    manager, workspace_id = _workspace_manager(tmp_path)
    window = MainWindow(manager, workspace_id)
    try:
        window.show()
        qapp.processEvents()
        assert window.model.add_task_with_values(
            description="Alpha",
            due_date="2026-03-11",
        )
        first_id = window.model.last_added_task_id()
        assert first_id is not None
        assert window.model.add_task_with_values(
            description="Beta",
            due_date="2026-03-12",
        )
        second_id = window.model.last_added_task_id()
        assert second_id is not None
        qapp.processEvents()

        due_col = _column_index_for_key(window.model, "due_date")
        first_idx = window._proxy_index_for_task_id(int(first_id)).siblingAtColumn(due_col)
        second_idx = window._proxy_index_for_task_id(int(second_id)).siblingAtColumn(due_col)
        assert first_idx.isValid()
        assert second_idx.isValid()

        window.view.setCurrentIndex(first_idx)
        window.view.edit(first_idx)
        qapp.processEvents()

        editor = _active_editor_root(window.view, qapp)
        assert isinstance(editor, DateEditorWithClear)
        editor.date_edit.setDate(editor.date_edit.date().addDays(2))
        qapp.processEvents()

        with _capture_qt_messages() as messages:
            window.view.setCurrentIndex(second_idx)
            qapp.processEvents()

        relevant = [
            msg for msg in messages
            if "commitData called with an editor that does not belong to this view" in msg
            or "closeEditor called with an editor that does not belong to this view" in msg
            or "edit: editing failed" in msg
        ]
        assert relevant == []
        assert window.db.fetch_task_by_id(int(first_id))["due_date"] == "2026-03-13"
    finally:
        window.close()
        qapp.processEvents()


def test_delegate_model_reset_during_edit_has_no_ownership_warning(tmp_path, qapp):
    db = Database(str(tmp_path / "delegate-owner.sqlite3"))
    db.insert_task({"description": "Alpha", "sort_order": 1})
    view = TaskTreeView()
    model = TaskTreeModel(db)
    view.setModel(model)

    delegate = SmartDelegate(view)
    view.setItemDelegate(delegate)
    view.show()
    qapp.processEvents()

    due_col = _column_index_for_key(model, "due_date")
    index = model.index(0, due_col)
    assert index.isValid()
    model.setData(index, "2026-03-11")
    qapp.processEvents()

    view.edit(index)
    qapp.processEvents()
    editor = _active_editor_root(view, qapp)
    assert isinstance(editor, DateEditorWithClear)
    editor.date_edit.setDate(editor.date_edit.date().addDays(1))
    qapp.processEvents()

    with _capture_qt_messages() as messages:
        model.reload_all(reset_header_state=False)
        qapp.processEvents()

    relevant = [
        msg for msg in messages
        if "commitData called with an editor that does not belong to this view" in msg
        or "closeEditor called with an editor that does not belong to this view" in msg
        or "edit: editing failed" in msg
    ]
    assert relevant == []
