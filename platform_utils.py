from __future__ import annotations

import sys

from PySide6.QtGui import QKeySequence


OS_MACOS = "macos"
OS_WINDOWS = "windows"
OS_LINUX = "linux"
OS_OTHER = "other"


def current_os() -> str:
    plat = sys.platform.lower()
    if plat.startswith("darwin"):
        return OS_MACOS
    if plat.startswith("win"):
        return OS_WINDOWS
    if plat.startswith("linux"):
        return OS_LINUX
    return OS_OTHER


def is_macos() -> bool:
    return current_os() == OS_MACOS


def is_windows() -> bool:
    return current_os() == OS_WINDOWS


def is_linux() -> bool:
    return current_os() == OS_LINUX


def _normalize_shortcut_spec(spec: str, os_name: str | None = None) -> str:
    text = str(spec or "").strip()
    if not text:
        return ""
    active_os = os_name or current_os()
    if active_os == OS_MACOS:
        return (
            text.replace("Command+", "Meta+")
            .replace("Cmd+", "Meta+")
            .replace("Ctrl+", "Meta+")
        )
    return text.replace("Command+", "Ctrl+").replace("Cmd+", "Ctrl+")


def shortcut_sequence(spec: str, os_name: str | None = None) -> QKeySequence:
    return QKeySequence(_normalize_shortcut_spec(spec, os_name=os_name))


def shortcut_display_text(
    value: str | QKeySequence | QKeySequence.StandardKey,
    os_name: str | None = None,
) -> str:
    if isinstance(value, QKeySequence):
        seq = value
    elif isinstance(value, QKeySequence.StandardKey):
        seq = QKeySequence(value)
    else:
        seq = shortcut_sequence(str(value or ""), os_name=os_name)

    text = seq.toString(QKeySequence.SequenceFormat.PortableText)
    if not text:
        return ""

    active_os = os_name or current_os()
    if active_os == OS_MACOS:
        mapping = {
            "Meta": "Command",
            "Alt": "Option",
            "Ctrl": "Control",
        }
    elif active_os == OS_WINDOWS:
        mapping = {"Meta": "Win"}
    else:
        mapping = {"Meta": "Super"}

    parts = [mapping.get(part, part) for part in text.split("+")]
    return "+".join(parts)
