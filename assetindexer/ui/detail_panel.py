"""Right-hand detail panel for the selected asset."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtMultimediaWidgets import QVideoWidget  # noqa: F401  (ensures backend load)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from .. import config, theme
from .model import pixmap_for


def _human_size(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} PB"


def _human_duration(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _ms(ms: int) -> str:
    m, s = divmod(int(ms) // 1000, 60)
    return f"{m}:{s:02d}"


class DetailPanel(QWidget):
    favorite_toggled = Signal(int, bool)
    tags_changed = Signal(int, list)
    find_similar = Signal(int)
    search_color = Signal(int, int, int)
    navigate_asset = Signal(int)   # asset id to open in the grid
    reveal_path = Signal(str)      # non-indexed file to reveal in folder

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = None
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._preview_effect = QGraphicsOpacityEffect(self.preview)
        self._preview_effect.setOpacity(1.0)
        self.preview.setGraphicsEffect(self._preview_effect)
        self._preview_anim = QPropertyAnimation(self._preview_effect, b"opacity", self)
        self._preview_anim.setDuration(160)
        self._preview_anim.setEasingCurve(QEasingCurve.OutCubic)
        lay.addWidget(self.preview)

        self.title = QLabel("", wordWrap=True)
        self.title.setStyleSheet("font-size:15px;font-weight:600;")
        lay.addWidget(self.title)

        self.info = QLabel("", wordWrap=True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.info)

        # audio player (shown only for music / sound assets)
        self.player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(0.9)
        self.player.setAudioOutput(self._audio_out)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.playbackStateChanged.connect(self._on_state)

        self.audio_row = QWidget()
        arl = QVBoxLayout(self.audio_row)
        arl.setContentsMargins(0, 0, 0, 0)
        arl.setSpacing(4)
        top = QHBoxLayout()
        self.play_btn = QPushButton("▶  Play")
        self.play_btn.clicked.connect(self._toggle_play)
        self.time_lbl = QLabel("0:00 / 0:00")
        self.time_lbl.setObjectName("timeLabel")
        top.addWidget(self.play_btn)
        top.addStretch(1)
        top.addWidget(self.time_lbl)
        arl.addLayout(top)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        arl.addWidget(self.seek)
        lay.addWidget(self.audio_row)

        # colour swatch + "search by colour"
        self.color_row = QWidget()
        crl = QHBoxLayout(self.color_row)
        crl.setContentsMargins(0, 0, 0, 0)
        self.swatch = QFrame()
        self.swatch.setFixedSize(26, 26)
        self.swatch.setStyleSheet("border-radius:5px;border:1px solid #444;")
        self.color_btn = QPushButton("Search by this colour")
        self.color_btn.clicked.connect(self._emit_color)
        crl.addWidget(self.swatch)
        crl.addWidget(self.color_btn, 1)
        lay.addWidget(self.color_row)

        # dependency graph sections
        self.uses_head = _section("USES")
        lay.addWidget(self.uses_head)
        self.uses_list = _dep_list()
        self.uses_list.itemClicked.connect(self._on_dep_clicked)
        lay.addWidget(self.uses_list)

        self.usedin_head = _section("USED IN")
        lay.addWidget(self.usedin_head)
        self.usedin_list = _dep_list()
        self.usedin_list.itemClicked.connect(self._on_dep_clicked)
        lay.addWidget(self.usedin_list)

        # tags
        lay.addWidget(_section("Tags"))
        self.tags_edit = QLineEdit(placeholderText="comma, separated, tags")
        self.tags_edit.editingFinished.connect(self._emit_tags)
        lay.addWidget(self.tags_edit)

        # actions
        btn_row = QHBoxLayout()
        self.fav_btn = QPushButton("☆ Favourite")
        self.fav_btn.setCheckable(True)
        self.fav_btn.clicked.connect(self._emit_favorite)
        self.similar_btn = QPushButton("Find similar")
        self.similar_btn.clicked.connect(lambda: self._row and self.find_similar.emit(self._row["id"]))
        btn_row.addWidget(self.fav_btn)
        btn_row.addWidget(self.similar_btn)
        lay.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self._open_file)
        self.reveal_btn = QPushButton("Show in folder")
        self.reveal_btn.clicked.connect(self._reveal)
        btn_row2.addWidget(self.open_btn)
        btn_row2.addWidget(self.reveal_btn)
        lay.addLayout(btn_row2)

        lay.addStretch(1)
        self.restyle()
        self.clear()

    def restyle(self) -> None:
        """Re-apply theme-dependent styling (called on theme change)."""
        t = theme.current()
        self.preview.setStyleSheet(
            f"background:{t.surface2};border-radius:12px;color:{t.text_faint};")
        self.info.setStyleSheet(f"color:{t.text_dim};font-size:12px;")
        self.time_lbl.setStyleSheet(f"color:{t.text_dim};font-size:11px;")

    # ------------------------------------------------------------------
    def set_row(self, row) -> None:
        self._row = row
        if row is None:
            self.clear()
            return
        self.setEnabled(True)
        pm = pixmap_for(row)
        self.preview.setPixmap(
            pm.scaled(self.preview.width() or 340, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._preview_anim.stop()
        self._preview_anim.setStartValue(0.0)
        self._preview_anim.setEndValue(1.0)
        self._preview_anim.start()
        self.title.setText(row["name"])

        lines = [f"<b>{config.CATEGORY_LABELS.get(row['category'], row['category'])}</b> · {row['ext']}"]
        lines.append(_human_size(row["size"]))
        if row["width"]:
            lines.append(f"{row['width']} × {row['height']} px")
        if row["duration"]:
            lines.append(f"Duration {_human_duration(row['duration'])}")
        meta = _parse_meta(row)
        for k in ("family", "style", "title", "artist", "album"):
            if meta.get(k):
                lines.append(f"{k.capitalize()}: {meta[k]}")
        lines.append(f"<span style='color:#767a83'>{row['path']}</span>")
        self.info.setText("<br>".join(lines))

        # audio player
        is_audio = row["category"] in config.AUDIO_CATEGORIES
        self.audio_row.setVisible(is_audio)
        self.player.stop()
        if is_audio:
            self.player.setSource(QUrl.fromLocalFile(row["path"]))
            self.play_btn.setText("▶  Play")
            self.time_lbl.setText("0:00 / 0:00")

        has_color = row["color_r"] is not None
        self.color_row.setVisible(has_color)
        if has_color:
            self.swatch.setStyleSheet(
                f"background:rgb({row['color_r']},{row['color_g']},{row['color_b']});"
                "border-radius:5px;border:1px solid #444;"
            )
        self.fav_btn.setChecked(bool(row["favorite"]))
        self.fav_btn.setText("★ Favourite" if row["favorite"] else "☆ Favourite")
        self.similar_btn.setVisible(bool(row["phash"]))

    def set_tags(self, tags: list[str]) -> None:
        self.tags_edit.setText(", ".join(tags))

    def set_dependencies(self, uses: list[dict], used_in: list[dict]) -> None:
        _fill_dep_list(self.uses_list, uses)
        _fill_dep_list(self.usedin_list, used_in)
        self.uses_head.setText(f"USES  ({len(uses)})")
        self.usedin_head.setText(f"USED IN  ({len(used_in)})")
        self.uses_head.setVisible(bool(uses))
        self.uses_list.setVisible(bool(uses))
        self.usedin_head.setVisible(bool(used_in))
        self.usedin_list.setVisible(bool(used_in))

    def _on_dep_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data.get("asset_id") is not None:
            self.navigate_asset.emit(data["asset_id"])
        else:
            self.reveal_path.emit(data["path"])

    def clear(self) -> None:
        self._row = None
        self.player.stop()
        self.preview.setText("Select an asset")
        self.preview.setPixmap(QPixmap())
        self.title.setText("")
        self.info.setText("")
        self.tags_edit.clear()
        self.color_row.setVisible(False)
        self.audio_row.setVisible(False)
        for w in (self.uses_head, self.uses_list, self.usedin_head, self.usedin_list):
            w.setVisible(False)
        self.setEnabled(False)

    # -- audio playback -------------------------------------------------
    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setText("⏸  Pause" if playing else "▶  Play")

    def _on_pos(self, pos: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(pos)
        self.time_lbl.setText(f"{_ms(pos)} / {_ms(self.player.duration())}")

    def _on_dur(self, dur: int) -> None:
        self.seek.setRange(0, dur)
        self.time_lbl.setText(f"{_ms(self.player.position())} / {_ms(dur)}")

    # ------------------------------------------------------------------
    def _emit_favorite(self) -> None:
        if self._row:
            state = self.fav_btn.isChecked()
            self.fav_btn.setText("★ Favourite" if state else "☆ Favourite")
            self.favorite_toggled.emit(self._row["id"], state)

    def _emit_tags(self) -> None:
        if self._row:
            tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
            self.tags_changed.emit(self._row["id"], tags)

    def _emit_color(self) -> None:
        if self._row and self._row["color_r"] is not None:
            self.search_color.emit(self._row["color_r"], self._row["color_g"], self._row["color_b"])

    def _open_file(self) -> None:
        if self._row:
            _os_open(self._row["path"])

    def _reveal(self) -> None:
        if self._row:
            reveal_in_folder(self._row["path"])


def _section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "section")
    return lbl


def _dep_list() -> QListWidget:
    lw = QListWidget()
    lw.setMaximumHeight(132)
    lw.setCursor(Qt.PointingHandCursor)
    return lw


def _fill_dep_list(lw: QListWidget, items: list[dict]) -> None:
    from .model import _CATEGORY_COLORS
    lw.clear()
    faint = theme.current().text_faint
    for d in items:
        prefix = "" if d["depth"] <= 1 else "↳ "
        it = QListWidgetItem(f"{prefix}{d['name']}")
        it.setData(Qt.UserRole, d)
        it.setToolTip(f"{d['path']}" + ("" if d["depth"] <= 1 else f"   (indirect, depth {d['depth']})"))
        color = _CATEGORY_COLORS.get(d["category"], faint)
        it.setForeground(QColor(color) if d["depth"] <= 1 else QColor(faint))
        lw.addItem(it)


def _parse_meta(row) -> dict:
    try:
        return json.loads(row["meta"]) if row["meta"] else {}
    except Exception:
        return {}


def _os_open(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def reveal_in_folder(path: str) -> None:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception:
        pass
