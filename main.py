"""Asset Indexer — entry point.

Run:  venv/Scripts/python.exe main.py
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from assetindexer import APP_NAME
from assetindexer.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    win = MainWindow()          # applies the persisted theme on construction
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
