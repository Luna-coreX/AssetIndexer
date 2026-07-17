"""Qt list model that presents assets as a lazily-thumbnailed icon grid."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractListModel, QMimeData, QModelIndex, QSize, Qt, QUrl,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

from .. import config, theme

ID_ROLE = Qt.UserRole + 1
ROW_ROLE = Qt.UserRole + 2

_CATEGORY_COLORS = {
    "texture": "#3d7ea6",
    "model": "#8e6bd1",
    "music": "#3aa675",
    "sound": "#3a9fa6",
    "font": "#c58a3a",
    "document": "#b5544e",
    "project": "#c07ac0",
    "other": "#6b6f78",
}

_placeholder_cache: dict[str, QPixmap] = {}
_thumb_cache: dict[str, QPixmap] = {}


def _placeholder(category: str, ext: str) -> QPixmap:
    t = theme.current()
    key = f"{t.name}:{category}:{ext}"
    if key in _placeholder_cache:
        return _placeholder_cache[key]
    size = config.THUMB_SIZE
    pm = QPixmap(size, size)
    pm.fill(QColor(t.thumb_bg))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    accent = QColor(_CATEGORY_COLORS.get(category, "#6b6f78"))
    p.setBrush(accent)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(size * 0.18, size * 0.16, size * 0.64, size * 0.52, 14, 14)
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setPixelSize(int(size * 0.26))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect().adjusted(0, -int(size * 0.06), 0, -int(size * 0.06)),
               Qt.AlignCenter, config.CATEGORY_GLYPHS.get(category, "•"))
    f2 = QFont()
    f2.setPixelSize(int(size * 0.11))
    f2.setBold(True)
    p.setFont(f2)
    p.setPen(QColor(t.text_dim))
    p.drawText(pm.rect().adjusted(0, int(size * 0.30), 0, int(size * 0.30)),
               Qt.AlignHCenter | Qt.AlignVCenter, ext.upper().lstrip("."))
    p.end()
    _placeholder_cache[key] = pm
    return pm


def pixmap_for(row) -> QPixmap:
    thumb = row["thumb"] if "thumb" in row.keys() else None
    if thumb:
        if thumb in _thumb_cache:
            return _thumb_cache[thumb]
        pm = QPixmap(thumb)
        if not pm.isNull():
            _thumb_cache[thumb] = pm
            return pm
    return _placeholder(row["category"], row["ext"] if "ext" in row.keys() else "")


class AssetListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[Any] = []

    def set_rows(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, index: QModelIndex):
        if 0 <= index.row() < len(self._rows):
            return self._rows[index.row()]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    # -- drag out to other apps / Explorer ------------------------------
    def flags(self, index):  # noqa: N802
        base = super().flags(index)
        if index.isValid():
            return base | Qt.ItemIsDragEnabled
        return base

    def mimeTypes(self):  # noqa: N802
        return ["text/uri-list"]

    def mimeData(self, indexes):  # noqa: N802
        md = QMimeData()
        urls = []
        for idx in indexes:
            if idx.isValid():
                urls.append(QUrl.fromLocalFile(self._rows[idx.row()]["path"]))
        md.setUrls(urls)
        return md

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return row["name"]
        if role == Qt.DecorationRole:
            return pixmap_for(row)
        if role == Qt.ToolTipRole:
            return row["path"]
        if role == ID_ROLE:
            return row["id"]
        if role == ROW_ROLE:
            return row
        if role == Qt.SizeHintRole:
            s = config.GRID_ICON_SIZE
            return QSize(s + 26, s + 44)
        return None
