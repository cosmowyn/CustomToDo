from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QColorDialog, QFontDialog, QFileDialog, QLineEdit,
    QGroupBox, QFormLayout, QPlainTextEdit, QMessageBox,
    QInputDialog, QScrollArea, QWidget
)

from theme import ThemeManager, default_theme_dict


def _set_color_btn(btn: QPushButton, color: str):
    btn.setText(color)
    btn.setStyleSheet(f"background: {color}; border: 1px solid rgba(255,255,255,0.25); padding: 6px 10px;")


def _font_label(font: QFont) -> str:
    return f"{font.family()} {max(font.pointSize(), 10)}pt"


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings & Themes")
        self.setMinimumSize(760, 720)

        self.tm = ThemeManager(settings)

        self._theme_name: str = self.tm.current_theme_name()
        self._theme: dict = self.tm.load_theme(self._theme_name)

        root = QVBoxLayout(self)

        # --- Top: theme selector + actions
        top = QHBoxLayout()
        top.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self.tm.list_themes())
        self.theme_combo.setCurrentText(self._theme_name)
        self.theme_combo.currentTextChanged.connect(self._on_theme_selected)
        top.addWidget(self.theme_combo, 1)

        self.btn_new = QPushButton("New")
        self.btn_save = QPushButton("Save")
        self.btn_save_as = QPushButton("Save as…")
        self.btn_delete = QPushButton("Delete")

        self.btn_new.clicked.connect(self._new_theme)
        self.btn_save.clicked.connect(self._save_theme)
        self.btn_save_as.clicked.connect(self._save_as_theme)
        self.btn_delete.clicked.connect(self._delete_theme)

        top.addWidget(self.btn_new)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_save_as)
        top.addWidget(self.btn_delete)

        root.addLayout(top)

        # --- Scrollable editor
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        editor = QWidget()
        self.form_root = QVBoxLayout(editor)
        self.form_root.setContentsMargins(0, 0, 0, 0)
        self.form_root.setSpacing(10)
        scroll.setWidget(editor)

        # --- Groups
        self._build_application_group()
        self._build_fonts_group()
        self._build_search_group()
        self._build_row_action_buttons_group()  # ✅ NEW
        self._build_window_group()
        self._build_menus_toolbar_group()
        self._build_header_group()
        self._build_tree_group()
        self._build_buttons_group()
        self._build_inputs_group()
        self._build_selection_group()
        self._build_advanced_group()

        # --- Bottom buttons
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self._ok)
        cancel.clicked.connect(self.reject)
        bottom.addWidget(ok)
        bottom.addWidget(cancel)
        root.addLayout(bottom)

        self._load_theme_into_controls()

    # ---------- UI building ----------
    def _mk_group(self, title: str) -> QGroupBox:
        g = QGroupBox(title)
        g.setLayout(QFormLayout())
        self.form_root.addWidget(g)
        return g

    def _wrap_row(self, lbl: QLabel, btn: QPushButton) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(lbl, 1)
        h.addWidget(btn)
        return w

    def _mk_font_row(self, handler):
        lbl = QLabel("")
        btn = QPushButton("Choose…")
        btn.clicked.connect(handler)
        return lbl, btn

    def _build_application_group(self):
        g = self._mk_group("Application")

        row = QHBoxLayout()
        self.icon_path = QLineEdit()
        self.btn_browse_icon = QPushButton("Browse…")
        self.btn_browse_icon.clicked.connect(self._browse_icon)
        row.addWidget(self.icon_path, 1)
        row.addWidget(self.btn_browse_icon)

        w = QWidget()
        w.setLayout(row)
        g.layout().addRow("App icon", w)

    def _build_fonts_group(self):
        g = self._mk_group("Fonts (separate per UI area)")

        self.font_base_lbl, self.font_base_btn = self._mk_font_row(self._choose_font_base)
        g.layout().addRow("Base", self._wrap_row(self.font_base_lbl, self.font_base_btn))

        self.font_header_lbl, self.font_header_btn = self._mk_font_row(self._choose_font_header)
        g.layout().addRow("Header", self._wrap_row(self.font_header_lbl, self.font_header_btn))

        self.font_tree_lbl, self.font_tree_btn = self._mk_font_row(self._choose_font_tree)
        g.layout().addRow("Tree/Table", self._wrap_row(self.font_tree_lbl, self.font_tree_btn))

        self.font_button_lbl, self.font_button_btn = self._mk_font_row(self._choose_font_button)
        g.layout().addRow("Buttons", self._wrap_row(self.font_button_lbl, self.font_button_btn))

        self.font_input_lbl, self.font_input_btn = self._mk_font_row(self._choose_font_input)
        g.layout().addRow("Inputs", self._wrap_row(self.font_input_lbl, self.font_input_btn))

        self.font_menu_lbl, self.font_menu_btn = self._mk_font_row(self._choose_font_menu)
        g.layout().addRow("Menus", self._wrap_row(self.font_menu_lbl, self.font_menu_btn))

        self.font_search_lbl, self.font_search_btn = self._mk_font_row(self._choose_font_search)
        g.layout().addRow("Search bar", self._wrap_row(self.font_search_lbl, self.font_search_btn))

    def _build_search_group(self):
        g = self._mk_group("Search bar styling")

        self.search_bg_btn = QPushButton()
        self.search_fg_btn = QPushButton()
        self.search_border_btn = QPushButton()
        self.search_focus_border_btn = QPushButton()
        self.search_placeholder_fg_btn = QPushButton()

        self.search_clear_bg_btn = QPushButton()
        self.search_clear_fg_btn = QPushButton()
        self.search_clear_border_btn = QPushButton()
        self.search_clear_hover_bg_btn = QPushButton()
        self.search_clear_pressed_bg_btn = QPushButton()

        self.search_bg_btn.clicked.connect(lambda: self._color_pick("search_bg", self.search_bg_btn))
        self.search_fg_btn.clicked.connect(lambda: self._color_pick("search_fg", self.search_fg_btn))
        self.search_border_btn.clicked.connect(lambda: self._color_pick("search_border", self.search_border_btn))
        self.search_focus_border_btn.clicked.connect(lambda: self._color_pick("search_focus_border", self.search_focus_border_btn))
        self.search_placeholder_fg_btn.clicked.connect(lambda: self._color_pick("search_placeholder_fg", self.search_placeholder_fg_btn))

        self.search_clear_bg_btn.clicked.connect(lambda: self._color_pick("search_clear_bg", self.search_clear_bg_btn))
        self.search_clear_fg_btn.clicked.connect(lambda: self._color_pick("search_clear_fg", self.search_clear_fg_btn))
        self.search_clear_border_btn.clicked.connect(lambda: self._color_pick("search_clear_border", self.search_clear_border_btn))
        self.search_clear_hover_bg_btn.clicked.connect(lambda: self._color_pick("search_clear_hover_bg", self.search_clear_hover_bg_btn))
        self.search_clear_pressed_bg_btn.clicked.connect(lambda: self._color_pick("search_clear_pressed_bg", self.search_clear_pressed_bg_btn))

        g.layout().addRow("Bar background", self.search_bg_btn)
        g.layout().addRow("Bar text", self.search_fg_btn)
        g.layout().addRow("Bar border", self.search_border_btn)
        g.layout().addRow("Bar focus border", self.search_focus_border_btn)
        g.layout().addRow("Placeholder text", self.search_placeholder_fg_btn)

        g.layout().addRow("Clear button background", self.search_clear_bg_btn)
        g.layout().addRow("Clear button text", self.search_clear_fg_btn)
        g.layout().addRow("Clear button border", self.search_clear_border_btn)
        g.layout().addRow("Clear hover background", self.search_clear_hover_bg_btn)
        g.layout().addRow("Clear pressed background", self.search_clear_pressed_bg_btn)

    # ✅ NEW group
    def _build_row_action_buttons_group(self):
        g = self._mk_group("Row action buttons (+ / -)")

        self.row_add_bg_btn = QPushButton()
        self.row_add_fg_btn = QPushButton()
        self.row_add_border_btn = QPushButton()
        self.row_add_hover_bg_btn = QPushButton()
        self.row_add_pressed_bg_btn = QPushButton()

        self.row_del_bg_btn = QPushButton()
        self.row_del_fg_btn = QPushButton()
        self.row_del_border_btn = QPushButton()
        self.row_del_hover_bg_btn = QPushButton()
        self.row_del_pressed_bg_btn = QPushButton()

        self.row_add_bg_btn.clicked.connect(lambda: self._color_pick("row_add_bg", self.row_add_bg_btn))
        self.row_add_fg_btn.clicked.connect(lambda: self._color_pick("row_add_fg", self.row_add_fg_btn))
        self.row_add_border_btn.clicked.connect(lambda: self._color_pick("row_add_border", self.row_add_border_btn))
        self.row_add_hover_bg_btn.clicked.connect(lambda: self._color_pick("row_add_hover_bg", self.row_add_hover_bg_btn))
        self.row_add_pressed_bg_btn.clicked.connect(lambda: self._color_pick("row_add_pressed_bg", self.row_add_pressed_bg_btn))

        self.row_del_bg_btn.clicked.connect(lambda: self._color_pick("row_del_bg", self.row_del_bg_btn))
        self.row_del_fg_btn.clicked.connect(lambda: self._color_pick("row_del_fg", self.row_del_fg_btn))
        self.row_del_border_btn.clicked.connect(lambda: self._color_pick("row_del_border", self.row_del_border_btn))
        self.row_del_hover_bg_btn.clicked.connect(lambda: self._color_pick("row_del_hover_bg", self.row_del_hover_bg_btn))
        self.row_del_pressed_bg_btn.clicked.connect(lambda: self._color_pick("row_del_pressed_bg", self.row_del_pressed_bg_btn))

        g.layout().addRow("Add (+) background", self.row_add_bg_btn)
        g.layout().addRow("Add (+) text", self.row_add_fg_btn)
        g.layout().addRow("Add (+) border", self.row_add_border_btn)
        g.layout().addRow("Add (+) hover bg", self.row_add_hover_bg_btn)
        g.layout().addRow("Add (+) pressed bg", self.row_add_pressed_bg_btn)

        g.layout().addRow("Delete (–) background", self.row_del_bg_btn)
        g.layout().addRow("Delete (–) text", self.row_del_fg_btn)
        g.layout().addRow("Delete (–) border", self.row_del_border_btn)
        g.layout().addRow("Delete (–) hover bg", self.row_del_hover_bg_btn)
        g.layout().addRow("Delete (–) pressed bg", self.row_del_pressed_bg_btn)

    # (rest of your existing SettingsDialog methods are unchanged below)
    # ---------- Existing groups ----------
    def _build_window_group(self):
        g = self._mk_group("Window & general colors")
        self.window_bg_btn = QPushButton()
        self.window_fg_btn = QPushButton()
        self.window_bg_btn.clicked.connect(lambda: self._color_pick("window_bg", self.window_bg_btn))
        self.window_fg_btn.clicked.connect(lambda: self._color_pick("window_fg", self.window_fg_btn))
        g.layout().addRow("Window background", self.window_bg_btn)
        g.layout().addRow("Text color", self.window_fg_btn)

    def _build_menus_toolbar_group(self):
        g = self._mk_group("Menus & toolbar colors")
        self.menubar_bg_btn = QPushButton()
        self.menu_bg_btn = QPushButton()
        self.menu_fg_btn = QPushButton()
        self.menu_border_btn = QPushButton()
        self.toolbar_bg_btn = QPushButton()
        self.toolbar_border_btn = QPushButton()

        self.menubar_bg_btn.clicked.connect(lambda: self._color_pick("menubar_bg", self.menubar_bg_btn))
        self.menu_bg_btn.clicked.connect(lambda: self._color_pick("menu_bg", self.menu_bg_btn))
        self.menu_fg_btn.clicked.connect(lambda: self._color_pick("menu_fg", self.menu_fg_btn))
        self.menu_border_btn.clicked.connect(lambda: self._color_pick("menu_border", self.menu_border_btn))
        self.toolbar_bg_btn.clicked.connect(lambda: self._color_pick("toolbar_bg", self.toolbar_bg_btn))
        self.toolbar_border_btn.clicked.connect(lambda: self._color_pick("toolbar_border", self.toolbar_border_btn))

        g.layout().addRow("Menu bar background", self.menubar_bg_btn)
        g.layout().addRow("Menu background", self.menu_bg_btn)
        g.layout().addRow("Menu text", self.menu_fg_btn)
        g.layout().addRow("Menu border", self.menu_border_btn)
        g.layout().addRow("Toolbar background", self.toolbar_bg_btn)
        g.layout().addRow("Toolbar border", self.toolbar_border_btn)

    def _build_header_group(self):
        g = self._mk_group("Header (table header) colors")
        self.header_bg_btn = QPushButton()
        self.header_fg_btn = QPushButton()
        self.header_border_btn = QPushButton()
        self.header_bg_btn.clicked.connect(lambda: self._color_pick("header_bg", self.header_bg_btn))
        self.header_fg_btn.clicked.connect(lambda: self._color_pick("header_fg", self.header_fg_btn))
        self.header_border_btn.clicked.connect(lambda: self._color_pick("header_border", self.header_border_btn))
        g.layout().addRow("Header background", self.header_bg_btn)
        g.layout().addRow("Header text", self.header_fg_btn)
        g.layout().addRow("Header border", self.header_border_btn)

    def _build_tree_group(self):
        g = self._mk_group("Tree/Table colors")
        self.tree_bg_btn = QPushButton()
        self.tree_alt_bg_btn = QPushButton()
        self.tree_fg_btn = QPushButton()
        self.grid_btn = QPushButton()

        self.tree_bg_btn.clicked.connect(lambda: self._color_pick("tree_bg", self.tree_bg_btn))
        self.tree_alt_bg_btn.clicked.connect(lambda: self._color_pick("tree_alt_bg", self.tree_alt_bg_btn))
        self.tree_fg_btn.clicked.connect(lambda: self._color_pick("tree_fg", self.tree_fg_btn))
        self.grid_btn.clicked.connect(lambda: self._color_pick("grid", self.grid_btn))

        g.layout().addRow("Background", self.tree_bg_btn)
        g.layout().addRow("Alternate row background", self.tree_alt_bg_btn)
        g.layout().addRow("Text", self.tree_fg_btn)
        g.layout().addRow("Gridlines", self.grid_btn)

    def _build_buttons_group(self):
        g = self._mk_group("Buttons colors")
        self.btn_bg_btn = QPushButton()
        self.btn_fg_btn = QPushButton()
        self.btn_border_btn = QPushButton()
        self.btn_hover_bg_btn = QPushButton()
        self.btn_pressed_bg_btn = QPushButton()
        self.btn_disabled_bg_btn = QPushButton()
        self.btn_disabled_fg_btn = QPushButton()

        self.btn_bg_btn.clicked.connect(lambda: self._color_pick("btn_bg", self.btn_bg_btn))
        self.btn_fg_btn.clicked.connect(lambda: self._color_pick("btn_fg", self.btn_fg_btn))
        self.btn_border_btn.clicked.connect(lambda: self._color_pick("btn_border", self.btn_border_btn))
        self.btn_hover_bg_btn.clicked.connect(lambda: self._color_pick("btn_hover_bg", self.btn_hover_bg_btn))
        self.btn_pressed_bg_btn.clicked.connect(lambda: self._color_pick("btn_pressed_bg", self.btn_pressed_bg_btn))
        self.btn_disabled_bg_btn.clicked.connect(lambda: self._color_pick("btn_disabled_bg", self.btn_disabled_bg_btn))
        self.btn_disabled_fg_btn.clicked.connect(lambda: self._color_pick("btn_disabled_fg", self.btn_disabled_fg_btn))

        g.layout().addRow("Background", self.btn_bg_btn)
        g.layout().addRow("Text", self.btn_fg_btn)
        g.layout().addRow("Border", self.btn_border_btn)
        g.layout().addRow("Hover background", self.btn_hover_bg_btn)
        g.layout().addRow("Pressed background", self.btn_pressed_bg_btn)
        g.layout().addRow("Disabled background", self.btn_disabled_bg_btn)
        g.layout().addRow("Disabled text", self.btn_disabled_fg_btn)

    def _build_inputs_group(self):
        g = self._mk_group("Inputs (editors) colors")
        self.input_bg_btn = QPushButton()
        self.input_fg_btn = QPushButton()
        self.input_border_btn = QPushButton()
        self.input_focus_border_btn = QPushButton()

        self.input_bg_btn.clicked.connect(lambda: self._color_pick("input_bg", self.input_bg_btn))
        self.input_fg_btn.clicked.connect(lambda: self._color_pick("input_fg", self.input_fg_btn))
        self.input_border_btn.clicked.connect(lambda: self._color_pick("input_border", self.input_border_btn))
        self.input_focus_border_btn.clicked.connect(lambda: self._color_pick("input_focus_border", self.input_focus_border_btn))

        g.layout().addRow("Background", self.input_bg_btn)
        g.layout().addRow("Text", self.input_fg_btn)
        g.layout().addRow("Border", self.input_border_btn)
        g.layout().addRow("Focus border", self.input_focus_border_btn)

    def _build_selection_group(self):
        g = self._mk_group("Selection colors")
        self.sel_bg_btn = QPushButton()
        self.sel_fg_btn = QPushButton()
        self.sel_bg_btn.clicked.connect(lambda: self._color_pick("sel_bg", self.sel_bg_btn))
        self.sel_fg_btn.clicked.connect(lambda: self._color_pick("sel_fg", self.sel_fg_btn))
        g.layout().addRow("Selection background", self.sel_bg_btn)
        g.layout().addRow("Selection text", self.sel_fg_btn)

    def _build_advanced_group(self):
        g = self._mk_group("Advanced")
        self.custom_qss = QPlainTextEdit()
        self.custom_qss.setPlaceholderText(
            "Optional: add custom Qt StyleSheet (QSS) here.\n"
            "This is appended after the generated theme QSS, so it can override anything.\n"
        )
        g.layout().addRow("Custom QSS override", self.custom_qss)

    # ---------- Theme load/save ----------
    def _on_theme_selected(self, name: str):
        if not name:
            return
        self._theme_name = name
        self._theme = self.tm.load_theme(name)
        self._load_theme_into_controls()

    def _new_theme(self):
        name, ok = QInputDialog.getText(self, "New theme", "Theme name:")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return

        self.tm.duplicate_theme(self._theme_name, name)
        self.theme_combo.clear()
        self.theme_combo.addItems(self.tm.list_themes())
        self.theme_combo.setCurrentText(name)

    def _save_theme(self):
        self._pull_controls_into_theme()
        self.tm.save_theme(self._theme_name, self._theme)
        self.tm.set_current_theme(self._theme_name)

    def _save_as_theme(self):
        name, ok = QInputDialog.getText(self, "Save theme as", "New theme name:")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        self._pull_controls_into_theme()
        self.tm.save_theme(name, self._theme)
        self.tm.set_current_theme(name)

        self.theme_combo.clear()
        self.theme_combo.addItems(self.tm.list_themes())
        self.theme_combo.setCurrentText(name)

    def _delete_theme(self):
        name = self._theme_name
        if len(self.tm.list_themes()) <= 1:
            QMessageBox.information(self, "Not possible", "At least one theme must remain.")
            return

        res = QMessageBox.question(self, "Delete theme", f"Delete theme '{name}'?")
        if res != QMessageBox.StandardButton.Yes:
            return

        self.tm.delete_theme(name)
        self.theme_combo.clear()
        self.theme_combo.addItems(self.tm.list_themes())
        self.theme_combo.setCurrentText(self.tm.current_theme_name())

    def _ok(self):
        self._save_theme()
        self.accept()

    # ---------- Controls <-> theme dict ----------
    def _load_theme_into_controls(self):
        d = default_theme_dict()
        t = d
        t.update(self._theme)
        t["fonts"].update(self._theme.get("fonts", {}))
        t["colors"].update(self._theme.get("colors", {}))
        self._theme = t

        self.icon_path.setText(self._theme.get("app_icon_path", ""))

        self._update_font_labels()

        c = self._theme["colors"]

        _set_color_btn(self.search_bg_btn, c["search_bg"])
        _set_color_btn(self.search_fg_btn, c["search_fg"])
        _set_color_btn(self.search_border_btn, c["search_border"])
        _set_color_btn(self.search_focus_border_btn, c["search_focus_border"])
        _set_color_btn(self.search_placeholder_fg_btn, c["search_placeholder_fg"])

        _set_color_btn(self.search_clear_bg_btn, c["search_clear_bg"])
        _set_color_btn(self.search_clear_fg_btn, c["search_clear_fg"])
        _set_color_btn(self.search_clear_border_btn, c["search_clear_border"])
        _set_color_btn(self.search_clear_hover_bg_btn, c["search_clear_hover_bg"])
        _set_color_btn(self.search_clear_pressed_bg_btn, c["search_clear_pressed_bg"])

        # ✅ NEW: load row button colours
        _set_color_btn(self.row_add_bg_btn, c["row_add_bg"])
        _set_color_btn(self.row_add_fg_btn, c["row_add_fg"])
        _set_color_btn(self.row_add_border_btn, c["row_add_border"])
        _set_color_btn(self.row_add_hover_bg_btn, c["row_add_hover_bg"])
        _set_color_btn(self.row_add_pressed_bg_btn, c["row_add_pressed_bg"])

        _set_color_btn(self.row_del_bg_btn, c["row_del_bg"])
        _set_color_btn(self.row_del_fg_btn, c["row_del_fg"])
        _set_color_btn(self.row_del_border_btn, c["row_del_border"])
        _set_color_btn(self.row_del_hover_bg_btn, c["row_del_hover_bg"])
        _set_color_btn(self.row_del_pressed_bg_btn, c["row_del_pressed_bg"])

        _set_color_btn(self.window_bg_btn, c["window_bg"])
        _set_color_btn(self.window_fg_btn, c["window_fg"])

        _set_color_btn(self.menubar_bg_btn, c["menubar_bg"])
        _set_color_btn(self.menu_bg_btn, c["menu_bg"])
        _set_color_btn(self.menu_fg_btn, c["menu_fg"])
        _set_color_btn(self.menu_border_btn, c["menu_border"])
        _set_color_btn(self.toolbar_bg_btn, c["toolbar_bg"])
        _set_color_btn(self.toolbar_border_btn, c["toolbar_border"])

        _set_color_btn(self.header_bg_btn, c["header_bg"])
        _set_color_btn(self.header_fg_btn, c["header_fg"])
        _set_color_btn(self.header_border_btn, c["header_border"])

        _set_color_btn(self.tree_bg_btn, c["tree_bg"])
        _set_color_btn(self.tree_alt_bg_btn, c["tree_alt_bg"])
        _set_color_btn(self.tree_fg_btn, c["tree_fg"])
        _set_color_btn(self.grid_btn, c["grid"])

        _set_color_btn(self.btn_bg_btn, c["btn_bg"])
        _set_color_btn(self.btn_fg_btn, c["btn_fg"])
        _set_color_btn(self.btn_border_btn, c["btn_border"])
        _set_color_btn(self.btn_hover_bg_btn, c["btn_hover_bg"])
        _set_color_btn(self.btn_pressed_bg_btn, c["btn_pressed_bg"])
        _set_color_btn(self.btn_disabled_bg_btn, c["btn_disabled_bg"])
        _set_color_btn(self.btn_disabled_fg_btn, c["btn_disabled_fg"])

        _set_color_btn(self.input_bg_btn, c["input_bg"])
        _set_color_btn(self.input_fg_btn, c["input_fg"])
        _set_color_btn(self.input_border_btn, c["input_border"])
        _set_color_btn(self.input_focus_border_btn, c["input_focus_border"])

        _set_color_btn(self.sel_bg_btn, c["sel_bg"])
        _set_color_btn(self.sel_fg_btn, c["sel_fg"])

        self.custom_qss.setPlainText(self._theme.get("custom_qss", ""))

    def _pull_controls_into_theme(self):
        self._theme["app_icon_path"] = self.icon_path.text().strip()
        self._theme["custom_qss"] = self.custom_qss.toPlainText()

    def _color_pick(self, key: str, btn: QPushButton):
        chosen = QColorDialog.getColor(parent=self)
        if chosen.isValid():
            self._theme["colors"][key] = chosen.name()
            _set_color_btn(btn, chosen.name())

    # ---------- Icon ----------
    def _browse_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose application icon",
            "",
            "Icons (*.ico *.png *.jpg *.jpeg *.bmp);;All files (*.*)",
        )
        if path:
            self.icon_path.setText(path)

    # ---------- Fonts ----------
    def _update_font_labels(self):
        from theme import _font_from_str

        base = _font_from_str(self._theme["fonts"].get("base", ""), QFont("Segoe UI", 10))
        header = _font_from_str(self._theme["fonts"].get("header", ""), base)
        tree = _font_from_str(self._theme["fonts"].get("tree", ""), base)
        button = _font_from_str(self._theme["fonts"].get("button", ""), base)
        input_f = _font_from_str(self._theme["fonts"].get("input", ""), base)
        menu = _font_from_str(self._theme["fonts"].get("menu", ""), base)
        search = _font_from_str(self._theme["fonts"].get("search", ""), input_f)

        self.font_base_lbl.setText(_font_label(base))
        self.font_header_lbl.setText(_font_label(header))
        self.font_tree_lbl.setText(_font_label(tree))
        self.font_button_lbl.setText(_font_label(button))
        self.font_input_lbl.setText(_font_label(input_f))
        self.font_menu_lbl.setText(_font_label(menu))
        self.font_search_lbl.setText(_font_label(search))

    def _choose_font_base(self):
        self._choose_font("base", QFont("Segoe UI", 10))

    def _choose_font_header(self):
        self._choose_font("header", QFont("Segoe UI", 10, QFont.Weight.DemiBold))

    def _choose_font_tree(self):
        self._choose_font("tree", QFont("Segoe UI", 10))

    def _choose_font_button(self):
        self._choose_font("button", QFont("Segoe UI", 10, QFont.Weight.Medium))

    def _choose_font_input(self):
        self._choose_font("input", QFont("Segoe UI", 10))

    def _choose_font_menu(self):
        self._choose_font("menu", QFont("Segoe UI", 10))

    def _choose_font_search(self):
        self._choose_font("search", QFont("Segoe UI", 10, QFont.Weight.Medium))

    def _choose_font(self, slot: str, fallback: QFont):
        from theme import _font_from_str, _font_to_str

        current = _font_from_str(self._theme["fonts"].get(slot, ""), fallback)
        ok, font = QFontDialog.getFont(current, self, f"Choose font ({slot})")
        if ok:
            self._theme["fonts"][slot] = _font_to_str(font)
            self._update_font_labels()