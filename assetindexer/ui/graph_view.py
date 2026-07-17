"""Interactive dependency graph: force-directed layout on a QGraphicsView."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QSpinBox, QVBoxLayout, QDialog, QPushButton,
)

from .. import theme
from .model import _CATEGORY_COLORS

NODE_W = 154
NODE_H = 44


# ---------------------------------------------------------------------------
# Force-directed layout (Fruchterman-Reingold), vectorised with numpy.
# ---------------------------------------------------------------------------
def force_layout(node_ids: list[str], edges: list[tuple[str, str]],
                 iterations: int = 300, seed: int = 7) -> dict[str, tuple[float, float]]:
    n = len(node_ids)
    if n == 0:
        return {}
    if n == 1:
        return {node_ids[0]: (0.0, 0.0)}
    idx = {c: i for i, c in enumerate(node_ids)}
    rng = np.random.default_rng(seed)
    pos = rng.random((n, 2)) * 2 - 1
    E = np.array([[idx[a], idx[b]] for a, b in edges if a in idx and b in idx], dtype=int)
    k = 1.0 / np.sqrt(n)
    temp = 0.12
    for _ in range(iterations):
        diff = pos[:, None, :] - pos[None, :, :]
        dist2 = np.sum(diff * diff, axis=2) + 1e-9
        coeff = (k * k) / dist2
        np.fill_diagonal(coeff, 0.0)
        disp = np.einsum("ij,ijk->ik", coeff, diff)
        if len(E):
            d = pos[E[:, 0]] - pos[E[:, 1]]
            dl = np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
            f = (dl / k) * d
            np.add.at(disp, E[:, 0], -f)
            np.add.at(disp, E[:, 1], f)
        dl = np.linalg.norm(disp, axis=1, keepdims=True) + 1e-9
        pos += (disp / dl) * np.minimum(dl, temp)
        temp *= 0.985
    mn, mx = pos.min(0), pos.max(0)
    span = mx - mn
    span[span == 0] = 1.0
    pos = (pos - mn) / span
    spread = max(600.0, n * 62.0)
    return {node_ids[i]: (float(pos[i, 0] * spread), float(pos[i, 1] * spread)) for i in range(n)}


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
class EdgeItem(QGraphicsItem):
    def __init__(self, src: "NodeItem", dst: "NodeItem"):
        super().__init__()
        self.src, self.dst = src, dst
        src.edges.append(self)
        dst.edges.append(self)
        self.setZValue(-1)

    def adjust(self) -> None:
        self.prepareGeometryChange()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(self.src.pos(), self.dst.pos()).normalized().adjusted(-40, -40, 40, 40)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        p1, p2 = self.src.pos(), self.dst.pos()
        line = QLineF(p1, p2)
        if line.length() < 1:
            return
        # stop at the target node's edge so the arrow head is visible
        unit = line.unitVector()
        dx, dy = unit.dx(), unit.dy()
        end = QPointF(p2.x() - dx * (NODE_W / 2 + 4), p2.y() - dy * (NODE_H / 2 + 2))
        edge_color = QColor(theme.current().edge)
        painter.setPen(QPen(edge_color, 1.4))
        painter.drawLine(p1, end)
        # arrow head
        ah = 8.0
        left = QPointF(end.x() - dx * ah + dy * ah * 0.6, end.y() - dy * ah - dx * ah * 0.6)
        right = QPointF(end.x() - dx * ah - dy * ah * 0.6, end.y() - dy * ah + dx * ah * 0.6)
        painter.setBrush(edge_color)
        painter.drawPolygon(QPolygonF([end, left, right]))


class NodeItem(QGraphicsObject):
    activated = Signal(str)   # double-click -> re-focus (cpath)
    picked = Signal(str)      # single click -> select

    def __init__(self, meta: dict, focus: bool = False):
        super().__init__()
        self.meta = meta
        self.focus = focus
        self.edges: list[EdgeItem] = []
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)
        self.setToolTip(meta["path"])
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-NODE_W / 2 - 2, -NODE_H / 2 - 2, NODE_W + 4, NODE_H + 4)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        painter.setRenderHint(QPainter.Antialiasing)
        t = theme.current()
        rect = QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)
        color = QColor(_CATEGORY_COLORS.get(self.meta["category"], "#6b6f78"))
        bg = QColor(t.node_focus_bg) if self.focus else QColor(t.node_bg)
        painter.setBrush(QBrush(bg))
        pen = QPen(QColor(t.accent) if self.focus else color, 2.2 if self.focus else 1.4)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 9, 9)
        # category colour dot
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(-NODE_W / 2 + 14, 0), 5, 5)
        # name (elided)
        painter.setPen(QColor(t.text) if self.focus else QColor(t.text_dim))
        f = QFont("Segoe UI", 9)
        f.setBold(self.focus)
        painter.setFont(f)
        fm = QFontMetrics(f)
        text_rect = rect.adjusted(28, 0, -8, 0)
        name = fm.elidedText(self.meta["name"], Qt.ElideMiddle, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in self.edges:
                e.adjust()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):  # noqa: N802
        self.picked.emit(self.meta["cpath"])
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.activated.emit(self.meta["cpath"])
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# View with wheel-zoom and empty-space panning
# ---------------------------------------------------------------------------
class GraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._panning = False
        self._pan_start = None

    def wheelEvent(self, event):  # noqa: N802
        factor = 1.16 if event.angleDelta().y() > 0 else 1 / 1.16
        self.scale(factor, factor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.itemAt(event.pos()) is None:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
class GraphDialog(QDialog):
    show_in_app = Signal(int)  # asset id

    def __init__(self, db, focus_cpath: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Dependency graph")
        self.resize(940, 680)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel("")
        self.title.setStyleSheet("font-size:14px;font-weight:600;")
        bar.addWidget(self.title, 1)
        bar.addWidget(QLabel("Depth:"))
        self.depth = QSpinBox()
        self.depth.setRange(1, 5)
        self.depth.setValue(2)
        self.depth.valueChanged.connect(lambda _: self._load(self._focus))
        bar.addWidget(self.depth)
        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self._fit)
        bar.addWidget(fit_btn)
        lay.addLayout(bar)

        self.scene = QGraphicsScene(self)
        self.view = GraphView(self.scene)
        self.view.setBackgroundBrush(QColor(theme.current().graph_bg))
        lay.addWidget(self.view, 1)

        self.hint = QLabel(
            "  Scroll to zoom · drag empty space to pan · drag a node to move · "
            "double-click a node to re-centre")
        self.hint.setStyleSheet(f"color:{theme.current().text_dim};font-size:11px;padding:6px 12px;")
        lay.addWidget(self.hint)

        self._focus = focus_cpath
        self._load(focus_cpath)

    def _load(self, cpath: str) -> None:
        self._focus = cpath
        metas, edges, truncated = self.db.dependency_subgraph(cpath, hops=self.depth.value())
        self.scene.clear()
        if not metas:
            return
        node_ids = list(metas.keys())
        positions = force_layout(node_ids, edges)
        items: dict[str, NodeItem] = {}
        for cp in node_ids:
            item = NodeItem(metas[cp], focus=(cp == cpath))
            item.picked.connect(self._on_pick)
            item.activated.connect(self._load)
            x, y = positions[cp]
            item.setPos(x, y)
            self.scene.addItem(item)
            items[cp] = item
        for a, b in edges:
            if a in items and b in items:
                self.scene.addItem(EdgeItem(items[a], items[b]))

        focus_meta = metas[cpath]
        extra = "  (truncated)" if truncated else ""
        self.title.setText(f"{focus_meta['name']}   ·   {len(node_ids)} nodes · {len(edges)} links{extra}")
        self._fit()

    def _fit(self) -> None:
        rect = self.scene.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        if not rect.isEmpty():
            self.view.setSceneRect(rect)
            self.view.fitInView(rect, Qt.KeepAspectRatio)

    def _on_pick(self, cpath: str) -> None:
        asset = self.db.get_asset_by_cpath(cpath)
        if asset:
            self.show_in_app.emit(asset["id"])
