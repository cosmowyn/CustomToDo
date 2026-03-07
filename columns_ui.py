from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem
)


class AddColumnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add custom column")

        v = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        row1.addWidget(self.name)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Type"))
        self.typ = QComboBox()
        self.typ.addItems(["text", "int", "date", "bool", "list"])
        row2.addWidget(self.typ)
        v.addLayout(row2)

        row3 = QHBoxLayout()
        self._list_label = QLabel("List values")
        row3.addWidget(self._list_label)
        self.list_values = QLineEdit()
        self.list_values.setPlaceholderText("Comma-separated values (optional)")
        row3.addWidget(self.list_values)
        v.addLayout(row3)

        self.typ.currentTextChanged.connect(self._update_type_ui)
        self._update_type_ui(self.typ.currentText())

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("Add")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        v.addLayout(btns)

    def _update_type_ui(self, col_type: str):
        is_list = str(col_type) == "list"
        self._list_label.setVisible(is_list)
        self.list_values.setVisible(is_list)

    def result_value(self):
        raw = self.list_values.text().strip()
        values = []
        if raw:
            seen = set()
            for part in raw.split(","):
                s = part.strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                values.append(s)
        return self.name.text().strip(), self.typ.currentText(), values


class RemoveColumnDialog(QDialog):
    def __init__(self, columns: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remove custom column")
        self.columns = columns

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Select a column to remove:"))

        self.list = QListWidget()
        for c in columns:
            item = QListWidgetItem(f"{c['name']}  ({c['col_type']})")
            item.setData(32, int(c["id"]))
            self.list.addItem(item)
        v.addWidget(self.list)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("Remove")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        v.addLayout(btns)

    def selected_column_id(self):
        it = self.list.currentItem()
        return int(it.data(32)) if it else None
