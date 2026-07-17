"""Icon grid view with hover tracking and a card delegate."""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtWidgets import QListView

from .. import config
from .delegate import AssetCardDelegate


class AssetGridView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(6)
        self.setSelectionMode(QListView.SingleSelection)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setIconSize(QSize(config.GRID_ICON_SIZE, config.GRID_ICON_SIZE))
        # drag assets out to Explorer / other apps
        self.setDragEnabled(True)
        self.setDragDropMode(QListView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self._delegate = AssetCardDelegate(self)
        self.setItemDelegate(self._delegate)
        self.entered.connect(self._delegate.set_hover)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._delegate.set_hover(QModelIndex())
        super().leaveEvent(event)
