from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProjectTutorialStep:
    step_id: str
    title: str
    concept_html: str
    action_html: str
    primary_action_label: str = ""
    help_anchor: str = "project-tutorial"


@dataclass
class ProjectTutorialSession:
    active: bool = False
    step_index: int = 0
    project_task_id: int | None = None
    project_idea: str = ""
    completed: bool = False


@dataclass(frozen=True)
class ProjectTutorialSnapshot:
    project_exists: bool = False
    project_name: str = ""
    objective_present: bool = False
    phase_count: int = 0
    work_task_count: int = 0
    milestone_count: int = 0
    dependency_count: int = 0
    blocker_count: int = 0
    dated_item_count: int = 0


PROJECT_TUTORIAL_STEPS: tuple[ProjectTutorialStep, ...] = (
    ProjectTutorialStep(
        "intro",
        "Introduction",
        (
            "<p>A Gantt chart is a time-based view of project work. It helps you see "
            "sequence, overlap, milestones, and blockers without losing the task-tree "
            "structure underneath it.</p>"
            "<p>The project cockpit in Gridoryn combines the charter, phases, "
            "milestones, dependencies, and timeline into one workspace. You will use "
            "it to build a real project step by step.</p>"
        ),
        (
            "<p>Open the project cockpit once so you can see the workspace you will be "
            "using during this tutorial.</p>"
        ),
        primary_action_label="Open project cockpit",
    ),
    ProjectTutorialStep(
        "choose-project",
        "Choose A Real Project",
        (
            "<p>Pick a real outcome you want to manage, not a fake demo. Good choices "
            "have a deadline, a few phases, and at least one external dependency or "
            "approval step.</p>"
            "<p>Think in terms of outcome, major sections, checkpoints, and likely "
            "blockers.</p>"
        ),
        (
            "<p>Enter the real project you want to model in the tutorial panel. This "
            "gives the rest of the tutorial a concrete target.</p>"
        ),
    ),
    ProjectTutorialStep(
        "create-root",
        "Create The Project Root",
        (
            "<p>Every project needs one clear root task. That root becomes the anchor "
            "for phases, milestones, and the cockpit timeline.</p>"
        ),
        (
            "<p>Use Quick add or Add task to create the project root. Then select that "
            "task in the main tree and click <strong>Use current selection</strong> in "
            "the tutorial so the guide can follow your real project.</p>"
        ),
        primary_action_label="Prepare quick add",
    ),
    ProjectTutorialStep(
        "define-phases",
        "Define Phases",
        (
            "<p>Phases keep a plan readable. They are not tasks themselves; they are "
            "the major sections that organize the work and make the timeline easier to "
            "scan.</p>"
        ),
        (
            "<p>Open the cockpit overview and add at least one phase. Two or three is "
            "usually enough to start: for example discovery, build, rollout.</p>"
        ),
        primary_action_label="Open cockpit overview",
    ),
    ProjectTutorialStep(
        "add-tasks",
        "Add Real Work",
        (
            "<p>Break the project into concrete tasks. Tasks should be specific enough "
            "to schedule and track, but not so detailed that the plan becomes a wall of "
            "micro-steps.</p>"
        ),
        (
            "<p>Add at least two real tasks under your project. If a task belongs to a "
            "phase, set its phase in the details panel or cockpit so the plan reads "
            "cleanly later.</p>"
        ),
        primary_action_label="Focus task tree",
    ),
    ProjectTutorialStep(
        "add-milestones",
        "Add A Milestone",
        (
            "<p>A milestone is a checkpoint, not a duration of work. It marks a review, "
            "handoff, launch, approval, or decision point that tells you whether the "
            "project is still on track.</p>"
        ),
        (
            "<p>Open the Milestones tab and create at least one milestone that matters "
            "for this project.</p>"
        ),
        primary_action_label="Open milestones tab",
    ),
    ProjectTutorialStep(
        "dependencies",
        "Model A Blocker Or Dependency",
        (
            "<p>Real projects are rarely independent. Some work is blocked by vendor "
            "input, approvals, or earlier tasks. Explicit dependencies make the chart "
            "honest.</p>"
        ),
        (
            "<p>Create at least one blocker, waiting item, or dependency. You can use a "
            "task dependency, a milestone dependency, or a waiting-for note on a real "
            "task that is stalled on something external.</p>"
        ),
        primary_action_label="Open timeline tab",
    ),
    ProjectTutorialStep(
        "timeline",
        "Put It On The Timeline",
        (
            "<p>The timeline shows sequence and overlap. You do not need a perfect plan; "
            "you need a believable first pass that reveals timing pressure and missing "
            "dependencies.</p>"
        ),
        (
            "<p>Open the Timeline tab and put at least some work on dates. Drag bars or "
            "edit dates until the chart shows a real sequence.</p>"
        ),
        primary_action_label="Open timeline tab",
    ),
    ProjectTutorialStep(
        "review",
        "Review And Improve",
        (
            "<p>Once the chart has real dates and dependencies, review it like a plan: "
            "look for impossible overlaps, missing handoffs, and blockers that should be "
            "visible earlier.</p>"
        ),
        (
            "<p>Use the cockpit to review your plan. If the status below still shows a "
            "gap, add or adjust the missing project structure before moving on.</p>"
        ),
        primary_action_label="Open timeline tab",
    ),
    ProjectTutorialStep(
        "complete",
        "Completion",
        (
            "<p>You now have a real project in the app rather than a demo shell. From "
            "here, keep refining phases, milestones, workload, and dependencies as the "
            "project changes.</p>"
        ),
        (
            "<p>Use the cockpit as your planning surface, the tree for day-to-day task "
            "editing, and the review workflow to keep the plan honest over time.</p>"
        ),
        primary_action_label="Open tutorial help",
    ),
)


def tutorial_step_count() -> int:
    return len(PROJECT_TUTORIAL_STEPS)


def tutorial_step_at(index: int) -> ProjectTutorialStep:
    if not PROJECT_TUTORIAL_STEPS:
        raise IndexError("No tutorial steps configured")
    idx = max(0, min(int(index), len(PROJECT_TUTORIAL_STEPS) - 1))
    return PROJECT_TUTORIAL_STEPS[idx]


def session_from_setting(raw) -> ProjectTutorialSession:
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ProjectTutorialSession()
        try:
            data = json.loads(text)
        except Exception:
            return ProjectTutorialSession()
    if not isinstance(data, dict):
        return ProjectTutorialSession()

    try:
        project_task_id = data.get("project_task_id")
        if project_task_id is not None:
            project_task_id = int(project_task_id)
            if project_task_id <= 0:
                project_task_id = None
    except Exception:
        project_task_id = None

    session = ProjectTutorialSession(
        active=bool(data.get("active", False)),
        step_index=max(0, int(data.get("step_index", 0) or 0)),
        project_task_id=project_task_id,
        project_idea=str(data.get("project_idea") or "").strip(),
        completed=bool(data.get("completed", False)),
    )
    if session.step_index >= tutorial_step_count():
        session.step_index = tutorial_step_count() - 1
    return session


def session_to_setting(session: ProjectTutorialSession | None) -> str:
    payload = asdict(session or ProjectTutorialSession())
    return json.dumps(payload, sort_keys=True)


def reset_session() -> ProjectTutorialSession:
    return ProjectTutorialSession(active=True, step_index=0)


def evaluate_step(
    step_id: str,
    session: ProjectTutorialSession,
    snapshot: ProjectTutorialSnapshot,
) -> tuple[bool, str]:
    if step_id == "intro":
        return True, "Read the overview, then open the project cockpit."
    if step_id == "choose-project":
        ready = bool(session.project_idea.strip())
        return ready, (
            f"Project idea: {session.project_idea.strip()}"
            if ready
            else "Enter the real project you want to build in the tutorial."
        )
    if step_id == "create-root":
        ready = bool(snapshot.project_exists)
        return ready, (
            f"Project root bound: {snapshot.project_name}"
            if ready
            else "Create a root task, select it, and bind it to the tutorial."
        )
    if step_id == "define-phases":
        ready = snapshot.phase_count >= 1
        return ready, (
            f"{snapshot.phase_count} phase(s) created."
            if ready
            else "Add at least one project phase."
        )
    if step_id == "add-tasks":
        ready = snapshot.work_task_count >= 2
        return ready, (
            f"{snapshot.work_task_count} project task(s) created."
            if ready
            else "Add at least two real work tasks under the project."
        )
    if step_id == "add-milestones":
        ready = snapshot.milestone_count >= 1
        return ready, (
            f"{snapshot.milestone_count} milestone(s) created."
            if ready
            else "Add at least one milestone."
        )
    if step_id == "dependencies":
        dependency_like_count = snapshot.dependency_count + snapshot.blocker_count
        ready = dependency_like_count >= 1
        return ready, (
            f"{dependency_like_count} blocker/dependency signal(s) present."
            if ready
            else "Model at least one blocker, waiting item, or dependency."
        )
    if step_id == "timeline":
        ready = snapshot.dated_item_count >= 2
        return ready, (
            f"{snapshot.dated_item_count} dated item(s) are on the timeline."
            if ready
            else "Place at least two items on the timeline."
        )
    if step_id == "review":
        ready = (
            snapshot.phase_count >= 1
            and snapshot.work_task_count >= 2
            and snapshot.milestone_count >= 1
            and (snapshot.dependency_count + snapshot.blocker_count) >= 1
            and snapshot.dated_item_count >= 2
        )
        return ready, (
            "The project now has enough real structure to use the cockpit meaningfully."
            if ready
            else "Review the chart and fill any remaining gaps before you rely on it."
        )
    if step_id == "complete":
        return True, (
            f"Tutorial project: {snapshot.project_name}"
            if snapshot.project_exists
            else "Tutorial complete."
        )
    return False, "Continue with the next step."
