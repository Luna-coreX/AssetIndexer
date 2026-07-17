"""Statistics dashboard: counts, disk usage by category, largest files."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)

from .. import config, theme
from .model import _CATEGORY_COLORS


def _human_size(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} PB"


class StatsDialog(QDialog):
    def __init__(self, db, reveal_cb, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics")
        self.resize(720, 640)
        self._reveal = reveal_cb
        s = db.stats()

        lay = QVBoxLayout(self)
        lay.setSpacing(16)

        # top stat tiles
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        tiles.addWidget(_tile("Assets", f"{s['total_count']:,}"))
        tiles.addWidget(_tile("Total size", _human_size(s["total_size"])))
        tiles.addWidget(_tile("Favourites", f"{s['favourites']:,}"))
        tiles.addWidget(_tile("Tags", f"{s['tags']:,}"))
        lay.addLayout(tiles)

        # per-category usage bars
        lay.addWidget(_heading("Disk usage by category"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        per = s["per_category"]
        max_size = max((v["size"] for v in per.values()), default=1) or 1
        r = 0
        for cat in config.CATEGORY_ORDER:
            if cat not in per:
                continue
            info = per[cat]
            grid.addWidget(_catlabel(cat), r, 0)
            grid.addWidget(_bar(info["size"] / max_size, _CATEGORY_COLORS.get(cat, "#6b6f78")), r, 1)
            val = QLabel(f"{info['count']:,} files · {_human_size(info['size'])}")
            val.setStyleSheet("color:#b9bcc4;font-size:12px;")
            grid.addWidget(val, r, 2)
            r += 1
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # largest files
        lay.addWidget(_heading("Largest files  (double-click to reveal)"))
        self.big = QListWidget()
        for row in s["largest"]:
            it = QListWidgetItem(f"{_human_size(row['size']):>9}   {row['name']}")
            it.setData(Qt.UserRole, row["path"])
            it.setToolTip(row["path"])
            self.big.addItem(it)
        self.big.itemDoubleClicked.connect(lambda it: self._reveal(it.data(Qt.UserRole)))
        lay.addWidget(self.big, 1)


def _tile(label: str, value: str) -> QWidget:
    t = theme.current()
    w = QFrame()
    w.setStyleSheet(f"QFrame{{background:{t.surface};border-radius:10px;}}")
    v = QVBoxLayout(w)
    v.setContentsMargins(14, 12, 14, 12)
    val = QLabel(value)
    val.setStyleSheet(f"font-size:22px;font-weight:700;color:{t.text};background:transparent;")
    cap = QLabel(label.upper())
    cap.setStyleSheet(f"color:{t.text_dim};font-size:10px;font-weight:700;letter-spacing:1px;background:transparent;")
    v.addWidget(val)
    v.addWidget(cap)
    return w


def _heading(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.current().text_dim};font-size:11px;font-weight:700;letter-spacing:1px;")
    return lbl


def _catlabel(cat: str) -> QLabel:
    lbl = QLabel(config.CATEGORY_LABELS.get(cat, cat))
    lbl.setFixedWidth(90)
    lbl.setStyleSheet(f"color:{theme.current().text};font-size:12px;")
    return lbl


def _bar(fraction: float, color: str) -> QWidget:
    track = QFrame()
    track.setFixedHeight(14)
    track.setStyleSheet(f"background:{theme.current().thumb_bg};border-radius:7px;")
    hl = QHBoxLayout(track)
    hl.setContentsMargins(0, 0, 0, 0)
    fill = QFrame()
    fill.setStyleSheet(f"background:{color};border-radius:7px;")
    fill.setFixedHeight(14)
    hl.addWidget(fill, max(1, int(fraction * 1000)))
    hl.addStretch(max(1, int((1 - fraction) * 1000)))
    return track
