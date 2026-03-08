# Changelog

All notable changes to this project should be documented in this file.

The format is inspired by Keep a Changelog and uses straightforward dated entries.

## [Unreleased]

No unreleased entries yet.

## [1.0.0] - 2026-03-08

### Added

- Production hardening features including crash logging, diagnostics, integrity checks, migration validation, restore-point reporting, centralized app version metadata, and an in-app application log viewer
- Workflow assistance features including a weekly review assistant, focus mode, onboarding/welcome flow, modular demo dataset generation, floating-table support, and expanded embedded help
- Project intelligence features including next-action analysis, stalled/blocked reasoning, workload warnings, scheduling hints, relationship inspection, and stronger project summaries
- Capture and interaction improvements including quick capture, tray integration, richer inline quick-add parsing, platform-aware shortcuts, and reusable capture command routing
- Advanced workspace and history tooling including portable workspace profiles, snapshot history browsing, safe restore-to-copy flows, safe removal flows for templates, workspaces, and snapshots, and workspace-aware backups
- Additional UI modules, a higher-resolution application icon asset for high-DPI packaging, and automated tests covering core database, model, backup/import, diagnostics, filtering, demo generation, workspace behavior, and project logic

### Changed

- Main application workflows, side panels, command/help surfaces, and filtering logic were expanded to expose the new review, focus, diagnostics, relationship, and workspace capabilities
- Repository hygiene, documentation, legal, and CI scaffolding were prepared for public GitHub use and updated to reflect the current app scope
- Pytest-based automated coverage was extended, CI runtime issues were corrected, and local signing artifacts are ignored in Git on the stable branch
- Style-only PEP 8 cleanup applied to selected UI/helper modules with no intended functional changes

## [0.1.0] - 2026-03-07

### Added

- Initial public repository baseline for the current desktop application
- README, contribution guide, security policy, changelog, issue templates, and CI workflow
- Explicit non-commercial license file and repository disclaimer

### Included Application Capabilities

- Hierarchical task management with custom columns, undo/redo, themes, backups, archive/restore, reminders, review workflow, templates, analytics, and calendar tools
