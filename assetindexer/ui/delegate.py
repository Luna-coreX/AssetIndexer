"""Custom card delegate: rounded thumbnails, extension badge, animated hover."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QModelIndex, QRectF, QSize, Qt, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import config, theme
from .model import ROW_ROLE, _CATEGORY_COLORS

CARD_MARGIN = 5
CARD_PAD = 11
CARD_RADIUS = 15
THUMB_RADIUS = 10


def _lerp(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class AssetCardDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._hover = QModelIndex()
        self._t = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    # -- hover animation ------------------------------------------------
    def _on_anim(self, value) -> None:
        self._t = float(value)
        if self._hover.isValid():
            self.view.viewport().update()

    def set_hover(self, index: QModelIndex) -> None:
        if index == self._hover:
            return
        self._hover = QModelIndex(index)
        self._anim.stop()
        if index.isValid():
            self._anim.start()
        else:
            self._t = 0.0
        self.view.viewport().update()

    # -- sizing ---------------------------------------------------------
    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        wc = config.GRID_ICON_SIZE + 34
        return QSize(wc, wc + 42)

    # -- painting -------------------------------------------------------
    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        t = theme.current()
        selected = bool(option.state & QStyle.State_Selected)
        hovered = index == self._hover
        hv = self._t if hovered else 0.0
        lift = max(hv, 1.0 if selected else 0.0)

        card = QRectF(option.rect).adjusted(CARD_MARGIN, CARD_MARGIN, -CARD_MARGIN, -CARD_MARGIN)

        # drop shadow on hover / selection
        if lift > 0:
            shadow = QRectF(card).adjusted(2, 3 + 3 * lift, 2, 5 + 4 * lift)
            sp = QPainterPath()
            sp.addRoundedRect(shadow, CARD_RADIUS, CARD_RADIUS)
            painter.fillPath(sp, QColor(0, 0, 0, int((40 if not t.dark else 70) * lift)))

        # card background
        if selected:
            bg = QColor(t.sel_bg)
        else:
            bg = _lerp(QColor(t.card), QColor(t.card_hover), hv)
        path = QPainterPath()
        path.addRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
        painter.fillPath(path, bg)

        # border
        if selected:
            pen = QPen(QColor(t.accent))
            pen.setWidthF(1.8)
            painter.setPen(pen)
            painter.drawPath(path)
        elif hv > 0:
            bc = QColor(t.border_strong)
            bc.setAlpha(int(230 * hv))
            pen = QPen(bc)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            painter.drawPath(path)

        row = index.data(ROW_ROLE)
        category = row["category"] if row is not None else "other"
        ext = (row["ext"] if row is not None else "").upper().lstrip(".")
        accent = QColor(_CATEGORY_COLORS.get(category, "#6b6f78"))

        # thumbnail
        side = card.width() - 2 * CARD_PAD
        thumb = QRectF(card.x() + CARD_PAD, card.y() + CARD_PAD, side, side)
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(thumb, THUMB_RADIUS, THUMB_RADIUS)
        painter.setClipPath(clip)
        painter.fillRect(thumb, QColor(t.thumb_bg))
        pm = index.data(Qt.DecorationRole)
        if isinstance(pm, QPixmap) and not pm.isNull():
            scaled = pm.scaled(thumb.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = thumb.x() + (thumb.width() - scaled.width()) / 2
            y = thumb.y() + (thumb.height() - scaled.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
        painter.restore()

        # extension badge (always shows the extension, bottom-right of thumb)
        if ext:
            painter.setFont(_badge_font())
            fm = QFontMetrics(_badge_font())
            bw = fm.horizontalAdvance(ext) + 14
            bh = fm.height() + 4
            badge = QRectF(thumb.right() - bw - 6, thumb.bottom() - bh - 6, bw, bh)
            bp = QPainterPath()
            bp.addRoundedRect(badge, bh / 2, bh / 2)
            painter.fillPath(bp, QColor(accent.red(), accent.green(), accent.blue(), 235))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, Qt.AlignCenter, ext)

        # filename (up to 2 lines, extension preserved via middle elision)
        name = row["name"] if row is not None else index.data(Qt.DisplayRole)
        text_rect = QRectF(
            card.x() + CARD_PAD, thumb.bottom() + 7,
            side, card.bottom() - thumb.bottom() - 10,
        )
        painter.setPen(QColor(t.text) if (selected or hv > 0) else QColor(t.text_dim))
        painter.setFont(_name_font())
        _draw_name(painter, text_rect, name, QFontMetrics(_name_font()))

        painter.restore()


def _name_font() -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(12)
    return f


def _badge_font() -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(10)
    f.setBold(True)
    return f


def _draw_name(painter: QPainter, rect: QRectF, name: str, fm: QFontMetrics) -> None:
    w = int(rect.width())
    if fm.horizontalAdvance(name) <= w:
        painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, name)
        return
    # greedily fill the first line, keep the remainder (with the extension) on
    # the second, middle-eliding only if it still overflows.
    i = len(name)
    while i > 1 and fm.horizontalAdvance(name[:i]) > w:
        i -= 1
    line1, line2 = name[:i], name[i:]
    if fm.horizontalAdvance(line2) > w:
        line2 = fm.elidedText(line2, Qt.ElideMiddle, w)
    lh = fm.height()
    r1 = QRectF(rect.x(), rect.y(), rect.width(), lh)
    r2 = QRectF(rect.x(), rect.y() + lh, rect.width(), lh)
    painter.drawText(r1, Qt.AlignHCenter | Qt.AlignTop, line1)
    painter.drawText(r2, Qt.AlignHCenter | Qt.AlignTop, line2)
