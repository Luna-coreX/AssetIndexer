"""Find duplicate / near-identical images by perceptual hash."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from .. import theme
from ..imaging import color_distance, hamming
from .model import pixmap_for


def _human_size(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} PB"


def _color(row):
    if row["color_r"] is None:
        return None
    return (row["color_r"], row["color_g"], row["color_b"])


def _is_dup(a, b, threshold: int, color_tol: float) -> bool:
    """Near-identical hash AND (when known) a similar dominant colour, so that
    visually different flat images are not lumped together."""
    if hamming(a["phash"], b["phash"]) > threshold:
        return False
    ca, cb = _color(a), _color(b)
    if ca is not None and cb is not None and color_distance(ca, cb) > color_tol:
        return False
    return True


def cluster_duplicates(rows, threshold: int = 8, color_tol: float = 60.0) -> list[list]:
    """Greedily group images that are near-identical by hash and colour."""
    remaining = list(rows)
    groups: list[list] = []
    used = [False] * len(remaining)
    for i in range(len(remaining)):
        if used[i]:
            continue
        base = remaining[i]
        group = [base]
        used[i] = True
        for j in range(i + 1, len(remaining)):
            if used[j]:
                continue
            if _is_dup(base, remaining[j], threshold, color_tol):
                group.append(remaining[j])
                used[j] = True
        if len(group) > 1:
            groups.append(group)
    # biggest waste first
    groups.sort(key=lambda g: sum(r["size"] for r in g) - max(r["size"] for r in g), reverse=True)
    return groups


class DuplicatesDialog(QDialog):
    def __init__(self, db, open_cb, reveal_cb, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate images")
        self.resize(880, 640)
        self._open = open_cb
        self._reveal = reveal_cb

        lay = QVBoxLayout(self)
        self.summary = QLabel("Scanning for duplicates…")
        self.summary.setStyleSheet("font-size:14px;font-weight:600;")
        lay.addWidget(self.summary)
        hint = QLabel("Click a thumbnail to reveal it in its folder. Files on disk are never touched.")
        hint.setStyleSheet(f"color:{theme.current().text_dim};font-size:12px;")
        lay.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setSpacing(14)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            groups = cluster_duplicates(db.images_with_phash())
        finally:
            QGuiApplication.restoreOverrideCursor()
        self._populate(groups)

    def _populate(self, groups) -> None:
        if not groups:
            self.summary.setText("No duplicate images found 🎉")
            return
        wasted = sum(sum(r["size"] for r in g) - max(r["size"] for r in g) for g in groups)
        dup_files = sum(len(g) - 1 for g in groups)
        self.summary.setText(
            f"{len(groups)} duplicate groups · {dup_files} redundant files · "
            f"~{_human_size(wasted)} reclaimable"
        )
        for n, group in enumerate(groups, 1):
            self.vbox.insertWidget(self.vbox.count() - 1, self._group_panel(n, group))

    def _group_panel(self, n: int, group) -> QWidget:
        t = theme.current()
        panel = QFrame()
        panel.setStyleSheet(f"QFrame{{background:{t.surface};border-radius:10px;}}")
        v = QVBoxLayout(panel)
        waste = sum(r["size"] for r in group) - max(r["size"] for r in group)
        head = QLabel(f"Group {n}  ·  {len(group)} files  ·  wastes ~{_human_size(waste)}")
        head.setStyleSheet(f"font-weight:600;color:{t.text};background:transparent;")
        v.addWidget(head)
        strip = QHBoxLayout()
        strip.setSpacing(10)
        for r in group:
            strip.addWidget(self._thumb_button(r))
        strip.addStretch(1)
        v.addLayout(strip)
        return panel

    def _thumb_button(self, row) -> QWidget:
        t = theme.current()
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(3)
        btn = QToolButton()
        btn.setIconSize(QSize(104, 104))
        btn.setFixedSize(116, 116)
        pm = pixmap_for(row)
        from PySide6.QtGui import QIcon
        btn.setIcon(QIcon(pm))
        btn.setToolTip(f"{row['path']}\n{_human_size(row['size'])}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QToolButton{{border:1px solid {t.border_strong};border-radius:8px;background:{t.thumb_bg};}}"
            f"QToolButton:hover{{border:1px solid {t.accent};}}")
        btn.clicked.connect(lambda _=False, p=row["path"]: self._reveal(p))
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda _=None, p=row["path"]: self._open(p))
        wl.addWidget(btn, alignment=Qt.AlignHCenter)
        name = QLabel(row["name"])
        name.setMaximumWidth(116)
        name.setStyleSheet(f"color:{t.text_dim};font-size:10px;background:transparent;")
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        wl.addWidget(name)
        lbl = QLabel(_human_size(row["size"]))
        lbl.setStyleSheet(f"color:{t.text_faint};font-size:10px;background:transparent;")
        lbl.setAlignment(Qt.AlignHCenter)
        wl.addWidget(lbl)
        return w
