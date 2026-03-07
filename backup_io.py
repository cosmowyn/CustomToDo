from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from db import Database, now_iso


FORMAT_VERSION = 1
ALLOWED_COL_TYPES = {"text", "int", "date", "bool", "list"}


class BackupError(RuntimeError):
    pass


@dataclass
class ImportReport:
    created_columns: int = 0
    skipped_columns: int = 0
    imported_tasks: int = 0
    imported_values: int = 0
    skipped_values: int = 0
    mode: str = ""


def export_backup_ui(parent: QWidget, db: Database) -> None:
    try:
        suggested = f"task_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export backup",
            suggested,
            "JSON Backup (*.json);;All files (*.*)",
        )
        if not out_path:
            return

        payload = export_payload(db)
        write_backup_file(Path(out_path), payload)

        QMessageBox.information(
            parent,
            "Backup exported",
            f"Backup exported successfully.\n\nFile:\n{out_path}",
        )
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Backup export failed",
            _format_exception_message("Export failed", e),
        )


def import_backup_ui(parent: QWidget) -> None:
    try:
        backup_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Select backup file",
            "",
            "JSON Backup (*.json);;All files (*.*)",
        )
        if not backup_path:
            return

        target_db_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Select target database file (new name/location)",
            "restored_tasks.sqlite3",
            "SQLite DB (*.sqlite3 *.db);;All files (*.*)",
        )
        if not target_db_path:
            return

        payload = read_backup_file(Path(backup_path), parent=parent)
        report = import_payload_into_dbfile(
            parent=parent,
            payload=payload,
            target_db_path=Path(target_db_path),
            make_file_backup=True,
        )

        QMessageBox.information(
            parent,
            "Import completed",
            _format_success_report(report, target_db_path),
        )

    except Exception as e:
        QMessageBox.critical(
            parent,
            "Backup import failed",
            _format_exception_message("Import failed", e),
        )


def export_payload(db: Database) -> dict:
    cur = db.conn.cursor()

    cur.execute("PRAGMA user_version;")
    user_version = int(cur.fetchone()[0])

    cur.execute("SELECT id, name, col_type, created_at FROM custom_columns ORDER BY id;")
    cols = [dict(r) for r in cur.fetchall()]
    for c in cols:
        if c.get("col_type") not in ALLOWED_COL_TYPES:
            c["col_type"] = "text"

    cur.execute(
        """
        SELECT column_id, value
        FROM custom_column_list_values
        ORDER BY column_id, sort_order ASC, value ASC;
        """
    )
    list_values_by_col: dict[int, list[str]] = {}
    for r in cur.fetchall():
        cid = int(r["column_id"])
        list_values_by_col.setdefault(cid, []).append(str(r["value"]))

    col_id_to_name = {int(c["id"]): str(c["name"]) for c in cols}

    cur.execute(
        """
        SELECT id, description, due_date, last_update, priority, status,
               parent_id, sort_order, is_collapsed
        FROM tasks
        ORDER BY COALESCE(parent_id, 0), sort_order ASC, id ASC;
        """
    )
    tasks = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT task_id, column_id, value FROM task_custom_values;")
    rows = cur.fetchall()

    values_by_task: dict[int, dict[str, Any]] = {}
    for r in rows:
        tid = int(r["task_id"])
        cid = int(r["column_id"])
        name = col_id_to_name.get(cid)
        if not name:
            continue
        values_by_task.setdefault(tid, {})[name] = r["value"]

    for t in tasks:
        t["custom"] = values_by_task.get(int(t["id"]), {})

    payload_wo_checksum = {
        "format_version": FORMAT_VERSION,
        "exported_at": now_iso(),
        "schema_user_version": user_version,
        "custom_columns": [
            {
                "name": c["name"],
                "col_type": c["col_type"],
                "created_at": c.get("created_at") or now_iso(),
                "list_values": list_values_by_col.get(int(c["id"]), []) if c.get("col_type") == "list" else [],
            }
            for c in cols
        ],
        "tasks": tasks,
    }

    checksum = _sha256_canonical_json(payload_wo_checksum)
    payload_wo_checksum["checksum_sha256"] = checksum
    return payload_wo_checksum


def write_backup_file(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2)

    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def read_backup_file(path: Path, parent: Optional[QWidget] = None) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)

    _validate_payload_shape(payload)

    claimed = str(payload.get("checksum_sha256") or "")
    payload_no = dict(payload)
    payload_no.pop("checksum_sha256", None)
    actual = _sha256_canonical_json(payload_no)

    if claimed and claimed != actual:
        if parent is not None:
            res = QMessageBox.warning(
                parent,
                "Backup integrity warning",
                "The backup checksum does not match.\n\n"
                "This file may be corrupted or edited.\n\n"
                "Do you want to continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if res != QMessageBox.StandardButton.Yes:
                raise BackupError("Import cancelled due to checksum mismatch.")
        else:
            raise BackupError("Checksum mismatch in backup file.")

    return payload


def import_payload_into_dbfile(
    parent: QWidget,
    payload: dict,
    target_db_path: Path,
    make_file_backup: bool = True,
) -> ImportReport:
    target_db_path = Path(target_db_path)

    bak_path = None
    existed_before = target_db_path.exists()
    if make_file_backup and existed_before:
        bak_path = target_db_path.with_suffix(target_db_path.suffix + ".preimport.bak")
        try:
            shutil.copy2(target_db_path, bak_path)
        except Exception:
            bak_path = None

    target_db = Database(str(target_db_path))
    try:
        report = import_payload(parent, payload, target_db)
    except Exception:
        try:
            target_db.conn.close()
        except Exception:
            pass

        if not existed_before:
            try:
                target_db_path.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    finally:
        try:
            target_db.conn.close()
        except Exception:
            pass

    return report


def import_payload(parent: QWidget, payload: dict, target_db: Database) -> ImportReport:
    _validate_payload_shape(payload)

    src_cols = payload["custom_columns"]
    src_tasks = payload["tasks"]

    tgt_cols = _get_target_columns(target_db)
    tgt_col_names = set(tgt_cols.keys())

    missing = [c for c in src_cols if c["name"] not in tgt_col_names]
    allowed_missing = [c for c in missing if c.get("col_type") in ALLOWED_COL_TYPES]
    unknown_type_missing = [c for c in missing if c.get("col_type") not in ALLOWED_COL_TYPES]

    if unknown_type_missing:
        for c in unknown_type_missing:
            c["col_type"] = "text"
        allowed_missing.extend(unknown_type_missing)

    create_missing = True
    if allowed_missing:
        text = "The backup contains custom columns that do not exist in the target database:\n\n"
        text += "\n".join([f"• {c['name']}  ({c['col_type']})" for c in allowed_missing])
        text += "\n\nCreate these columns in the target database before importing?"

        res = QMessageBox.question(
            parent,
            "Missing custom columns",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if res == QMessageBox.StandardButton.Cancel:
            raise BackupError("Import cancelled by user.")
        create_missing = (res == QMessageBox.StandardButton.Yes)

    tgt_task_count = _count_target_tasks(target_db)
    mode = "replace"
    if tgt_task_count > 0:
        res = QMessageBox.question(
            parent,
            "Target database not empty",
            f"The target database already contains {tgt_task_count} task(s).\n\n"
            "Do you want to REPLACE them with the backup content?\n\n"
            "Yes = Replace (clears existing tasks)\n"
            "No = Merge (imports alongside existing tasks)\n"
            "Cancel = Abort",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if res == QMessageBox.StandardButton.Cancel:
            raise BackupError("Import cancelled by user.")
        mode = "replace" if res == QMessageBox.StandardButton.Yes else "merge"

    report = ImportReport(mode=mode)

    try:
        with target_db.tx():
            cur = target_db.conn.cursor()

            if mode == "replace":
                cur.execute("DELETE FROM task_custom_values;")
                cur.execute("DELETE FROM tasks;")

            if allowed_missing and create_missing:
                for c in allowed_missing:
                    cur.execute("SELECT 1 FROM custom_columns WHERE name=?;", (c["name"],))
                    if cur.fetchone():
                        continue
                    cur.execute(
                        "INSERT INTO custom_columns(name, col_type, created_at) VALUES(?, ?, ?);",
                        (c["name"], c["col_type"], c.get("created_at") or now_iso()),
                    )
                    new_col_id = int(cur.lastrowid)
                    if c.get("col_type") == "list":
                        vals = _normalize_list_values(c.get("list_values"))
                        for i, v in enumerate(vals, start=1):
                            cur.execute(
                                """
                                INSERT INTO custom_column_list_values(column_id, value, sort_order)
                                VALUES(?, ?, ?)
                                ON CONFLICT(column_id, value) DO NOTHING;
                                """,
                                (new_col_id, v, i),
                            )
                    report.created_columns += 1
            elif allowed_missing and not create_missing:
                report.skipped_columns = len(allowed_missing)

            tgt_cols = _get_target_columns(target_db)
            for c in src_cols:
                name = str(c.get("name", ""))
                tgt = tgt_cols.get(name)
                if not tgt:
                    continue
                col_id, tgt_type = tgt
                if tgt_type != "list":
                    continue
                vals = _normalize_list_values(c.get("list_values"))
                for v in vals:
                    cur.execute(
                        "SELECT 1 FROM custom_column_list_values WHERE column_id=? AND value=?;",
                        (int(col_id), v),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
                        FROM custom_column_list_values
                        WHERE column_id=?;
                        """,
                        (int(col_id),),
                    )
                    next_order = int(cur.fetchone()["next_order"])
                    cur.execute(
                        """
                        INSERT INTO custom_column_list_values(column_id, value, sort_order)
                        VALUES(?, ?, ?)
                        ON CONFLICT(column_id, value) DO NOTHING;
                        """,
                        (int(col_id), v, next_order),
                    )

            if mode == "replace":
                _import_tasks_keep_ids(cur, src_tasks, tgt_cols, report)
            else:
                task_id_map = {}
                _import_tasks_merge(cur, src_tasks, tgt_cols, report, task_id_map)

    except Exception as e:
        raise BackupError(_format_exception_message("Import transaction failed", e))

    return report


def _import_tasks_keep_ids(cur, src_tasks: list[dict], tgt_cols: dict, report: ImportReport) -> None:
    pending = {int(t["id"]): t for t in src_tasks if "id" in t}
    inserted = set()

    max_passes = len(pending) + 5
    passes = 0

    while pending and passes < max_passes:
        passes += 1
        progress = 0

        for tid in list(pending.keys()):
            t = pending[tid]
            pid = t.get("parent_id")
            if pid is None or int(pid) in inserted or int(pid) not in pending:
                parent_id = int(pid) if (pid is not None and int(pid) in inserted) else None

                cur.execute(
                    """
                    INSERT INTO tasks(id, description, due_date, last_update, priority, status,
                                      parent_id, sort_order, is_collapsed)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        tid,
                        t.get("description", ""),
                        t.get("due_date"),
                        t.get("last_update") or now_iso(),
                        int(t.get("priority", 3)),
                        t.get("status", "Todo"),
                        parent_id,
                        int(t.get("sort_order", 1)),
                        int(t.get("is_collapsed", 0)),
                    ),
                )

                report.imported_tasks += 1
                inserted.add(tid)
                _insert_custom_values(cur, tid, t.get("custom", {}), tgt_cols, report)

                pending.pop(tid, None)
                progress += 1

        if progress == 0:
            for tid, t in list(pending.items()):
                cur.execute(
                    """
                    INSERT INTO tasks(id, description, due_date, last_update, priority, status,
                                      parent_id, sort_order, is_collapsed)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        tid,
                        t.get("description", ""),
                        t.get("due_date"),
                        t.get("last_update") or now_iso(),
                        int(t.get("priority", 3)),
                        t.get("status", "Todo"),
                        None,
                        int(t.get("sort_order", 1)),
                        int(t.get("is_collapsed", 0)),
                    ),
                )
                report.imported_tasks += 1
                inserted.add(tid)
                _insert_custom_values(cur, tid, t.get("custom", {}), tgt_cols, report)
                pending.pop(tid, None)

    if pending:
        raise BackupError("Import failed: could not resolve some parent/child relations (unexpected).")


def _import_tasks_merge(cur, src_tasks: list[dict], tgt_cols: dict, report: ImportReport, id_map: dict[int, int]) -> None:
    cur.execute("SELECT parent_id, COALESCE(MAX(sort_order), 0) AS mx FROM tasks GROUP BY parent_id;")
    max_by_parent = {r["parent_id"]: int(r["mx"]) for r in cur.fetchall()}

    pending = {int(t["id"]): t for t in src_tasks if "id" in t}
    max_passes = len(pending) + 5
    passes = 0

    while pending and passes < max_passes:
        passes += 1
        progress = 0

        for old_id in list(pending.keys()):
            t = pending[old_id]
            old_parent = t.get("parent_id")

            if old_parent is None:
                new_parent = None
                can_insert = True
            else:
                op = int(old_parent)
                if op in id_map:
                    new_parent = id_map[op]
                    can_insert = True
                elif op not in pending:
                    new_parent = None
                    can_insert = True
                else:
                    can_insert = False

            if not can_insert:
                continue

            base = max_by_parent.get(new_parent, 0)
            sort_order = base + int(t.get("sort_order", 1))
            max_by_parent[new_parent] = max(max_by_parent.get(new_parent, 0), sort_order)

            cur.execute(
                """
                INSERT INTO tasks(description, due_date, last_update, priority, status,
                                  parent_id, sort_order, is_collapsed)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    t.get("description", ""),
                    t.get("due_date"),
                    t.get("last_update") or now_iso(),
                    int(t.get("priority", 3)),
                    t.get("status", "Todo"),
                    new_parent,
                    sort_order,
                    int(t.get("is_collapsed", 0)),
                ),
            )
            new_id = int(cur.lastrowid)
            id_map[old_id] = new_id

            report.imported_tasks += 1
            _insert_custom_values(cur, new_id, t.get("custom", {}), tgt_cols, report)

            pending.pop(old_id, None)
            progress += 1

        if progress == 0:
            for old_id, t in list(pending.items()):
                cur.execute(
                    """
                    INSERT INTO tasks(description, due_date, last_update, priority, status,
                                      parent_id, sort_order, is_collapsed)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        t.get("description", ""),
                        t.get("due_date"),
                        t.get("last_update") or now_iso(),
                        int(t.get("priority", 3)),
                        t.get("status", "Todo"),
                        None,
                        int(t.get("sort_order", 1)),
                        int(t.get("is_collapsed", 0)),
                    ),
                )
                new_id = int(cur.lastrowid)
                id_map[old_id] = new_id

                report.imported_tasks += 1
                _insert_custom_values(cur, new_id, t.get("custom", {}), tgt_cols, report)

                pending.pop(old_id, None)


def _insert_custom_values(cur, task_id: int, custom: dict, tgt_cols: dict, report: ImportReport) -> None:
    if not isinstance(custom, dict):
        return

    for name, value in custom.items():
        if name not in tgt_cols:
            report.skipped_values += 1
            continue
        col_id, _col_type = tgt_cols[name]
        cur.execute(
            """
            INSERT INTO task_custom_values(task_id, column_id, value)
            VALUES(?, ?, ?)
            ON CONFLICT(task_id, column_id) DO UPDATE SET value=excluded.value;
            """,
            (int(task_id), int(col_id), None if value is None else str(value)),
        )
        if _col_type == "list" and value is not None:
            sv = str(value).strip()
            if sv:
                cur.execute(
                    "SELECT 1 FROM custom_column_list_values WHERE column_id=? AND value=?;",
                    (int(col_id), sv),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
                        FROM custom_column_list_values
                        WHERE column_id=?;
                        """,
                        (int(col_id),),
                    )
                    next_order = int(cur.fetchone()["next_order"])
                    cur.execute(
                        """
                        INSERT INTO custom_column_list_values(column_id, value, sort_order)
                        VALUES(?, ?, ?)
                        ON CONFLICT(column_id, value) DO NOTHING;
                        """,
                        (int(col_id), sv, next_order),
                    )
        report.imported_values += 1


def _get_target_columns(db: Database) -> dict[str, tuple[int, str]]:
    cur = db.conn.cursor()
    cur.execute("SELECT id, name, col_type FROM custom_columns;")
    out = {}
    for r in cur.fetchall():
        out[str(r["name"])] = (int(r["id"]), str(r["col_type"]) if r["col_type"] in ALLOWED_COL_TYPES else "text")
    return out


def _normalize_list_values(values) -> list[str]:
    if not isinstance(values, list):
        return []
    out = []
    seen = set()
    for v in values:
        s = str(v).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _count_target_tasks(db: Database) -> int:
    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM tasks;")
    return int(cur.fetchone()["c"])


def _validate_payload_shape(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise BackupError("Backup payload is not a JSON object.")

    if int(payload.get("format_version", -1)) != FORMAT_VERSION:
        raise BackupError(f"Unsupported backup format_version: {payload.get('format_version')}")

    if "custom_columns" not in payload or not isinstance(payload["custom_columns"], list):
        raise BackupError("Backup is missing 'custom_columns' list.")

    if "tasks" not in payload or not isinstance(payload["tasks"], list):
        raise BackupError("Backup is missing 'tasks' list.")

    seen = set()
    for c in payload["custom_columns"]:
        if not isinstance(c, dict):
            raise BackupError("Invalid custom_columns entry (not an object).")
        name = str(c.get("name", "")).strip()
        if not name:
            raise BackupError("Custom column with empty name found in backup.")
        lv = c.get("list_values")
        if lv is not None and not isinstance(lv, list):
            raise BackupError("Custom column 'list_values' must be a list if present.")
        if name in seen:
            raise BackupError(f"Duplicate custom column name in backup: {name}")
        seen.add(name)

    for t in payload["tasks"]:
        if not isinstance(t, dict):
            raise BackupError("Invalid task entry (not an object).")
        if "id" not in t:
            raise BackupError("Task missing 'id' in backup.")
        if "custom" in t and t["custom"] is not None and not isinstance(t["custom"], dict):
            raise BackupError("Task 'custom' must be an object if present.")


def _sha256_canonical_json(obj: dict) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _format_exception_message(prefix: str, e: Exception) -> str:
    return (
        f"{prefix}.\n\n"
        f"Type: {type(e).__name__}\n"
        f"Details: {e}\n\n"
        "Tip: If you need deeper debugging, run the app from a terminal to see tracebacks."
    )


def _format_success_report(report: ImportReport, target_db_path: str) -> str:
    lines = [
        "Import finished without errors.",
        "",
        f"Target DB: {target_db_path}",
        f"Mode: {report.mode}",
        "",
        f"Tasks imported: {report.imported_tasks}",
        f"Custom values imported: {report.imported_values}",
    ]
    if report.created_columns:
        lines.append(f"Custom columns created: {report.created_columns}")
    if report.skipped_columns:
        lines.append(f"Custom columns skipped: {report.skipped_columns}")
    if report.skipped_values:
        lines.append(f"Custom values skipped (missing columns): {report.skipped_values}")
    lines.append("")
    lines.append("You can now open the new database file in your app.")
    return "\n".join(lines)
