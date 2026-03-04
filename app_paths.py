import os
import sys
from pathlib import Path
from PySide6.QtCore import QStandardPaths


def is_frozen() -> bool:
    # PyInstaller sets sys.frozen; bootloader also provides sys._MEIPASS (onefile & onedir)
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> str:
    """
    Base directory for bundled resources.

    - In PyInstaller onefile/onedir, resources are accessible under sys._MEIPASS.
    - Fallback to the executable dir if _MEIPASS is not set for any reason.
    - In dev mode, use the directory containing this file (project root in this app).
    """
    if is_frozen():
        return str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve())
    return str(Path(__file__).resolve().parent)


def resource_path(*relative_parts: str) -> str:
    """
    Resolve a path to a bundled resource (works in dev + frozen).
    Example: resource_path("resources", "app.png")
    """
    return str(Path(bundle_dir(), *relative_parts).resolve())


def app_data_dir() -> str:
    """
    Per-user app data directory (cross-platform):
      - Windows: %APPDATA%\\<Org>\\<App>...
      - macOS: ~/Library/Application Support/<Org>/<App>...
      - Linux: ~/.local/share/<Org>/<App>...
    """
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(base, exist_ok=True)
    return base


def app_db_path() -> str:
    return os.path.join(app_data_dir(), "tasks.sqlite3")