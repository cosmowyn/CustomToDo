from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from context_help import create_context_help_header
from project_tutorial import (
    ProjectTutorialSession,
    ProjectTutorialSnapshot,
    ProjectTutorialStep,
)
from ui_layout import (
    SectionPanel,
    add_left_aligned_buttons,
    configure_box_layout,
    polish_button_layouts,
)


class ProjectTutorialPanel(QWidget):
    backRequested = Signal()
    nextRequested = Signal()
    restartRequested = Signal()
    closeRequested = Signal()
    primaryActionRequested = Signal(str)
    bindCurrentSelectionRequested = Signal()
    openHelpRequested = Signal(str)
    projectIdeaChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_step_id = ""
        self.setObjectName("ProjectTutorialPanel")

        root = QVBoxLayout(self)
        configure_box_layout(root, margins=(8, 8, 8, 8), spacing=10)

        self.help_header = create_context_help_header(
            "Project tutorial",
            "project_tutorial",
            self,
            tooltip="Open help for the guided project tutorial",
        )
        root.addWidget(self.help_header)

        summary_panel = SectionPanel(
            "Tutorial progress",
            "Build a real project while the guide checks your progress.",
        )
        root.addWidget(summary_panel)

        self.progress_label = QLabel("Step 1 of 10")
        self.progress_label.setWordWrap(True)
        summary_panel.body_layout.addWidget(self.progress_label)

        idea_row = QHBoxLayout()
        configure_box_layout(idea_row, spacing=6)
        idea_row.addWidget(QLabel("Project to plan"))
        self.project_idea_edit = QLineEdit()
        self.project_idea_edit.setPlaceholderText(
            "Example: Launch client onboarding workflow"
        )
        self.project_idea_edit.setToolTip(
            "Enter the real project you want to build during the tutorial."
        )
        idea_row.addWidget(self.project_idea_edit, 1)
        summary_panel.body_layout.addLayout(idea_row)

        bind_row = QHBoxLayout()
        configure_box_layout(bind_row, spacing=6)
        self.bound_project_label = QLabel("No project root bound yet.")
        self.bound_project_label.setWordWrap(True)
        bind_row.addWidget(self.bound_project_label, 1)
        self.bind_selection_btn = QPushButton("Use current selection")
        self.bind_selection_btn.setToolTip(
            "Bind the currently selected task as the tutorial project root."
        )
        bind_row.addWidget(self.bind_selection_btn)
        summary_panel.body_layout.addLayout(bind_row)

        concept_panel = SectionPanel(
            "Concept",
            "Why this step matters in project planning.",
        )
        root.addWidget(concept_panel)
        self.step_title = QLabel("Introduction")
        self.step_title.setWordWrap(True)
        self.step_title.setStyleSheet("font-weight: 600;")
        concept_panel.body_layout.addWidget(self.step_title)
        self.concept_body = QLabel("")
        self.concept_body.setWordWrap(True)
        self.concept_body.setTextFormat(Qt.TextFormat.RichText)
        concept_panel.body_layout.addWidget(self.concept_body)

        action_panel = SectionPanel(
            "What to do now",
            "One real action at a time.",
        )
        root.addWidget(action_panel, 1)
        self.action_body = QLabel("")
        self.action_body.setWordWrap(True)
        self.action_body.setTextFormat(Qt.TextFormat.RichText)
        action_panel.body_layout.addWidget(self.action_body)

        self.status_label = QLabel("Status: waiting")
        self.status_label.setWordWrap(True)
        action_panel.body_layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        configure_box_layout(actions)
        self.primary_action_btn = QPushButton("Open relevant area")
        self.help_btn = QPushButton("Related help")
        self.back_btn = QPushButton("Back")
        self.next_btn = QPushButton("Next")
        self.restart_btn = QPushButton("Restart")
        self.close_btn = QPushButton("Hide tutorial")
        add_left_aligned_buttons(
            actions,
            self.primary_action_btn,
            self.help_btn,
            self.back_btn,
            self.next_btn,
            self.restart_btn,
            self.close_btn,
        )
        root.addLayout(actions)

        self.project_idea_edit.textChanged.connect(self.projectIdeaChanged.emit)
        self.bind_selection_btn.clicked.connect(self.bindCurrentSelectionRequested.emit)
        self.primary_action_btn.clicked.connect(
            lambda: self.primaryActionRequested.emit(self._current_step_id)
        )
        self.help_btn.clicked.connect(
            lambda: self.openHelpRequested.emit("project-tutorial")
        )
        self.back_btn.clicked.connect(self.backRequested.emit)
        self.next_btn.clicked.connect(self.nextRequested.emit)
        self.restart_btn.clicked.connect(self.restartRequested.emit)
        self.close_btn.clicked.connect(self.closeRequested.emit)

        polish_button_layouts(self)

    def focus_target(self) -> QWidget | None:
        return self.project_idea_edit

    def render_state(
        self,
        *,
        session: ProjectTutorialSession,
        step: ProjectTutorialStep,
        step_index: int,
        total_steps: int,
        is_complete: bool,
        status_text: str,
        snapshot: ProjectTutorialSnapshot,
    ):
        self._current_step_id = str(step.step_id or "")
        self.progress_label.setText(
            f"Step {int(step_index) + 1} of {int(total_steps)}"
        )
        self.step_title.setText(str(step.title or ""))
        self.concept_body.setText(str(step.concept_html or ""))
        self.action_body.setText(str(step.action_html or ""))
        self.project_idea_edit.blockSignals(True)
        self.project_idea_edit.setText(str(session.project_idea or ""))
        self.project_idea_edit.blockSignals(False)
        if snapshot.project_exists:
            self.bound_project_label.setText(
                f"Bound project root: {snapshot.project_name}"
            )
        elif session.project_task_id is not None:
            self.bound_project_label.setText(
                f"Bound project root missing: task {int(session.project_task_id)}"
            )
        else:
            self.bound_project_label.setText("No project root bound yet.")
        self.status_label.setText(
            f"Status: {'ready' if is_complete else 'not complete yet'} — {status_text}"
        )
        self.primary_action_btn.setVisible(bool(step.primary_action_label))
        self.primary_action_btn.setText(
            str(step.primary_action_label or "Open relevant area")
        )
        self.back_btn.setEnabled(int(step_index) > 0)
        self.next_btn.setText("Finish" if int(step_index) >= int(total_steps) - 1 else "Next")
