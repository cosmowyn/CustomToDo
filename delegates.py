from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QDateEdit, QSpinBox, QComboBox

from model import STATUSES


class AdaptiveRowDelegate(QStyledItemDelegate):
    """
    Fixes too-small row heights when users choose larger fonts.

    - Ensures sizeHint() is at least font height + padding
    - Draws a subtle separator line under parent rows (rows with children)
      NOTE: works with both source model and proxy models.
    """

    EXTRA_VPAD = 10  # avoids clipping for big fonts

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        fm = option.fontMetrics
        min_h = fm.height() + self.EXTRA_VPAD
        if base.height() < min_h:
            base.setHeight(min_h)
        return base

    def _has_children(self, index) -> bool:
        # Support proxy models (mapToSource)
        m = index.model()
        try:
            idx0 = index.siblingAtColumn(0)
        except Exception:
            idx0 = index

        if hasattr(m, "mapToSource"):
            try:
                src = m.mapToSource(idx0)
                sm = m.sourceModel()
                if sm is None or not src.isValid():
                    return False
                return sm.rowCount(src) > 0
            except Exception:
                return False

        # Source model
        try:
            return m.rowCount(idx0) > 0
        except Exception:
            return False

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)

        # Draw line only once per row
        if index.column() != 0:
            return

        if not self._has_children(index):
            return

        painter.save()
        pen = QPen(option.palette.mid().color())
        pen.setWidth(1)
        painter.setPen(pen)
        r = option.rect
        y = r.bottom()
        painter.drawLine(r.left(), y, r.right(), y)
        painter.restore()


class DateDelegate(AdaptiveRowDelegate):
    def createEditor(self, parent, option, index):
        ed = QDateEdit(parent)
        ed.setCalendarPopup(True)
        ed.setDisplayFormat("dd-MMM-yyyy")
        ed.setMinimumHeight(option.fontMetrics.height() + self.EXTRA_VPAD)
        return ed

    def setEditorData(self, editor, index):
        s = index.model().data(index, Qt.ItemDataRole.EditRole)
        if s and isinstance(s, str) and len(s) >= 10 and s[4] == "-" and s[7] == "-":
            y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
            editor.setDate(QDate(y, m, d))
        else:
            editor.setDate(QDate.currentDate())

    def setModelData(self, editor, model, index):
        qd = editor.date()
        model.setData(index, qd.toString("yyyy-MM-dd"), Qt.ItemDataRole.EditRole)


class PriorityDelegate(AdaptiveRowDelegate):
    def createEditor(self, parent, option, index):
        ed = QSpinBox(parent)
        ed.setRange(1, 5)
        ed.setMinimumHeight(option.fontMetrics.height() + self.EXTRA_VPAD)
        return ed

    def setEditorData(self, editor, index):
        v = index.model().data(index, Qt.ItemDataRole.EditRole)
        try:
            editor.setValue(int(v))
        except Exception:
            editor.setValue(3)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)


class StatusDelegate(AdaptiveRowDelegate):
    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(STATUSES)
        cb.setMinimumHeight(option.fontMetrics.height() + self.EXTRA_VPAD)
        return cb

    def setEditorData(self, editor, index):
        v = str(index.model().data(index, Qt.ItemDataRole.EditRole) or "Todo")
        i = editor.findText(v)
        editor.setCurrentIndex(i if i >= 0 else 0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


def install_delegates(view, model):
    # Base delegate for all columns (row height + parent separator)
    view.setItemDelegate(AdaptiveRowDelegate(view))

    # Column-specific editors (inherit AdaptiveRowDelegate so sizeHint stays consistent)
    view.setItemDelegateForColumn(1, DateDelegate(view))
    view.setItemDelegateForColumn(3, PriorityDelegate(view))
    view.setItemDelegateForColumn(4, StatusDelegate(view))