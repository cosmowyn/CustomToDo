import sys

# --- PyInstaller splash: close it ASAP (safe when not built with --splash) ---
try:
    import pyi_splash  # type: ignore
    pyi_splash.close()
except Exception:
    pass

from PySide6.QtCore import Qt, QTimer, QModelIndex, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeView, QPushButton, QToolBar, QMenu, QMessageBox,
    QLineEdit, QDockWidget, QLabel, QToolButton
)

from app_paths import app_db_path
from db import Database
from model import TaskTreeModel, STATUSES
from delegates import install_delegates
from settings_ui import SettingsDialog
from columns_ui import AddColumnDialog, RemoveColumnDialog
from filter_proxy import TaskFilterProxyModel
from filters_ui import FilterPanel

from backup_io import export_backup_ui, import_backup_ui
from theme_io import export_themes_ui, import_themes_ui


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CustomTaskManager")

        self.db = Database(app_db_path())

        # Source model (full tree)
        self.model = TaskTreeModel(self.db)
        self.undo_stack = self.model.undo_stack

        # Apply theme early so palette + fonts are correct
        self.model.apply_theme_to_app(QApplication.instance())
        icon = self.model.current_window_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        # Proxy (search + filters)
        self.proxy = TaskFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self._pending_edit_on_insert = False
        self.model.rowsInserted.connect(self._on_source_rows_inserted)

        # View
        self.view = QTreeView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.setUniformRowHeights(False)

        hdr = self.view.header()
        hdr.setSectionsMovable(True)
        hdr.setStretchLastSection(True)

        self.view.setRootIsDecorated(True)
        self.view.setItemsExpandable(True)
        self.view.setExpandsOnDoubleClick(True)
        self._row_action_gutter = 72

        # Default drag/drop enabled (will be disabled automatically when filters active)
        self._set_dragdrop_enabled(True)

        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._open_context_menu)

        # Persist collapse state (map proxy -> source)
        self._applying_expand_state = False
        self.view.collapsed.connect(self._on_collapsed)
        self.view.expanded.connect(self._on_expanded)

        install_delegates(self.view, self.proxy)

        # --- Search bar (above the view)
        self.search = QLineEdit()
        self.search.setObjectName("SearchBar")
        self.search.setPlaceholderText("Search… (Ctrl+F)")
        self.search.textChanged.connect(self._on_search_changed)

        clear_btn = QToolButton()
        clear_btn.setObjectName("SearchClear")
        clear_btn.setText("✕")
        clear_btn.setToolTip("Clear search")
        clear_btn.clicked.connect(lambda: self.search.setText(""))

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        search_row.addWidget(self.search, 1)
        search_row.addWidget(clear_btn)

        add_btn = QPushButton("Add task")
        add_btn.clicked.connect(self._add_task_and_edit)

        # Layout
        main = QWidget()
        v = QVBoxLayout(main)
        v.addLayout(search_row)

        self._row_gutter = QWidget()
        self._row_gutter.setObjectName("RowActionGutter")
        self._row_gutter.setFixedWidth(self._row_action_gutter)

        tree_row = QHBoxLayout()
        tree_row.setContentsMargins(0, 0, 0, 0)
        tree_row.setSpacing(0)
        tree_row.addWidget(self._row_gutter)
        tree_row.addWidget(self.view, 1)

        tree_wrap = QWidget()
        tree_wrap.setLayout(tree_row)
        v.addWidget(tree_wrap, 1)

        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(add_btn)
        v.addLayout(h)

        self.setCentralWidget(main)

        # --- Row overlay buttons (+ / -) ---
        self.row_add_btn = QToolButton(self._row_gutter)
        self.row_add_btn.setObjectName("RowAddChildButton")
        self.row_add_btn.setText("+")
        self.row_add_btn.setToolTip("Add child task to this row")
        self.row_add_btn.clicked.connect(self._row_add_child_clicked)
        self.row_add_btn.hide()

        self.row_del_btn = QToolButton(self._row_gutter)
        self.row_del_btn.setObjectName("RowDeleteButton")
        self.row_del_btn.setText("–")
        self.row_del_btn.setToolTip("Delete this task")
        self.row_del_btn.clicked.connect(self._row_delete_clicked)
        self.row_del_btn.hide()

        self.view.selectionModel().currentChanged.connect(lambda *_: self._update_row_action_buttons())
        self.view.verticalScrollBar().valueChanged.connect(lambda *_: self._update_row_action_buttons())
        self.view.horizontalScrollBar().valueChanged.connect(lambda *_: self._update_row_action_buttons())
        self.view.header().geometriesChanged.connect(lambda: self._update_row_action_buttons())
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)

        # Advanced filter panel (dock)
        self._init_filter_dock()

        self._build_menus_and_toolbar()
        self._restore_ui_settings()

        self.model.modelReset.connect(self._apply_collapsed_state_to_view)
        self.proxy.modelReset.connect(self._apply_collapsed_state_to_view)

        # Timer to refresh due-date gradient + foreground contrast
        self._due_timer = QTimer(self)
        self._due_timer.setInterval(60_000)
        self._due_timer.timeout.connect(self.model.refresh_due_highlights)
        self._due_timer.start()

        self.model.refresh_due_highlights()

        # Shortcut: focus search
        focus_search = QAction(self)
        focus_search.setShortcut(QKeySequence(Qt.CTRL | Qt.Key.Key_F))
        focus_search.triggered.connect(lambda: self.search.setFocus())
        self.addAction(focus_search)

        QTimer.singleShot(0, self._update_row_action_buttons)

    # ---------- Splash (close again once UI shows) ----------
    def showEvent(self, event):
        super().showEvent(event)
        try:
            import pyi_splash  # type: ignore
            pyi_splash.close()
        except Exception:
            pass

    # ---------- Event filter for overlay alignment ----------
    def eventFilter(self, obj, event):
        if obj in (self.view.viewport(), self.view):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Wheel, QEvent.Type.Move, QEvent.Type.Show):
                QTimer.singleShot(0, self._update_row_action_buttons)
        return super().eventFilter(obj, event)

    def _row_button_size(self) -> int:
        h = self.view.fontMetrics().height()
        return max(18, min(28, h + 6))

    def _update_row_action_buttons(self):
        idx = self.view.currentIndex()
        if not idx.isValid():
            self.row_add_btn.hide()
            self.row_del_btn.hide()
            return

        idx0 = idx.siblingAtColumn(0)
        rect = self.view.visualRect(idx0)
        vp_rect = self.view.viewport().rect()

        if rect.isNull() or rect.height() <= 0 or not rect.intersects(vp_rect):
            self.row_add_btn.hide()
            self.row_del_btn.hide()
            return

        size = self._row_button_size()
        gap = 6
        required_gutter = (2 * size) + gap + 8
        if self._row_action_gutter < required_gutter:
            self._row_action_gutter = required_gutter
            self._row_gutter.setFixedWidth(self._row_action_gutter)
        gutter_w = self._row_gutter.width()

        self.row_add_btn.setFixedSize(size, size)
        self.row_del_btn.setFixedSize(size, size)

        src_idx0 = self.proxy.mapToSource(idx0)
        task_id = self.model.task_id_from_index(src_idx0)
        can_add_child = task_id is not None and self.model.can_add_child_task(task_id)
        self.row_add_btn.setEnabled(can_add_child)
        if can_add_child:
            self.row_add_btn.setToolTip("Add child task to this row")
        else:
            self.row_add_btn.setToolTip(
                f"Max nesting depth ({self.model.max_nesting_levels()}) reached for this branch"
            )

        # center two buttons within the dedicated left gutter
        x_add = max(4, (gutter_w - ((2 * size) + gap)) // 2)
        x_del = x_add + size + gap

        center_global = self.view.viewport().mapToGlobal(rect.center())
        center_in_gutter = self._row_gutter.mapFromGlobal(center_global)
        y = center_in_gutter.y() - (size // 2)
        y = max(0, min(self._row_gutter.height() - size, y))

        self.row_add_btn.move(x_add, y)
        self.row_del_btn.move(x_del, y)

        self.row_add_btn.show()
        self.row_del_btn.show()
        self.row_add_btn.raise_()
        self.row_del_btn.raise_()
        
    def _row_add_child_clicked(self):
        pidx = self.view.currentIndex()
        if not pidx.isValid():
            return
        src = self.proxy.mapToSource(pidx)
        task_id = self.model.task_id_from_index(src)
        if task_id is None:
            return
        self.view.expand(pidx)
        if not self.model.add_child_task(task_id):
            self._pending_edit_on_insert = False
            self._show_nesting_limit_message()
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _row_delete_clicked(self):
        self._delete_selected()
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _request_edit_after_insert(self):
        self._pending_edit_on_insert = True

    def _show_nesting_limit_message(self):
        max_depth = self.model.max_nesting_levels()
        QMessageBox.information(
            self,
            "Nesting limit reached",
            f"A branch can be nested at most {max_depth} levels below a top-level parent.",
        )

    def _on_source_rows_inserted(self, parent: QModelIndex, first: int, last: int):
        if not self._pending_edit_on_insert:
            return

        self._pending_edit_on_insert = False

        # Focus the first column of the last inserted row
        src_idx = self.model.index(last, 0, parent)
        if not src_idx.isValid():
            return

        proxy_idx = self.proxy.mapFromSource(src_idx)
        if not proxy_idx.isValid():
            return

        # Ensure visible and selected
        if parent.isValid():
            parent_proxy = self.proxy.mapFromSource(parent)
            if parent_proxy.isValid():
                self.view.expand(parent_proxy)

        self.view.setCurrentIndex(proxy_idx)
        self.view.scrollTo(proxy_idx)

        QTimer.singleShot(0, lambda: self.view.edit(proxy_idx))

    def _add_task_and_edit(self):
        self._request_edit_after_insert()
        if not self.model.add_task(parent_id=None):
            self._pending_edit_on_insert = False

    def _delete_sibling_of_selected(self):
        pidx = self._selected_proxy_index()
        if not pidx:
            return

        src = self.proxy.mapToSource(pidx)
        if not src.isValid():
            return

        parent_src = src.parent()
        row = src.row()

        sibling_src = QModelIndex()

        # Prefer next sibling, else previous sibling
        next_row = row + 1
        if self.model.rowCount(parent_src) > next_row:
            sibling_src = self.model.index(next_row, 0, parent_src)
        elif row - 1 >= 0:
            sibling_src = self.model.index(row - 1, 0, parent_src)

        if not sibling_src.isValid():
            return

        task_id = self.model.task_id_from_index(sibling_src)
        if task_id is None:
            return

        self.model.delete_task(task_id)
        QTimer.singleShot(0, self._update_row_action_buttons)

    # ---------- Filters ----------
    def _init_filter_dock(self):
        self.filter_panel = FilterPanel(STATUSES, self)
        self.filter_panel.changed.connect(self._apply_filters)

        self.filter_dock = QDockWidget("Filters", self)
        self.filter_dock.setObjectName("FiltersDock")
        self.filter_dock.setWidget(self.filter_panel)
        self.filter_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.filter_dock)
        self.filter_dock.hide()

    def _on_search_changed(self, text: str):
        self.proxy.set_search_text(text)
        self._update_dragdrop_mode()
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _apply_filters(self):
        statuses = self.filter_panel.status_allowed()
        pmin, pmax = self.filter_panel.priority_range()
        dfrom, dto = self.filter_panel.due_range()

        self.proxy.set_status_allowed(statuses)
        self.proxy.set_priority_range(pmin, pmax)
        self.proxy.set_due_range(dfrom, dto)
        self.proxy.set_hide_done(self.filter_panel.hide_done())
        self.proxy.set_overdue_only(self.filter_panel.overdue_only())
        self.proxy.set_show_children_of_matches(self.filter_panel.show_children_of_matches())

        self._update_dragdrop_mode()
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _update_dragdrop_mode(self):
        active = self.proxy.is_filter_active()
        self._set_dragdrop_enabled(not active)

    def _set_dragdrop_enabled(self, enabled: bool):
        if enabled:
            self.view.setDragEnabled(True)
            self.view.setAcceptDrops(True)
            self.view.setDropIndicatorShown(True)
            self.view.setDragDropMode(QTreeView.DragDropMode.InternalMove)
            self.view.setDefaultDropAction(Qt.DropAction.MoveAction)
        else:
            self.view.setDragEnabled(False)
            self.view.setAcceptDrops(False)
            self.view.setDropIndicatorShown(False)
            self.view.setDragDropMode(QTreeView.DragDropMode.NoDragDrop)

    # ---------- Menus / toolbar ----------
    def _build_menus_and_toolbar(self):
        undo_act = QAction("Undo", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self.undo_stack.undo)

        redo_act = QAction("Redo", self)
        redo_act.setShortcut(QKeySequence.StandardKey.Redo)
        redo_act.triggered.connect(self.undo_stack.redo)

        add_act = QAction("Add task", self)
        add_act.setShortcut(QKeySequence(Qt.CTRL | Qt.Key.Key_N))
        add_act.triggered.connect(self._add_task_and_edit)

        add_child_act = QAction("Add child task", self)
        add_child_act.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key.Key_N))
        add_child_act.triggered.connect(self._add_child_to_selected)

        del_act = QAction("Delete task", self)
        del_act.setShortcut(QKeySequence.StandardKey.Delete)
        del_act.triggered.connect(self._delete_selected)

        settings_act = QAction("Settings & Themes…", self)
        settings_act.triggered.connect(self._open_settings)

        toggle_filters_act = QAction("Filters panel", self)
        toggle_filters_act.setCheckable(True)
        toggle_filters_act.setChecked(False)
        toggle_filters_act.triggered.connect(self._toggle_filters_dock)

        collapse_all_act = QAction("Collapse all", self)
        collapse_all_act.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key.Key_Up))
        collapse_all_act.triggered.connect(self._collapse_all)

        expand_all_act = QAction("Expand all", self)
        expand_all_act.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key.Key_Down))
        expand_all_act.triggered.connect(self._expand_all)

        menubar = self.menuBar()

        m_file = menubar.addMenu("File")
        m_file.addAction(settings_act)

        # Backup submenu (data + themes)
        m_backup = m_file.addMenu("Backup")

        export_db_act = QAction("Export Data…", self)
        export_db_act.triggered.connect(lambda: export_backup_ui(self, self.db))
        m_backup.addAction(export_db_act)

        import_db_act = QAction("Import Data…", self)
        import_db_act.triggered.connect(lambda: import_backup_ui(self))
        m_backup.addAction(import_db_act)

        m_backup.addSeparator()

        export_theme_act = QAction("Export Themes…", self)
        export_theme_act.triggered.connect(lambda: export_themes_ui(self, self.model.settings))
        m_backup.addAction(export_theme_act)

        import_theme_act = QAction("Import Themes…", self)
        import_theme_act.triggered.connect(
            lambda: import_themes_ui(
                self,
                self.model.settings,
                apply_callback=lambda: self._apply_theme_now(),
            )
        )
        m_backup.addAction(import_theme_act)

        m_file.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        m_file.addAction(exit_act)

        m_edit = menubar.addMenu("Edit")
        m_edit.addAction(undo_act)
        m_edit.addAction(redo_act)
        m_edit.addSeparator()
        m_edit.addAction(add_act)
        m_edit.addAction(add_child_act)
        m_edit.addAction(del_act)

        m_view = menubar.addMenu("View")
        m_view.addAction(toggle_filters_act)
        m_view.addSeparator()
        m_view.addAction(collapse_all_act)
        m_view.addAction(expand_all_act)

        self.m_columns = menubar.addMenu("Columns")
        self.m_columns.aboutToShow.connect(self._rebuild_columns_menu)
        # macOS: empty menus sometimes don't show; build once now
        self._rebuild_columns_menu()

        tb = QToolBar("Main", self)
        self.addToolBar(tb)
        tb.addAction(add_act)
        tb.addAction(add_child_act)
        tb.addSeparator()
        tb.addAction(undo_act)
        tb.addAction(redo_act)

        self._toggle_filters_act = toggle_filters_act

        add_shortcut_act = QAction(self)
        add_shortcut_act.setShortcut(QKeySequence("+"))
        add_shortcut_act.triggered.connect(self._add_task_and_edit)
        self.addAction(add_shortcut_act)

        remove_shortcut_act = QAction(self)
        remove_shortcut_act.setShortcut(QKeySequence("-"))
        remove_shortcut_act.triggered.connect(self._delete_selected)
        self.addAction(remove_shortcut_act)

        add_child_shortcut_act = QAction(self)
        add_child_shortcut_act.setShortcut(QKeySequence("Shift++"))
        add_child_shortcut_act.triggered.connect(self._add_child_to_selected)
        self.addAction(add_child_shortcut_act)

        remove_sibling_shortcut_act = QAction(self)
        remove_sibling_shortcut_act.setShortcut(QKeySequence("Shift+-"))
        remove_sibling_shortcut_act.triggered.connect(self._delete_sibling_of_selected)
        self.addAction(remove_sibling_shortcut_act)

    def _toggle_filters_dock(self, checked: bool):
        if checked:
            self.filter_dock.show()
        else:
            self.filter_dock.hide()
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _rebuild_columns_menu(self):
        self.m_columns.clear()

        # Always include manage actions so menu is never empty
        add_col_act = QAction("Add custom column…", self)
        add_col_act.triggered.connect(self._add_custom_column)

        rem_col_act = QAction("Remove custom column…", self)
        rem_col_act.triggered.connect(self._remove_custom_column)

        self.m_columns.addAction(add_col_act)
        self.m_columns.addAction(rem_col_act)
        self.m_columns.addSeparator()

        for logical in range(self.proxy.columnCount()):
            key = self.model.column_key(logical)
            title = self.proxy.headerData(logical, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)

            act = QAction(str(title), self)
            act.setCheckable(True)
            act.setChecked(not self.view.isColumnHidden(logical))

            def make_toggle(col_index: int, col_key: str):
                def _toggle(checked: bool):
                    self.view.setColumnHidden(col_index, not checked)
                    self.model.settings.setValue(f"columns/hidden/{col_key}", not checked)
                    QTimer.singleShot(0, self._update_row_action_buttons)
                return _toggle

            act.triggered.connect(make_toggle(logical, key))
            self.m_columns.addAction(act)

    # ---------- Expand / collapse all ----------
    def _collapse_all(self):
        self.view.collapseAll()
        for node in self.model.iter_nodes_preorder():
            if node.task:
                self.model.set_collapsed(int(node.task["id"]), True)
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _expand_all(self):
        self.view.expandAll()
        for node in self.model.iter_nodes_preorder():
            if node.task:
                self.model.set_collapsed(int(node.task["id"]), False)
        QTimer.singleShot(0, self._update_row_action_buttons)

    # ---------- Context menu + selection helpers ----------
    def _open_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return

        src = self.proxy.mapToSource(index)
        task_id = self.model.task_id_from_index(src)
        if task_id is None:
            return

        menu = QMenu(self)

        add_child = QAction("Add child task", self)
        add_child.triggered.connect(self._add_child_to_selected)
        menu.addAction(add_child)

        menu.addSeparator()

        del_act = QAction("Delete", self)
        del_act.triggered.connect(self._delete_selected)
        menu.addAction(del_act)

        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _selected_proxy_index(self):
        idx = self.view.currentIndex()
        return idx if idx.isValid() else None

    def _selected_task_id(self):
        pidx = self._selected_proxy_index()
        if not pidx:
            return None
        src = self.proxy.mapToSource(pidx)
        return self.model.task_id_from_index(src)

    def _delete_selected(self):
        task_id = self._selected_task_id()
        if task_id is None:
            return
        self.model.delete_task(task_id)

    def _add_child_to_selected(self):
        pidx = self._selected_proxy_index()
        if not pidx:
            self.model.add_task(parent_id=None)
            return

        src = self.proxy.mapToSource(pidx)
        task_id = self.model.task_id_from_index(src)
        if task_id is None:
            return

        self.view.expand(pidx)
        if not self.model.add_child_task(task_id):
            self._pending_edit_on_insert = False
            self._show_nesting_limit_message()

        QTimer.singleShot(0, self._update_row_action_buttons)

    # ---------- Settings ----------
    def _apply_theme_now(self):
        self.model.apply_theme_to_app(QApplication.instance())
        icon = self.model.current_window_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self.model.refresh_due_highlights()

    def _open_settings(self):
        dlg = SettingsDialog(self.model.settings, self)
        if dlg.exec():
            self._apply_theme_now()
            QTimer.singleShot(0, self._update_row_action_buttons)

    def _add_custom_column(self):
        dlg = AddColumnDialog(self)
        if dlg.exec():
            name, col_type, list_values = dlg.result_value()
            self.model.add_custom_column(name, col_type, list_values)

    def _remove_custom_column(self):
        cols = self.model.custom_columns_snapshot()
        if not cols:
            QMessageBox.information(self, "No custom columns", "There are no custom columns to remove.")
            return

        dlg = RemoveColumnDialog(cols, self)
        if dlg.exec():
            col_id = dlg.selected_column_id()
            if col_id is not None:
                self.model.remove_custom_column(col_id)

    # ---------- Collapse persistence ----------
    def _on_collapsed(self, proxy_index):
        if self._applying_expand_state:
            return
        src = self.proxy.mapToSource(proxy_index)
        task_id = self.model.task_id_from_index(src)
        if task_id is not None:
            self.model.set_collapsed(task_id, True)
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _on_expanded(self, proxy_index):
        if self._applying_expand_state:
            return
        src = self.proxy.mapToSource(proxy_index)
        task_id = self.model.task_id_from_index(src)
        if task_id is not None:
            self.model.set_collapsed(task_id, False)
        QTimer.singleShot(0, self._update_row_action_buttons)

    def _apply_collapsed_state_to_view(self):
        self._applying_expand_state = True
        try:
            for node in self.model.iter_nodes_preorder():
                if not node.task:
                    continue

                src_idx = self._source_index_for_node(node)
                if not src_idx.isValid():
                    continue

                pidx = self.proxy.mapFromSource(src_idx)
                if not pidx.isValid():
                    continue

                collapsed = int(node.task.get("is_collapsed", 0)) == 1
                self.view.setExpanded(pidx, not collapsed)
        finally:
            self._applying_expand_state = False

        QTimer.singleShot(0, self._update_row_action_buttons)

    def _source_index_for_node(self, node):
        if node == self.model.root or node is None or node.task is None or node.parent is None:
            return QModelIndex()

        parent = node.parent
        pidx = self._source_index_for_node(parent)

        row = 0
        for i, ch in enumerate(parent.children):
            if ch is node:
                row = i
                break

        return self.model.index(row, 0, pidx)

    # ---------- Restore / save UI state ----------
    def _restore_ui_settings(self):
        s = self.model.settings

        geo = s.value("ui/geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        win_state = s.value("ui/window_state")
        if win_state is not None:
            self.restoreState(win_state)

        header_state = s.value("ui/header_state")
        if header_state is not None:
            self.view.header().restoreState(header_state)

        for logical in range(self.proxy.columnCount()):
            key = self.model.column_key(logical)
            hidden = s.value(f"columns/hidden/{key}", False, type=bool)
            self.view.setColumnHidden(logical, bool(hidden))

        dock_visible = s.value("ui/filters_dock_visible", False, type=bool)
        self.filter_dock.setVisible(bool(dock_visible))
        self._toggle_filters_act.setChecked(bool(dock_visible))

        self._apply_collapsed_state_to_view()

        QTimer.singleShot(0, self._update_row_action_buttons)

    def closeEvent(self, event):
        s = self.model.settings
        s.setValue("ui/geometry", self.saveGeometry())
        s.setValue("ui/window_state", self.saveState())
        s.setValue("ui/header_state", self.view.header().saveState())
        s.setValue("ui/filters_dock_visible", self.filter_dock.isVisible())
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("FocusTools")
    app.setApplicationName("CustomTaskManager")

    w = MainWindow()
    w.resize(1100, 650)
    w.show()

    # Close splash again after show (covers slow first paint)
    try:
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
