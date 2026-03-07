from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from PySide6.QtCore import (
    Qt, QAbstractItemModel, QModelIndex, QMimeData, QByteArray, QSettings
)
from PySide6.QtGui import QColor, QUndoStack, QIcon

from commands import (
    AddTaskCommand, DeleteSubtreeCommand, EditCellCommand, MoveNodeCommand,
    AddCustomColumnCommand, RemoveCustomColumnCommand
)
from theme import ThemeManager


STATUSES = ["Todo", "In Progress", "Blocked", "Done"]
CUSTOM_TYPES = ["text", "int", "date", "bool", "list"]


def _parse_iso_date(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _today():
    return date.today()


def _clamp(x: float, a: float, b: float) -> float:
    return a if x < a else b if x > b else x


def _lerp(a: int, b: int, t: float) -> int:
    t = _clamp(t, 0.0, 1.0)
    return int(round(a + (b - a) * t))


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        _lerp(c1.red(), c2.red(), t),
        _lerp(c1.green(), c2.green(), t),
        _lerp(c1.blue(), c2.blue(), t),
    )


def _tri_gradient(green: QColor, orange: QColor, red: QColor, t: float) -> QColor:
    t = _clamp(t, 0.0, 1.0)
    if t <= 0.5:
        return _lerp_color(green, orange, t / 0.5)
    return _lerp_color(orange, red, (t - 0.5) / 0.5)


def _best_contrast_text_color(bg: QColor) -> QColor:
    """Return black/white for best readability on a colored background."""
    r, g, b = bg.red(), bg.green(), bg.blue()
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return QColor("#000000") if luminance > 150 else QColor("#FFFFFF")


@dataclass
class _Node:
    task: Optional[dict]
    parent: Optional["_Node"]
    children: list["_Node"]

    def __init__(self, task=None, parent=None):
        self.task = task
        self.parent = parent
        self.children = []


class TaskTreeModel(QAbstractItemModel):
    MAX_NESTING_LEVELS = 10

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.undo_stack = QUndoStack(self)
        self.settings = QSettings()

        self.theme_mgr = ThemeManager(self.settings)
        self._last_applied_icon: QIcon | None = None

        self.core_cols = [
            ("description", "Task description", "text"),
            ("due_date", "Planned due date", "date"),
            ("last_update", "Last update", "datetime"),
            ("priority", "Priority", "int"),
            ("status", "Status", "status"),
        ]

        self.custom_cols = []
        self.root = _Node(task=None, parent=None)
        self._id_map: dict[int, _Node] = {}

        self.reload_all(reset_header_state=False)

    # ---------- Theme ----------
    def apply_theme_to_app(self, app):
        self._last_applied_icon = self.theme_mgr.apply_to_app(app)

    def current_window_icon(self) -> QIcon | None:
        if self._last_applied_icon is not None and not self._last_applied_icon.isNull():
            return self._last_applied_icon
        theme = self.theme_mgr.load_theme(self.theme_mgr.current_theme_name())
        return self.theme_mgr.icon_for_theme(theme)

    # ---------- Load / rebuild ----------
    def reload_all(self, reset_header_state: bool = False):
        self.beginResetModel()
        self.custom_cols = self.db.fetch_custom_columns()
        self._rebuild_tree(self.db.fetch_tasks())
        self.endResetModel()

        if reset_header_state:
            self.settings.remove("ui/header_state")

    def _rebuild_tree(self, tasks: list[dict]):
        self.root = _Node(task=None, parent=None)
        self._id_map = {}

        for t in tasks:
            n = _Node(task=t, parent=None)
            self._id_map[int(t["id"])] = n

        for t in tasks:
            nid = int(t["id"])
            parent_id = t.get("parent_id")
            node = self._id_map[nid]

            if parent_id is None:
                node.parent = self.root
                self.root.children.append(node)
            else:
                p = self._id_map.get(int(parent_id))
                if p is None:
                    node.parent = self.root
                    self.root.children.append(node)
                else:
                    node.parent = p
                    p.children.append(node)

        def sort_children(n: _Node):
            n.children.sort(
                key=lambda x: (
                    int(x.task.get("sort_order", 1)) if x.task else 1,
                    int(x.task.get("id", 0)) if x.task else 0,
                )
            )
            for ch in n.children:
                sort_children(ch)

        sort_children(self.root)

    # ---------- Helpers ----------
    def node_for_id(self, task_id: int) -> Optional[_Node]:
        return self._id_map.get(int(task_id))

    def max_nesting_levels(self) -> int:
        return self.MAX_NESTING_LEVELS

    def _parent_node_for_id(self, parent_id: int | None) -> _Node:
        if parent_id is None:
            return self.root
        node = self.node_for_id(int(parent_id))
        return node if node is not None else self.root

    def _node_depth_from_top(self, node: _Node) -> int:
        """
        Depth relative to a top-level task:
        - top-level task => 0
        - its child => 1
        """
        depth = 0
        cur = node
        while cur.parent and cur.parent != self.root:
            depth += 1
            cur = cur.parent
        return depth

    def _subtree_max_relative_depth(self, node: _Node) -> int:
        if not node.children:
            return 0
        return 1 + max(self._subtree_max_relative_depth(ch) for ch in node.children)

    def _can_add_under_parent(self, parent_node: _Node) -> bool:
        if parent_node == self.root:
            return True
        return (self._node_depth_from_top(parent_node) + 1) <= self.MAX_NESTING_LEVELS

    def _can_place_subtree_under_parent(self, moving_node: _Node, new_parent_node: _Node) -> bool:
        moved_root_new_depth = 0 if new_parent_node == self.root else self._node_depth_from_top(new_parent_node) + 1
        deepest_after_move = moved_root_new_depth + self._subtree_max_relative_depth(moving_node)
        return deepest_after_move <= self.MAX_NESTING_LEVELS

    def can_add_child_task(self, parent_task_id: int) -> bool:
        parent_node = self.node_for_id(int(parent_task_id))
        if parent_node is None:
            return False
        return self._can_add_under_parent(parent_node)

    def task_id_from_index(self, index: QModelIndex) -> Optional[int]:
        if not index.isValid():
            return None
        node = index.internalPointer()
        if not node or not node.task:
            return None
        return int(node.task["id"])

    def column_key(self, logical_index: int) -> str: 
        if logical_index < len(self.core_cols):
            return self.core_cols[logical_index][0]
        cc = self.custom_cols[logical_index - len(self.core_cols)]
        return f"custom:{cc['id']}"

    def custom_columns_snapshot(self):
        return list(self.custom_cols)

    def sibling_order(self, parent_id: int | None) -> list[int]:
        parent_node = self.root if parent_id is None else self.node_for_id(parent_id)
        if parent_node is None:
            parent_node = self.root
        return [int(ch.task["id"]) for ch in parent_node.children if ch.task]

    def _renumber_siblings(self, parent_id: int | None) -> None:
        """
        Reassign sequential sort_order values to the current in-memory sibling order
        and persist that order to the database.
        """
        parent_node = self.root if parent_id is None else self.node_for_id(parent_id)
        if parent_node is None:
            parent_node = self.root

        cur = self.db.conn.cursor()

        for i, ch in enumerate(parent_node.children, start=1):
            if not ch.task:
                continue
            task_id = int(ch.task["id"])
            ch.task["sort_order"] = i
            cur.execute(
                "UPDATE tasks SET sort_order=? WHERE id=?;",
                (i, task_id),
            )

        self.db.conn.commit()


    def _apply_sibling_order(self, parent_id: int | None, ordered_ids: list[int]) -> None:
        """
        Force the children of parent_id into the exact id order given by ordered_ids,
        then rewrite sort_order both in memory and in the database.

        This is used by undo/redo commands to restore a previous sibling order safely.
        """
        parent_node = self.root if parent_id is None else self.node_for_id(parent_id)
        if parent_node is None:
            parent_node = self.root

        # Current children mapped by id
        by_id = {}
        remaining = []
        for ch in parent_node.children:
            if ch.task:
                by_id[int(ch.task["id"])] = ch
            else:
                remaining.append(ch)

        # Rebuild children list in requested order
        new_children = []
        used = set()

        for tid in ordered_ids:
            node = by_id.get(int(tid))
            if node is not None:
                new_children.append(node)
                used.add(int(tid))

        # Append any children not present in ordered_ids at the end
        for ch in parent_node.children:
            if not ch.task:
                continue
            tid = int(ch.task["id"])
            if tid not in used:
                new_children.append(ch)

        # Preserve any taskless nodes too, just in case
        new_children.extend(remaining)

        self.beginResetModel()
        parent_node.children = new_children

        cur = self.db.conn.cursor()
        for i, ch in enumerate(parent_node.children, start=1):
            if not ch.task:
                continue
            task_id = int(ch.task["id"])
            ch.task["sort_order"] = i
            cur.execute(
                "UPDATE tasks SET sort_order=? WHERE id=?;",
                (i, task_id),
            )

        self.db.conn.commit()
        self.endResetModel()

        self.refresh_due_highlights()

    def snapshot_subtree(self, root_id: int) -> list[dict]:
        node = self.node_for_id(root_id)
        if not node:
            return []
        out = []

        def walk(n: _Node):
            t = dict(n.task)
            t["custom"] = dict(n.task.get("custom") or {})
            out.append(t)
            for c in n.children:
                walk(c)

        walk(node)
        return out

    def iter_nodes_preorder(self):
        def walk(n: _Node):
            for c in n.children:
                yield c
                yield from walk(c)
        yield from walk(self.root)

    # ---------- Stable index creation (for dataChanged) ----------
    def _row_in_parent(self, node: _Node) -> int:
        if not node.parent:
            return 0
        for i, ch in enumerate(node.parent.children):
            if ch is node:
                return i
        return 0

    def _index_for_node(self, node: _Node, column: int = 0) -> QModelIndex:
        if node is None or node == self.root or node.parent is None:
            return QModelIndex()
        parent = node.parent
        parent_index = QModelIndex() if parent == self.root else self._index_for_node(parent, 0)
        row = self._row_in_parent(node)
        return self.index(row, column, parent_index)

    # ---------- Model basics ----------
    def columnCount(self, parent=QModelIndex()):
        return len(self.core_cols) + len(self.custom_cols)

    def rowCount(self, parent=QModelIndex()):
        node = self.root if not parent.isValid() else parent.internalPointer()
        if not node:
            return 0
        return len(node.children)

    def index(self, row, column, parent=QModelIndex()):
        if column < 0 or column >= self.columnCount():
            return QModelIndex()

        parent_node = self.root if not parent.isValid() else parent.internalPointer()
        if not parent_node or row < 0 or row >= len(parent_node.children):
            return QModelIndex()

        child = parent_node.children[row]
        return self.createIndex(row, column, child)

    def parent(self, index: QModelIndex):
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        if not node or not node.parent or node.parent == self.root:
            return QModelIndex()

        parent_node = node.parent
        grand = parent_node.parent or self.root

        row = 0
        for i, ch in enumerate(grand.children):
            if ch is parent_node:
                row = i
                break

        return self.createIndex(row, 0, parent_node)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section < len(self.core_cols):
                return self.core_cols[section][1]
            return self.custom_cols[section - len(self.core_cols)]["name"]
        return str(section + 1)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled

        base = (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        if index.column() != 2:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    # ---------- Drag/drop ----------
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def mimeTypes(self):
        return ["application/x-focus-todo-node"]

    def mimeData(self, indexes):
        ids = sorted({self.task_id_from_index(i) for i in indexes if i.isValid() and self.task_id_from_index(i) is not None})
        if not ids:
            return QMimeData()
        md = QMimeData()
        md.setData("application/x-focus-todo-node", QByteArray(str(ids[0]).encode("utf-8")))
        return md

    def canDropMimeData(self, data, action, row, column, parent):
        if action != Qt.DropAction.MoveAction:
            return False
        if not data.hasFormat("application/x-focus-todo-node"):
            return False
        try:
            task_id = int(bytes(data.data("application/x-focus-todo-node")).decode("utf-8"))
        except Exception:
            return False

        dragged = self.node_for_id(task_id)
        if not dragged:
            return False

        new_parent_node = self.root if not parent.isValid() else parent.internalPointer()
        if not new_parent_node:
            new_parent_node = self.root

        cur = new_parent_node
        while cur and cur.task:
            if int(cur.task["id"]) == task_id:
                return False
            cur = cur.parent

        old_parent_node = dragged.parent
        if old_parent_node is new_parent_node:
            return True

        if not self._can_place_subtree_under_parent(dragged, new_parent_node):
            return False

        return True

    def dropMimeData(self, data, action, row, column, parent):
        if not self.canDropMimeData(data, action, row, column, parent):
            return False

        task_id = int(bytes(data.data("application/x-focus-todo-node")).decode("utf-8"))
        new_parent_node = self.root if not parent.isValid() else parent.internalPointer()
        new_parent_id = None if new_parent_node == self.root else int(new_parent_node.task["id"])

        if row < 0:
            row = self.rowCount(parent)

        self.undo_stack.push(MoveNodeCommand(self, task_id, new_parent_id, row))
        return True

    # ---------- Data ----------
    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        node = index.internalPointer()
        if not node or not node.task:
            return None

        col = index.column()
        value = self._get_value(node.task, col)

        if role == Qt.ItemDataRole.DisplayRole:
            if self._col_type(col) == "date":
                d = _parse_iso_date(value) if isinstance(value, str) else None
                return d.strftime("%d-%b-%Y") if d else ""
            if col == 2:
                return value or ""
            if self._col_type(col) == "bool":
                return "Yes" if (value == "1" or value is True) else "No"
            return "" if value is None else str(value)

        if role == Qt.ItemDataRole.EditRole:
            return value

        if role == Qt.ItemDataRole.BackgroundRole:
            return self._due_background(node.task)

        # NEW: readable text on dynamic due-date rows (only when bg is set)
        if role == Qt.ItemDataRole.ForegroundRole:
            bg = self._due_background(node.task)
            if isinstance(bg, QColor):
                return _best_contrast_text_color(bg)
            return None

        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if index.column() == 2:
            return False

        node = index.internalPointer()
        task_id = int(node.task["id"])
        col = index.column()

        old = self._get_value(node.task, col)
        new = self._normalize_incoming(col, value)
        if self._col_type(col) == "list" and new is not None:
            self._ensure_list_option_for_column(col, str(new))
        if old == new:
            return False

        self.undo_stack.push(EditCellCommand(self, task_id, col, old, new))
        return True

    def _col_type(self, col: int) -> str:
        if col < len(self.core_cols):
            return self.core_cols[col][2]
        return self.custom_cols[col - len(self.core_cols)]["col_type"]

    def col_type_for_column(self, col: int) -> str:
        """Public helper for delegates/proxies: returns the logical column type."""
        return self._col_type(col)

    def _custom_col_meta(self, col: int) -> Optional[dict]:
        if col < len(self.core_cols):
            return None
        idx = col - len(self.core_cols)
        if idx < 0 or idx >= len(self.custom_cols):
            return None
        return self.custom_cols[idx]

    def list_options_for_column(self, col: int) -> list[str]:
        cc = self._custom_col_meta(col)
        if not cc or str(cc.get("col_type") or "") != "list":
            return []
        vals = cc.get("list_values") or []
        return [str(v) for v in vals]

    def _ensure_list_option_for_column(self, col: int, value: str):
        cc = self._custom_col_meta(col)
        if not cc or str(cc.get("col_type") or "") != "list":
            return
        val = str(value or "").strip()
        if not val:
            return
        current = cc.setdefault("list_values", [])
        if val in current:
            return
        if self.db.add_custom_column_list_value(int(cc["id"]), val):
            current.append(val)

    def _get_value(self, task: dict, col: int):
        if col < len(self.core_cols):
            return task.get(self.core_cols[col][0])
        cc = self.custom_cols[col - len(self.core_cols)]
        return task.get("custom", {}).get(cc["id"])

    def _normalize_incoming(self, col: int, value):
        t = self._col_type(col)

        if t == "date":
            if value is None:
                return None
            s = str(value).strip()
            if not s:
                return None
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                return s[:10]
            return s

        if t == "int":
            try:
                return int(value)
            except Exception:
                return 3

        if t == "status":
            s = str(value)
            return s if s in STATUSES else "Todo"

        if t == "bool":
            if isinstance(value, bool):
                return "1" if value else "0"
            s = str(value).strip().lower()
            return "1" if s in {"1", "true", "yes", "y"} else "0"

        if t == "list":
            s = str(value or "").strip()
            return s if s else None

        return "" if value is None else str(value)

    # ---------- Smooth due-date gradient ----------
    def _due_background(self, task: dict):
        if task.get("status") == "Done":
            return None

        due = _parse_iso_date(task.get("due_date") or "")
        if not due:
            return None

        days = (due - _today()).days

        green = QColor("#00C853")
        orange = QColor("#FF9800")
        red = QColor("#D50000")

        far_days = 30
        due_days = 0
        overdue_soft = -7

        if days >= far_days:
            return green
        if days <= overdue_soft:
            return red

        t = (far_days - days) / float(far_days - due_days)
        return _tri_gradient(green, orange, red, t)

    def refresh_due_highlights(self):
        # safe minimal repaint trigger (top-level); avoids layoutChanged
        if self.rowCount() == 0 or self.columnCount() == 0:
            return
        tl = self.index(0, 0, QModelIndex())
        br = self.index(self.rowCount() - 1, self.columnCount() - 1, QModelIndex())
        if tl.isValid() and br.isValid():
            self.dataChanged.emit(
                tl,
                br,
                [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
            )

    # ---------- Public operations ----------
    def add_task(self, parent_id: int | None = None) -> bool:
        parent_node = self._parent_node_for_id(parent_id)
        effective_parent_id = None if parent_node == self.root else int(parent_node.task["id"])

        if not self._can_add_under_parent(parent_node):
            return False

        task = {
            "description": "",
            "due_date": None,
            "last_update": self._now_iso(),
            "priority": 3,
            "status": "Todo",
            "parent_id": effective_parent_id,
            "sort_order": self.db.next_sort_order(effective_parent_id),
            "is_collapsed": 0,
            "custom": {},
        }

        insert_row = len(parent_node.children)

        self.undo_stack.push(AddTaskCommand(self, effective_parent_id, insert_row, task))
        return True

    def add_child_task(self, parent_task_id: int) -> bool:
        return self.add_task(parent_id=int(parent_task_id))

    def delete_task(self, task_id: int):
        self.undo_stack.push(DeleteSubtreeCommand(self, int(task_id)))

    def add_custom_column(self, name: str, col_type: str, list_values: list[str] | None = None):
        name = (name or "").strip()
        if not name:
            return
        if col_type not in CUSTOM_TYPES:
            col_type = "text"
        self.undo_stack.push(AddCustomColumnCommand(self, name, col_type, list_values))

    def remove_custom_column(self, col_id: int):
        col = None
        for c in self.custom_cols:
            if int(c["id"]) == int(col_id):
                col = dict(c)
                break
        if not col:
            return

        cur = self.db.conn.cursor()
        cur.execute("SELECT id, name, col_type, created_at FROM custom_columns WHERE id=?;", (int(col_id),))
        row = cur.fetchone()
        if not row:
            return
        col_full = dict(row)
        if str(col_full.get("col_type") or "") == "list":
            cur.execute(
                """
                SELECT value
                FROM custom_column_list_values
                WHERE column_id=?
                ORDER BY sort_order ASC, value ASC;
                """,
                (int(col_id),),
            )
            col_full["list_values"] = [str(r["value"]) for r in cur.fetchall()]

        values = {}
        for tid, node in self._id_map.items():
            v = node.task.get("custom", {}).get(int(col_id))
            if v is not None:
                values[tid] = v

        self.undo_stack.push(RemoveColumnCommandCompat(self, col_full, values))

    def _now_iso(self) -> str:
        return datetime.now().replace(microsecond=0).isoformat(sep=" ")

    # ---------- DB helpers used by commands ----------
    def _db_insert_task(self, task: dict) -> int:
        return self.db.insert_task(task, keep_id=False)

    def _db_restore_task(self, task: dict):
        self.db.insert_task(task, keep_id=True)

    def _db_restore_subtree(self, subtree: list[dict]):
        for t in subtree:
            self.db.insert_task(t, keep_id=True)
        self.reload_all(reset_header_state=False)

    # ---------- Collapse persistence helpers ----------
    def set_collapsed(self, task_id: int, collapsed: bool):
        self.db.set_task_collapsed(task_id, collapsed)
        node = self.node_for_id(task_id)
        if node and node.task:
            node.task["is_collapsed"] = 1 if collapsed else 0

    # ---------- Internal model helpers used by commands ----------
    def _model_insert_task(self, task_id: int, parent_id: int | None, row: int):
        parent_node = self.root if parent_id is None else self.node_for_id(parent_id)
        if not parent_node:
            parent_node = self.root

        parent_index = QModelIndex() if parent_node == self.root else self._index_for_node(parent_node, 0)
        row = max(0, min(row, len(parent_node.children)))

        self.beginInsertRows(parent_index, row, row)

        t = self.db.fetch_task_by_id(task_id)
        node = _Node(task=t, parent=parent_node)
        self._id_map[int(task_id)] = node
        parent_node.children.insert(row, node)

        self.endInsertRows()
        self.refresh_due_highlights()

    def _model_remove_task(self, task_id: int):
        node = self.node_for_id(task_id)
        if not node or not node.parent:
            return

        parent_node = node.parent
        parent_index = QModelIndex() if parent_node == self.root else self._index_for_node(parent_node, 0)

        row = self._row_in_parent(node)

        self.beginRemoveRows(parent_index, row, row)

        parent_node.children.pop(row)

        def drop_ids(n: _Node):
            if n.task:
                self._id_map.pop(int(n.task["id"]), None)
            for c in n.children:
                drop_ids(c)

        drop_ids(node)

        self.endRemoveRows()
        self.refresh_due_highlights()

    def _apply_cell_change(self, task_id: int, col: int, new_value):
        """
        IMPORTANT: never emit layoutChanged here.
        Emit dataChanged for the row only.
        """
        node = self.node_for_id(task_id)
        if not node or not node.task:
            return

        if col < len(self.core_cols):
            key = self.core_cols[col][0]
            if key in {"description", "due_date", "priority", "status"}:
                self.db.update_task_field(task_id, key, new_value)
        else:
            cc = self.custom_cols[col - len(self.core_cols)]
            self.db.update_custom_value(task_id, cc["id"], new_value)

        node.task = self.db.fetch_task_by_id(task_id)

        idx0 = self._index_for_node(node, 0)
        idx_last = self._index_for_node(node, self.columnCount() - 1)
        if idx0.isValid() and idx_last.isValid():
            self.dataChanged.emit(
                idx0,
                idx_last,
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
            )

    def _model_move_node(self, task_id: int, new_parent_id: int | None, new_row: int):
        node = self.node_for_id(task_id)
        if not node or not node.parent:
            return

        old_parent_node = node.parent
        old_parent_id = None if old_parent_node == self.root else int(old_parent_node.task["id"])

        new_parent_node = self.root if new_parent_id is None else self.node_for_id(new_parent_id)
        if not new_parent_node:
            new_parent_node = self.root

        # prevent cycles
        cur = new_parent_node
        while cur and cur.task:
            if int(cur.task["id"]) == task_id:
                return
            cur = cur.parent

        if old_parent_node is not new_parent_node:
            if not self._can_place_subtree_under_parent(node, new_parent_node):
                return

        old_parent_index = QModelIndex() if old_parent_node == self.root else self._index_for_node(old_parent_node, 0)
        new_parent_index = QModelIndex() if new_parent_node == self.root else self._index_for_node(new_parent_node, 0)

        from_row = self._row_in_parent(node)

        new_row = max(0, min(new_row, len(new_parent_node.children)))
        dest_row = new_row
        if old_parent_node is new_parent_node and new_row > from_row:
            dest_row += 1

        self.beginMoveRows(old_parent_index, from_row, from_row, new_parent_index, dest_row)

        old_parent_node.children.pop(from_row)
        node.parent = new_parent_node
        new_parent_node.children.insert(new_row, node)

        self.endMoveRows()

        old_order = [int(ch.task["id"]) for ch in old_parent_node.children if ch.task]
        new_order = [int(ch.task["id"]) for ch in new_parent_node.children if ch.task]

        self.db.move_task(
            task_id=task_id,
            new_parent_id=new_parent_id,
            old_parent_id=old_parent_id,
            old_parent_order=old_order,
            new_parent_order=new_order,
        )

        for i, ch in enumerate(old_parent_node.children, start=1):
            ch.task["sort_order"] = i
        for i, ch in enumerate(new_parent_node.children, start=1):
            ch.task["sort_order"] = i
            if int(ch.task["id"]) == task_id:
                ch.task["parent_id"] = new_parent_id

        self.refresh_due_highlights()


class RemoveColumnCommandCompat(RemoveCustomColumnCommand):
    pass
