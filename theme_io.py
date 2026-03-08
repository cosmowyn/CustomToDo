from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from crash_logging import log_event, log_exception

THEME_FORMAT_VERSION = 1


class ThemeIOError(RuntimeError):
    pass


def export_themes_ui(parent: QWidget, settings: QSettings) -> None:
    """
    UI flow:
      - pick .json path
      - export themes from QSettings
      - atomic write
      - success/error messagebox
    """
    try:
        suggested = f"themes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export themes",
            suggested,
            "JSON (*.json);;All files (*.*)",
        )
        if not out_path:
            return

        log_event(
            "Theme export started",
            context="theme.export",
            details={"target_path": out_path},
        )
        payload = export_themes_payload(settings)
        write_json_atomic(Path(out_path), payload)
        log_event(
            "Theme export completed",
            context="theme.export",
            details={"target_path": out_path, "theme_count": len(payload.get("themes") or {})},
        )

        QMessageBox.information(
            parent,
            "Themes exported",
            f"Themes exported successfully.\n\nFile:\n{out_path}",
        )
    except Exception as e:
        log_exception(e, context="theme.export")
        QMessageBox.critical(parent, "Theme export failed", _fmt_exc("Export failed", e))


def import_themes_ui(
    parent: QWidget,
    settings: QSettings,
    apply_callback: Optional[Callable[[], None]] = None,
) -> None:
    """
    UI flow:
      - pick themes backup .json
      - validate checksum + structure
      - handle conflicts (overwrite / keep both / skip)
      - import into QSettings
      - optionally set imported current theme active
      - apply_callback() can re-apply theme immediately
    """
    try:
        in_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import themes",
            "",
            "JSON (*.json);;All files (*.*)",
        )
        if not in_path:
            return

        log_event(
            "Theme import started",
            context="theme.import",
            details={"source_path": in_path},
        )
        payload = read_themes_file(Path(in_path), parent=parent)
        report = import_themes_payload(parent, settings, payload)

        if report["applied_current"] and apply_callback:
            try:
                apply_callback()
            except Exception:
                pass

        QMessageBox.information(
            parent,
            "Themes imported",
            _fmt_import_report(report),
        )
        log_event(
            "Theme import completed",
            context="theme.import",
            details={
                "source_path": in_path,
                "mode": str(report.get("mode") or ""),
                "created": int(report.get("created") or 0),
                "overwritten": int(report.get("overwritten") or 0),
                "renamed": int(report.get("renamed") or 0),
                "skipped": int(report.get("skipped") or 0),
                "applied_current": bool(report.get("applied_current")),
            },
        )

    except Exception as e:
        log_exception(e, context="theme.import")
        QMessageBox.critical(parent, "Theme import failed", _fmt_exc("Import failed", e))


def export_themes_payload(settings: QSettings) -> dict:
    names = _get_list(settings, "themes/list")
    current = str(settings.value("themes/current") or "")

    themes: dict[str, dict] = {}
    for name in names:
        raw = settings.value(f"themes/data/{name}")
        if not raw:
            continue
        try:
            themes[name] = json.loads(str(raw))
        except Exception:
            themes[name] = {"name": name}

    payload = {
        "format_version": THEME_FORMAT_VERSION,
        "exported_at": _now_iso(),
        "current_theme": current,
        "themes": themes,
    }
    payload["checksum_sha256"] = _sha256_canonical_json(payload)
    return payload


def import_themes_payload(parent: QWidget, settings: QSettings, payload: dict) -> dict:
    _validate_payload(payload)

    incoming: dict[str, dict] = payload["themes"]
    incoming_current: str = str(payload.get("current_theme") or "")

    existing_names = set(_get_list(settings, "themes/list"))
    incoming_names = list(incoming.keys())
    conflicts = [n for n in incoming_names if n in existing_names]

    mode = "merge"
    if conflicts:
        mode = _prompt_conflict_mode(parent, conflicts)
        if mode == "cancel":
            raise ThemeIOError("Import cancelled by user.")

    final_name_map: dict[str, str] = {}
    created = 0
    overwritten = 0
    skipped = 0
    renamed = 0

    names_list = _get_list(settings, "themes/list")
    names_set = set(names_list)

    for name, theme in incoming.items():
        if not isinstance(theme, dict):
            skipped += 1
            continue

        final_name = name

        if name in names_set:
            if mode == "skip":
                skipped += 1
                continue
            if mode == "overwrite":
                overwritten += 1
            if mode == "keep_both":
                final_name = _unique_name(name, names_set)
                renamed += 1

        theme = dict(theme)
        theme["name"] = final_name

        settings.setValue(f"themes/data/{final_name}", json.dumps(theme, ensure_ascii=False))
        if final_name not in names_set:
            names_list.append(final_name)
            names_set.add(final_name)
            created += 1

        final_name_map[name] = final_name

    settings.setValue("themes/list", names_list)

    applied_current = False
    if incoming_current:
        mapped = final_name_map.get(incoming_current)
        if mapped and mapped in names_set:
            res = QMessageBox.question(
                parent,
                "Set active theme?",
                f"Set imported theme '{mapped}' as the active theme now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if res == QMessageBox.StandardButton.Yes:
                settings.setValue("themes/current", mapped)
                applied_current = True

    return {
        "mode": mode,
        "created": created,
        "overwritten": overwritten,
        "renamed": renamed,
        "skipped": skipped,
        "applied_current": applied_current,
    }


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_themes_file(path: Path, parent: Optional[QWidget] = None) -> dict:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    _validate_payload(payload)

    claimed = str(payload.get("checksum_sha256") or "")
    actual = _sha256_canonical_json(payload)

    if claimed and claimed != actual:
        if parent is not None:
            res = QMessageBox.warning(
                parent,
                "Themes integrity warning",
                "Checksum mismatch.\n\n"
                "The file may be corrupted or edited.\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if res != QMessageBox.StandardButton.Yes:
                raise ThemeIOError("Import cancelled due to checksum mismatch.")
        else:
            raise ThemeIOError("Checksum mismatch.")
    return payload


def _validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ThemeIOError("Theme backup is not a JSON object.")
    if int(payload.get("format_version", -1)) != THEME_FORMAT_VERSION:
        raise ThemeIOError(f"Unsupported theme backup format_version: {payload.get('format_version')}")
    if "themes" not in payload or not isinstance(payload["themes"], dict):
        raise ThemeIOError("Theme backup missing 'themes' object.")
    for k, v in payload["themes"].items():
        if not isinstance(k, str) or not k.strip():
            raise ThemeIOError("Theme backup contains an invalid theme name.")
        if not isinstance(v, dict):
            raise ThemeIOError(f"Theme '{k}' data is not an object.")


def _sha256_canonical_json(payload: dict) -> str:
    p = dict(payload)
    p["checksum_sha256"] = ""
    s = json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _get_list(settings: QSettings, key: str) -> list[str]:
    v = settings.value(key, [])
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return []


def _unique_name(base: str, taken: set[str]) -> str:
    cand = f"{base} (imported)"
    if cand not in taken:
        return cand
    i = 2
    while True:
        cand = f"{base} (imported {i})"
        if cand not in taken:
            return cand
        i += 1


def _prompt_conflict_mode(parent: QWidget, conflicts: list[str]) -> str:
    preview = "\n".join([f"• {n}" for n in conflicts[:12]])
    if len(conflicts) > 12:
        preview += f"\n… and {len(conflicts) - 12} more"

    mb = QMessageBox(parent)
    mb.setIcon(QMessageBox.Icon.Question)
    mb.setWindowTitle("Theme name conflicts")
    mb.setText(
        "Some imported themes already exist in your app:\n\n"
        f"{preview}\n\n"
        "Choose how to handle conflicts:"
    )

    btn_overwrite = mb.addButton("Overwrite existing", QMessageBox.ButtonRole.AcceptRole)
    btn_keep = mb.addButton("Keep both (rename imported)", QMessageBox.ButtonRole.ActionRole)
    btn_skip = mb.addButton("Skip conflicting", QMessageBox.ButtonRole.ActionRole)
    btn_cancel = mb.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

    mb.setDefaultButton(btn_keep)
    mb.exec()

    clicked = mb.clickedButton()
    if clicked == btn_overwrite:
        return "overwrite"
    if clicked == btn_keep:
        return "keep_both"
    if clicked == btn_skip:
        return "skip"
    return "cancel"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _fmt_exc(prefix: str, e: Exception) -> str:
    return (
        f"{prefix}.\n\n"
        f"Type: {type(e).__name__}\n"
        f"Details: {e}\n\n"
        "Tip: run from a terminal to see full tracebacks if needed."
    )


def _fmt_import_report(r: dict) -> str:
    lines = [
        "Theme import completed.",
        "",
        f"Conflict mode: {r['mode']}",
        f"New themes added: {r['created']}",
        f"Themes overwritten: {r['overwritten']}",
        f"Themes renamed: {r['renamed']}",
        f"Themes skipped: {r['skipped']}",
    ]
    if r.get("applied_current"):
        lines.append("")
        lines.append("Active theme was updated.")
    return "\n".join(lines)
