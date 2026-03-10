from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ui_layout import (
    DEFAULT_DIALOG_MARGINS,
    SectionPanel,
    add_form_row,
    add_left_aligned_buttons,
    configure_box_layout,
    configure_form_layout,
    polish_button_layouts,
)


ICON_SOURCE_PRESET = "preset"
ICON_SOURCE_EMOJI = "emoji"
ICON_SOURCE_FILE = "file"

DEFAULT_FOLDER_ICON_KEY = "folder"
DEFAULT_FOLDER_EMOJI = "📁"

ICON_PRESETS = [
    {"key": "folder", "label": "Folder", "themes": ["folder"], "fallback": "SP_DirIcon"},
    {"key": "folder_open", "label": "Open folder", "themes": ["folder-open"], "fallback": "SP_DirOpenIcon"},
    {"key": "home", "label": "Home", "themes": ["user-home", "go-home"], "fallback": "SP_DirHomeIcon"},
    {"key": "briefcase", "label": "Briefcase", "themes": ["folder-documents", "document-open-recent"], "fallback": "SP_FileDialogDetailedView"},
    {"key": "document", "label": "Document", "themes": ["text-x-generic", "document-new"], "fallback": "SP_FileIcon"},
    {"key": "documents", "label": "Documents", "themes": ["folder-documents"], "fallback": "SP_FileDialogContentsView"},
    {"key": "download", "label": "Download", "themes": ["folder-download", "go-down"], "fallback": "SP_ArrowDown"},
    {"key": "upload", "label": "Upload", "themes": ["folder-upload", "go-up"], "fallback": "SP_ArrowUp"},
    {"key": "computer", "label": "Computer", "themes": ["computer"], "fallback": "SP_ComputerIcon"},
    {"key": "network", "label": "Network", "themes": ["network-workgroup", "network-server"], "fallback": "SP_DriveNetIcon"},
    {"key": "drive", "label": "Drive", "themes": ["drive-harddisk"], "fallback": "SP_DriveHDIcon"},
    {"key": "calendar", "label": "Calendar", "themes": ["x-office-calendar", "view-calendar"], "fallback": "SP_FileDialogContentsView"},
    {"key": "clock", "label": "Clock", "themes": ["alarm", "appointment-new"], "fallback": "SP_BrowserReload"},
    {"key": "bookmark", "label": "Bookmark", "themes": ["bookmark-new", "bookmarks"], "fallback": "SP_FileDialogContentsView"},
    {"key": "flag", "label": "Flag", "themes": ["flag", "emblem-important"], "fallback": "SP_MessageBoxWarning"},
    {"key": "star", "label": "Star", "themes": ["starred", "rating"], "fallback": "SP_DialogApplyButton"},
    {"key": "tag", "label": "Tag", "themes": ["tag", "tag-new"], "fallback": "SP_FileDialogListView"},
    {"key": "archive", "label": "Archive", "themes": ["folder-archive", "mail-archive"], "fallback": "SP_DirClosedIcon"},
    {"key": "inbox", "label": "Inbox", "themes": ["mail-folder-inbox"], "fallback": "SP_DialogOpenButton"},
    {"key": "cloud", "label": "Cloud", "themes": ["folder-cloud", "network-server"], "fallback": "SP_DriveNetIcon"},
    {"key": "settings", "label": "Settings", "themes": ["preferences-system", "configure"], "fallback": "SP_FileDialogDetailedView"},
    {"key": "warning", "label": "Warning", "themes": ["dialog-warning"], "fallback": "SP_MessageBoxWarning"},
    {"key": "info", "label": "Information", "themes": ["dialog-information"], "fallback": "SP_MessageBoxInformation"},
    {"key": "help", "label": "Help", "themes": ["help-browser", "dialog-question"], "fallback": "SP_MessageBoxQuestion"},
    {"key": "check", "label": "Check", "themes": ["emblem-default", "task-complete"], "fallback": "SP_DialogApplyButton"},
    {"key": "search", "label": "Search", "themes": ["system-search", "edit-find"], "fallback": "SP_FileDialogContentsView"},
    {"key": "trash", "label": "Trash", "themes": ["user-trash"], "fallback": "SP_TrashIcon"},
    {"key": "lock", "label": "Lock", "themes": ["object-locked"], "fallback": "SP_MessageBoxCritical"},
]

ICON_PRESET_BY_KEY = {entry["key"]: entry for entry in ICON_PRESETS}

EMOJI_PRESETS = [
    ("📁", "Folder"),
    ("🗂️", "Organizer"),
    ("🧰", "Toolkit"),
    ("📦", "Package"),
    ("🏠", "Home"),
    ("💼", "Work"),
    ("🚀", "Launch"),
    ("🛒", "Shopping"),
    ("💡", "Ideas"),
    ("🧠", "Thinking"),
    ("📚", "Learning"),
    ("📝", "Writing"),
    ("🎯", "Goals"),
    ("📅", "Calendar"),
    ("⏰", "Time"),
    ("✅", "Done"),
    ("⚠️", "Warning"),
    ("🔒", "Secure"),
    ("🔧", "Maintenance"),
    ("🖥️", "Computer"),
    ("🌐", "Web"),
    ("☁️", "Cloud"),
    ("💰", "Finance"),
    ("🏷️", "Tagged"),
    ("🎨", "Design"),
    ("🎵", "Music"),
    ("📷", "Media"),
    ("✈️", "Travel"),
    ("🏃", "Health"),
    ("🌱", "Growth"),
]


def folder_display_name(folder: dict | None) -> str:
    if not folder:
        return ""
    identifier = str(folder.get("identifier") or "").strip()
    name = str(folder.get("name") or "").strip()
    return f"[{identifier}] {name}" if identifier else name


def parse_folder_icon_spec(icon_name: str | None) -> tuple[str, str]:
    raw = str(icon_name or "").strip()
    if not raw:
        return ICON_SOURCE_PRESET, DEFAULT_FOLDER_ICON_KEY
    if raw.startswith(f"{ICON_SOURCE_EMOJI}:"):
        value = raw.split(":", 1)[1].strip()
        return ICON_SOURCE_EMOJI, value or DEFAULT_FOLDER_EMOJI
    if raw.startswith(f"{ICON_SOURCE_FILE}:"):
        value = raw.split(":", 1)[1].strip()
        return ICON_SOURCE_FILE, value
    if raw.startswith(f"{ICON_SOURCE_PRESET}:"):
        value = raw.split(":", 1)[1].strip().lower()
        return ICON_SOURCE_PRESET, value or DEFAULT_FOLDER_ICON_KEY
    return ICON_SOURCE_PRESET, raw.lower() or DEFAULT_FOLDER_ICON_KEY


def folder_icon_spec(source: str, value: str | None) -> str:
    src = str(source or ICON_SOURCE_PRESET).strip().lower()
    text = str(value or "").strip()
    if src == ICON_SOURCE_EMOJI:
        return f"{ICON_SOURCE_EMOJI}:{text or DEFAULT_FOLDER_EMOJI}"
    if src == ICON_SOURCE_FILE:
        return f"{ICON_SOURCE_FILE}:{text}"
    return f"{ICON_SOURCE_PRESET}:{text.lower() or DEFAULT_FOLDER_ICON_KEY}"


def folder_icon_description(icon_name: str | None) -> str:
    source, value = parse_folder_icon_spec(icon_name)
    if source == ICON_SOURCE_EMOJI:
        return f"Emoji: {value}"
    if source == ICON_SOURCE_FILE:
        return f"File icon: {value}" if value else "File icon"
    preset = ICON_PRESET_BY_KEY.get(value)
    if preset:
        return f"Built-in icon: {preset['label']}"
    return f"Built-in icon: {value}"


def _style_standard_icon(name: str, default_name: str = "SP_DirIcon") -> QIcon:
    style = QApplication.style()
    if style is None:
        return QIcon()
    fallback = getattr(QStyle.StandardPixmap, name, None)
    if fallback is None:
        fallback = getattr(QStyle.StandardPixmap, default_name, QStyle.StandardPixmap.SP_DirIcon)
    return style.standardIcon(fallback)


def _emoji_icon(value: str) -> QIcon:
    text = str(value or "").strip()
    if not text:
        text = DEFAULT_FOLDER_EMOJI
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(QApplication.font())
    font.setPointSize(max(font.pointSize(), 18))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


def folder_icon(icon_name: str | None) -> QIcon:
    source, value = parse_folder_icon_spec(icon_name)

    if source == ICON_SOURCE_EMOJI:
        return _emoji_icon(value)

    if source == ICON_SOURCE_FILE:
        if value and os.path.isfile(value):
            icon = QIcon(value)
            if not icon.isNull():
                return icon
        return folder_icon(folder_icon_spec(ICON_SOURCE_PRESET, DEFAULT_FOLDER_ICON_KEY))

    preset = ICON_PRESET_BY_KEY.get(value)
    if preset is None:
        theme_names = [value]
        fallback_name = "SP_DirIcon"
    else:
        theme_names = preset["themes"]
        fallback_name = preset["fallback"]

    for theme_name in theme_names:
        icon = QIcon.fromTheme(theme_name)
        if not icon.isNull():
            return icon
    return _style_standard_icon(fallback_name)


def default_system_icon_dir() -> str:
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates = [
            "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources",
            "/System/Library/CoreServices",
            "/System/Library/Extensions",
        ]
    elif sys.platform.startswith("win"):
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        candidates = [
            os.path.join(system_root, "System32"),
            os.path.join(system_root, "SystemResources"),
            os.path.join(system_root, "Web"),
        ]
    else:
        candidates = [
            "/usr/share/icons",
            "/usr/share/pixmaps",
            os.path.expanduser("~/.icons"),
            os.path.expanduser("~/.local/share/icons"),
        ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return str(Path.home())


def _set_color_button(button: QPushButton, color_hex: str | None):
    color = str(color_hex or "").strip()
    button.setText(color if color else "Default")
    if color:
        qcolor = QColor(color)
        text_color = "#ffffff" if qcolor.lightness() < 140 else "#000000"
        button.setStyleSheet(
            "QPushButton {"
            f"background:{color};"
            f"color:{text_color};"
            "}"
        )
    else:
        button.setStyleSheet("")


class CategoryFolderDialog(QDialog):
    def __init__(self, folder: dict | None = None, parent=None):
        super().__init__(parent)
        self._folder = dict(folder or {})
        self._color_hex = str(self._folder.get("color_hex") or "").strip() or None
        self._text_color_hex = str(self._folder.get("text_color_hex") or "").strip() or None
        self.setWindowTitle("Category properties")
        self.resize(580, 360)

        root = QVBoxLayout(self)
        configure_box_layout(root, margins=DEFAULT_DIALOG_MARGINS, spacing=10)

        section = SectionPanel(
            "Category folder",
            "Customize the label, icon, and color used for this category.",
        )
        root.addWidget(section, 1)

        form = QFormLayout()
        configure_form_layout(form, label_width=110)
        section.body_layout.addLayout(form)

        self.name_edit = QLineEdit(str(self._folder.get("name") or ""))
        add_form_row(form, "Name", self.name_edit)

        self.identifier_edit = QLineEdit(str(self._folder.get("identifier") or ""))
        self.identifier_edit.setPlaceholderText("Optional short identifier")
        add_form_row(form, "Identifier", self.identifier_edit)

        self.icon_source_combo = QComboBox()
        self.icon_source_combo.addItem("Built-in UI icon", ICON_SOURCE_PRESET)
        self.icon_source_combo.addItem("Emoji", ICON_SOURCE_EMOJI)
        self.icon_source_combo.addItem("Icon file…", ICON_SOURCE_FILE)

        self.icon_stack = QStackedWidget()

        preset_page = QWidget()
        preset_layout = QHBoxLayout(preset_page)
        configure_box_layout(preset_layout)
        self.icon_preset_combo = QComboBox()
        for entry in ICON_PRESETS:
            self.icon_preset_combo.addItem(
                folder_icon(folder_icon_spec(ICON_SOURCE_PRESET, entry["key"])),
                entry["label"],
                entry["key"],
            )
        preset_layout.addWidget(self.icon_preset_combo, 1)

        emoji_page = QWidget()
        emoji_layout = QVBoxLayout(emoji_page)
        configure_box_layout(emoji_layout, spacing=6)
        self.icon_emoji_combo = QComboBox()
        self.icon_emoji_combo.setEditable(True)
        self.icon_emoji_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.icon_emoji_combo.setMaxVisibleItems(16)
        for emoji, label in EMOJI_PRESETS:
            self.icon_emoji_combo.addItem(emoji, emoji)
            emoji_index = self.icon_emoji_combo.count() - 1
            self.icon_emoji_combo.setItemData(emoji_index, label, Qt.ItemDataRole.ToolTipRole)
        self.icon_emoji_edit = self.icon_emoji_combo.lineEdit()
        if self.icon_emoji_edit is not None:
            self.icon_emoji_edit.setPlaceholderText("Pick an emoji or type your own")
        emoji_layout.addWidget(self.icon_emoji_combo)
        emoji_hint = QLabel("Choose a preset emoji or type your own symbol.")
        emoji_hint.setWordWrap(True)
        emoji_layout.addWidget(emoji_hint)

        file_page = QWidget()
        file_layout = QHBoxLayout(file_page)
        configure_box_layout(file_layout)
        self.icon_file_edit = QLineEdit()
        self.icon_file_edit.setPlaceholderText("Choose a .png, .ico, .icns, .svg, or similar icon file")
        self.icon_browse_btn = QPushButton("Browse…")
        file_layout.addWidget(self.icon_file_edit, 1)
        file_layout.addWidget(self.icon_browse_btn)

        self.icon_stack.addWidget(preset_page)
        self.icon_stack.addWidget(emoji_page)
        self.icon_stack.addWidget(file_page)

        icon_row = QWidget()
        icon_row_layout = QVBoxLayout(icon_row)
        configure_box_layout(icon_row_layout, spacing=6)
        icon_row_layout.addWidget(self.icon_source_combo)
        icon_row_layout.addWidget(self.icon_stack)
        add_form_row(form, "Icon", icon_row)

        color_row = QHBoxLayout()
        configure_box_layout(color_row)
        self.color_btn = QPushButton()
        _set_color_button(self.color_btn, self._color_hex)
        self.clear_color_btn = QPushButton("Clear")
        color_row.addWidget(self.color_btn)
        color_row.addWidget(self.clear_color_btn)
        add_form_row(form, "Color", color_row)

        text_color_row = QHBoxLayout()
        configure_box_layout(text_color_row)
        self.text_color_btn = QPushButton()
        _set_color_button(self.text_color_btn, self._text_color_hex)
        self.clear_text_color_btn = QPushButton("Clear")
        text_color_row.addWidget(self.text_color_btn)
        text_color_row.addWidget(self.clear_text_color_btn)
        add_form_row(form, "Text color", text_color_row)

        preview_row = QHBoxLayout()
        configure_box_layout(preview_row)
        self.preview_icon_label = QLabel()
        self.preview_icon_label.setMinimumSize(QSize(18, 18))
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        preview_row.addWidget(self.preview_icon_label)
        preview_row.addWidget(self.preview_label, 1)
        section.body_layout.addLayout(preview_row)

        actions = QHBoxLayout()
        configure_box_layout(actions)
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        add_left_aligned_buttons(actions, self.save_btn, self.cancel_btn)
        section.body_layout.addLayout(actions)

        self.color_btn.clicked.connect(self._pick_color)
        self.clear_color_btn.clicked.connect(self._clear_color)
        self.text_color_btn.clicked.connect(self._pick_text_color)
        self.clear_text_color_btn.clicked.connect(self._clear_text_color)
        self.icon_source_combo.currentIndexChanged.connect(self._on_icon_source_changed)
        self.icon_preset_combo.currentIndexChanged.connect(self._update_preview)
        self.icon_emoji_combo.currentIndexChanged.connect(self._update_preview)
        self.icon_emoji_combo.currentTextChanged.connect(self._update_preview)
        self.icon_file_edit.textChanged.connect(self._update_preview)
        self.icon_browse_btn.clicked.connect(self._browse_icon_file)
        self.name_edit.textChanged.connect(self._update_preview)
        self.identifier_edit.textChanged.connect(self._update_preview)
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._load_existing_icon_spec()
        polish_button_layouts(self)
        self._update_preview()

    def _load_existing_icon_spec(self):
        source, value = parse_folder_icon_spec(self._folder.get("icon_name"))
        source_index = self.icon_source_combo.findData(source)
        self.icon_source_combo.setCurrentIndex(source_index if source_index >= 0 else 0)

        if source == ICON_SOURCE_EMOJI:
            emoji_index = self.icon_emoji_combo.findData(value)
            if emoji_index >= 0:
                self.icon_emoji_combo.setCurrentIndex(emoji_index)
            else:
                self.icon_emoji_combo.setEditText(value)
        elif source == ICON_SOURCE_FILE:
            self.icon_file_edit.setText(value)
        else:
            preset_index = self.icon_preset_combo.findData(value)
            self.icon_preset_combo.setCurrentIndex(preset_index if preset_index >= 0 else 0)

        self._on_icon_source_changed()

    def _current_icon_spec(self) -> str:
        source = str(self.icon_source_combo.currentData() or ICON_SOURCE_PRESET)
        if source == ICON_SOURCE_EMOJI:
            return folder_icon_spec(source, self.icon_emoji_combo.currentText())
        if source == ICON_SOURCE_FILE:
            return folder_icon_spec(source, self.icon_file_edit.text())
        return folder_icon_spec(source, self.icon_preset_combo.currentData())

    def _on_icon_source_changed(self):
        source = str(self.icon_source_combo.currentData() or ICON_SOURCE_PRESET)
        index = {
            ICON_SOURCE_PRESET: 0,
            ICON_SOURCE_EMOJI: 1,
            ICON_SOURCE_FILE: 2,
        }.get(source, 0)
        self.icon_stack.setCurrentIndex(index)
        self._update_preview()

    def _browse_icon_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose icon file",
            default_system_icon_dir(),
            "Icons (*.png *.svg *.svgz *.ico *.icns *.jpg *.jpeg *.bmp *.webp);;All files (*.*)",
        )
        if path:
            self.icon_file_edit.setText(path)
            source_index = self.icon_source_combo.findData(ICON_SOURCE_FILE)
            self.icon_source_combo.setCurrentIndex(source_index if source_index >= 0 else 0)

    def _pick_color(self):
        chosen = QColorDialog.getColor(parent=self)
        if not chosen.isValid():
            return
        self._color_hex = chosen.name()
        _set_color_button(self.color_btn, self._color_hex)
        self._update_preview()

    def _clear_color(self):
        self._color_hex = None
        _set_color_button(self.color_btn, None)
        self._update_preview()

    def _pick_text_color(self):
        chosen = QColorDialog.getColor(parent=self)
        if not chosen.isValid():
            return
        self._text_color_hex = chosen.name()
        _set_color_button(self.text_color_btn, self._text_color_hex)
        self._update_preview()

    def _clear_text_color(self):
        self._text_color_hex = None
        _set_color_button(self.text_color_btn, None)
        self._update_preview()

    def _update_preview(self):
        preview_folder = {
            "name": self.name_edit.text().strip(),
            "identifier": self.identifier_edit.text().strip(),
        }
        text = folder_display_name(preview_folder) or "(unnamed category)"
        description = folder_icon_description(self._current_icon_spec())
        self.preview_label.setText(f"Preview: {text}\n{description}")
        self.preview_icon_label.setPixmap(folder_icon(self._current_icon_spec()).pixmap(16, 16))
        styles: list[str] = []
        if self._text_color_hex:
            styles.append(f"color:{self._text_color_hex};")
        if self._color_hex:
            bg = QColor(self._color_hex)
            bg.setAlpha(26)
            styles.append(
                "background-color:"
                f"rgba({bg.red()}, {bg.green()}, {bg.blue()}, {bg.alpha()});"
            )
        self.preview_label.setStyleSheet("".join(styles))

    def payload(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "identifier": self.identifier_edit.text().strip() or None,
            "icon_name": self._current_icon_spec(),
            "color_hex": self._color_hex,
            "text_color_hex": self._text_color_hex,
        }
