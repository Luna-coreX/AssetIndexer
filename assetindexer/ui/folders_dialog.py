"""Dialog for managing indexed root folders."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QPushButton, QVBoxLayout,
)


class FoldersDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Indexed folders")
        self.resize(560, 340)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Folders included in the index:"))

        self.list = QListWidget()
        lay.addWidget(self.list, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton("＋ Add folder…")
        add_btn.clicked.connect(self._add)
        self.remove_btn = QPushButton("🗑 Remove selected")
        self.remove_btn.clicked.connect(self._remove)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(add_btn)
        btns.addWidget(self.remove_btn)
        btns.addStretch(1)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

        self._reload()

    def _reload(self) -> None:
        self.list.clear()
        for r in self.db.roots():
            self.list.addItem(r)

    def _add(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to index")
        if path:
            self.db.add_root(path)
            self._reload()
            QMessageBox.information(
                self, "Folder added",
                "Folder added. Close this dialog and press ⟳ Rescan to index it.",
            )

    def _remove(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        path = item.text()
        ok = QMessageBox.question(
            self, "Remove folder",
            f"Remove “{path}” from the index?\n\n"
            "Its assets will be dropped from the database (files on disk are "
            "not touched).",
        )
        if ok == QMessageBox.Yes:
            n = self.db.remove_root(path)
            self._reload()
            QMessageBox.information(self, "Removed", f"Removed folder · {n} assets dropped.")
