from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QColorDialog

from db import Database

from category_folders_ui import (
    CategoryFolderDialog,
    DEFAULT_FOLDER_EMOJI,
    ICON_SOURCE_EMOJI,
    ICON_SOURCE_FILE,
    ICON_SOURCE_PRESET,
    EMOJI_PRESETS,
    folder_icon,
    folder_icon_description,
)


def test_folder_icon_supports_emoji_and_file_specs(tmp_path, qapp):
    image_path = Path(tmp_path) / "folder-icon.png"
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ff0000"))
    assert image.save(str(image_path))

    assert not folder_icon("emoji:📁").isNull()
    assert not folder_icon(f"file:{image_path}").isNull()
    assert not folder_icon("preset:calendar").isNull()


def test_category_folder_dialog_loads_and_emits_icon_specs(tmp_path, qapp):
    image_path = Path(tmp_path) / "folder-icon.png"
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(QColor("#00aa88"))
    assert image.save(str(image_path))

    dialog = CategoryFolderDialog({"icon_name": "emoji:🚀"})
    assert dialog.icon_source_combo.currentData() == ICON_SOURCE_EMOJI
    assert dialog.icon_emoji_combo.currentText() == "🚀"

    dialog.icon_source_combo.setCurrentIndex(
        dialog.icon_source_combo.findData(ICON_SOURCE_PRESET)
    )
    dialog.icon_preset_combo.setCurrentIndex(
        dialog.icon_preset_combo.findData("calendar")
    )
    assert dialog.payload()["icon_name"] == "preset:calendar"

    dialog.icon_source_combo.setCurrentIndex(
        dialog.icon_source_combo.findData(ICON_SOURCE_FILE)
    )
    dialog.icon_file_edit.setText(str(image_path))
    assert dialog.payload()["icon_name"] == f"file:{image_path}"


def test_category_folder_dialog_preloads_emoji_list_and_supports_text_color(monkeypatch, qapp):
    dialog = CategoryFolderDialog({"icon_name": "emoji:🚀", "text_color_hex": "#ffffff"})
    assert dialog.icon_emoji_combo.count() == len(EMOJI_PRESETS)
    assert dialog.icon_emoji_combo.currentText() == "🚀"
    assert dialog.payload()["text_color_hex"] == "#ffffff"

    monkeypatch.setattr(QColorDialog, "getColor", lambda parent=None: QColor("#112233"))
    dialog._pick_text_color()
    assert dialog.payload()["text_color_hex"] == "#112233"

    dialog.icon_source_combo.setCurrentIndex(dialog.icon_source_combo.findData(ICON_SOURCE_EMOJI))
    dialog.icon_emoji_combo.setEditText("")
    assert dialog.payload()["icon_name"] == f"emoji:{DEFAULT_FOLDER_EMOJI}"


def test_category_folder_db_roundtrip_preserves_text_color(tmp_path):
    db = Database(str(tmp_path / "folders.sqlite3"))
    folder_id = db.create_category_folder(
        "Visual",
        color_hex="#224466",
        text_color_hex="#f8f9fa",
        icon_name="emoji:🎨",
    )
    folder = db.fetch_category_folder(folder_id)
    assert folder is not None
    assert str(folder.get("text_color_hex") or "").lower() == "#f8f9fa"
    db.close()


def test_folder_icon_description_is_human_readable(qapp):
    assert folder_icon_description("emoji:📁") == "Emoji: 📁"
    assert "Built-in icon" in folder_icon_description("preset:folder")
    assert "File icon" in folder_icon_description("file:/tmp/example.png")
