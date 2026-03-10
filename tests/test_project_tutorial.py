from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSettings

import main as main_module
from main import MainWindow
from workspace_profiles import WorkspaceProfileManager


def _build_window(tmp_path, qapp, monkeypatch, manager=None, workspace_id=None):
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
    manager = manager or WorkspaceProfileManager(base_dir=str(tmp_path / "workspace-data"))
    if workspace_id is None:
        workspace = manager.create_workspace(
            "Project Tutorial Test",
            db_path=str(tmp_path / "project-tutorial.sqlite3"),
            inherit_current_state=False,
        )
        workspace_id = str(workspace["id"])
    manager.set_current_workspace(str(workspace_id))
    window = MainWindow(manager, str(workspace_id))
    window.show()
    qapp.processEvents()
    return window, manager, str(workspace_id)


def test_project_tutorial_guides_real_project_setup(
    tmp_path,
    qapp,
    monkeypatch,
):
    window, _manager, _workspace_id = _build_window(tmp_path, qapp, monkeypatch)
    try:
        window._open_project_tutorial()
        qapp.processEvents()

        assert window.project_tutorial_dock.isVisible()
        assert window._project_tutorial_session.active
        assert window.project_tutorial_panel.step_title.text() == "Introduction"

        window._project_tutorial_next()
        window._update_project_tutorial_idea("Launch onboarding portal")
        qapp.processEvents()
        assert window.project_tutorial_panel.status_label.text().startswith("Status: ready")

        window._project_tutorial_next()
        assert window.model.add_task_with_values("Launch onboarding portal")
        project_id = int(window.model.last_added_task_id())
        window._focus_task_by_id(project_id)
        qapp.processEvents()
        window._bind_project_tutorial_to_selection()
        qapp.processEvents()
        assert window._project_tutorial_session.project_task_id == project_id

        window._project_tutorial_next()
        phase_id = int(window.model.add_project_phase(project_id, "Build"))
        qapp.processEvents()
        assert "ready" in window.project_tutorial_panel.status_label.text()

        window._project_tutorial_next()
        assert window.model.add_task_with_values("Design workflow", parent_id=project_id)
        task_one = int(window.model.last_added_task_id())
        assert window.model.add_task_with_values("Ship launch plan", parent_id=project_id)
        task_two = int(window.model.last_added_task_id())
        window.model.set_task_phase(task_one, phase_id)
        window.model.set_task_phase(task_two, phase_id)
        qapp.processEvents()

        window._project_tutorial_next()
        milestone_id = int(
            window.model.upsert_milestone(
                {
                    "project_task_id": project_id,
                    "title": "Stakeholder sign-off",
                    "phase_id": phase_id,
                    "target_date": date(2026, 3, 25).isoformat(),
                    "status": "planned",
                }
            )
        )
        qapp.processEvents()
        assert milestone_id > 0

        window._project_tutorial_next()
        window.model.set_task_dependencies(task_two, [task_one])
        window.model.set_task_waiting_for(task_two, "Waiting for design approval")
        qapp.processEvents()

        window._project_tutorial_next()
        window.model.set_task_start_date(task_one, "2026-03-20")
        window.model.set_task_due_date(task_one, "2026-03-22")
        window.model.set_task_start_date(task_two, "2026-03-23")
        window.model.set_task_due_date(task_two, "2026-03-26")
        qapp.processEvents()

        window._project_tutorial_next()
        qapp.processEvents()
        status_text = window.project_tutorial_panel.status_label.text().lower()
        assert "ready" in status_text
        assert "real structure" in status_text

        window._project_tutorial_next()
        qapp.processEvents()
        assert window._project_tutorial_session.completed
        assert window.project_tutorial_panel.bound_project_label.text().endswith(
            "Launch onboarding portal"
        )
    finally:
        window.close()
        qapp.processEvents()


def test_project_tutorial_session_resumes_after_reopen(
    tmp_path,
    qapp,
    monkeypatch,
):
    window, manager, workspace_id = _build_window(tmp_path, qapp, monkeypatch)
    try:
        window._open_project_tutorial()
        window._project_tutorial_next()
        window._update_project_tutorial_idea("Prepare annual conference")
        assert window.model.add_task_with_values("Prepare annual conference")
        project_id = int(window.model.last_added_task_id())
        window._focus_task_by_id(project_id)
        qapp.processEvents()
        window._bind_project_tutorial_to_selection()
        window._project_tutorial_next()
        qapp.processEvents()
        assert window._project_tutorial_session.step_index == 2
    finally:
        window.close()
        qapp.processEvents()

    reopened, _manager, _workspace_id = _build_window(
        tmp_path,
        qapp,
        monkeypatch,
        manager=manager,
        workspace_id=workspace_id,
    )
    try:
        qapp.processEvents()
        assert reopened.project_tutorial_dock.isVisible()
        assert reopened._project_tutorial_session.project_task_id == project_id
        assert reopened._project_tutorial_session.project_idea == "Prepare annual conference"
        assert reopened.project_tutorial_panel.step_title.text() == "Create The Project Root"
    finally:
        reopened.close()
        qapp.processEvents()
