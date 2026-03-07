from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app_paths import app_data_dir
from backup_io import export_payload, write_backup_file


def backups_dir() -> Path:
    p = Path(app_data_dir()) / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_versioned_backup(db, reason: str = "auto") -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"task_snapshot_{ts}_{reason}.json"
    path = backups_dir() / filename
    payload = export_payload(db)
    write_backup_file(path, payload)
    return path


def rotate_backups(max_keep: int = 20):
    keep = max(1, int(max_keep))
    files = sorted(backups_dir().glob("task_snapshot_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            continue
