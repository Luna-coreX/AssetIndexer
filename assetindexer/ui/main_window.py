"""Main application window."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QComboBox, QFileDialog,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QProgressBar, QPushButton, QSplitter, QToolBar, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QMimeData

from .. import config, theme
from ..database import Database
from ..imaging import color_distance, hamming
from ..scanner import ScanWorker
from .detail_panel import DetailPanel
from .grid_view import AssetGridView
from .model import AssetListModel, ID_ROLE, ROW_ROLE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Asset Indexer")
        self.resize(1180, 760)

        self.db = Database()
        self.worker: ScanWorker | None = None
        self._special_mode = None  # None | "color" | "similar"
        self._last_scan_refresh = 0

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

        self._debounce = QTimer(self, singleShot=True, interval=180)
        self._debounce.timeout.connect(self.refresh)

        # apply the persisted theme (without re-persisting it)
        saved = self.db.get_setting("theme", theme.DEFAULT)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(saved)
        self.theme_combo.blockSignals(False)
        self.apply_theme(saved, persist=False)

        self.refresh()
        if not self.db.roots():
            self.status.setText("Add a folder to start indexing  →  “Add folder”")

    def apply_theme(self, name: str, persist: bool = True) -> None:
        theme.set_current(name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.qss(theme.current()))
        from .model import _placeholder_cache
        _placeholder_cache.clear()
        self.detail.restyle()
        self.view.viewport().update()
        if persist:
            self.db.set_setting("theme", name)

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        add_act = QAction("＋ Add folder", self)
        add_act.triggered.connect(self.add_folder)
        tb.addAction(add_act)

        rescan_act = QAction("⟳ Rescan", self)
        rescan_act.triggered.connect(self.rescan)
        tb.addAction(rescan_act)

        folders_act = QAction("🗂 Folders", self)
        folders_act.triggered.connect(self.manage_folders)
        tb.addAction(folders_act)

        dups_act = QAction("⧉ Duplicates", self)
        dups_act.triggered.connect(self.show_duplicates)
        tb.addAction(dups_act)

        stats_act = QAction("📊 Stats", self)
        stats_act.triggered.connect(self.show_stats)
        tb.addAction(stats_act)

        graph_act = QAction("🕸 Graph", self)
        graph_act.triggered.connect(self.show_graph)
        tb.addAction(graph_act)
        tb.addSeparator()

        self.search_box = QLineEdit(placeholderText="Search  (e.g.  metal floor)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.search_box.setMinimumWidth(320)
        tb.addWidget(self.search_box)
        tb.addSeparator()

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.addItem("Newest", "newest")
        self.sort_combo.addItem("Largest", "size")
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        tb.addWidget(QLabel(" Sort: "))
        tb.addWidget(self.sort_combo)

        self.fav_btn = QPushButton("★ Favourites")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self.refresh)
        tb.addWidget(self.fav_btn)

        self.color_btn = QPushButton("🎨 By colour")
        self.color_btn.clicked.connect(self.pick_color)
        tb.addWidget(self.color_btn)

        self.theme_combo = QComboBox()
        for n in theme.names():
            self.theme_combo.addItem(n)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        tb.addWidget(QLabel(" Theme: "))
        tb.addWidget(self.theme_combo)

    def _build_body(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # category filter chips
        chip_bar = QWidget()
        chl = QHBoxLayout(chip_bar)
        chl.setContentsMargins(10, 8, 10, 8)
        chl.setSpacing(6)
        self.cat_group = QButtonGroup(self)
        self.cat_group.setExclusive(True)
        for key in ["all"] + config.CATEGORY_ORDER:
            label = "All" if key == "all" else config.CATEGORY_LABELS[key]
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("cat", key)
            b.setProperty("chip", True)
            b.setCursor(Qt.PointingHandCursor)
            if key == "all":
                b.setChecked(True)
            self.cat_group.addButton(b)
            chl.addWidget(b)
        chl.addStretch(1)
        self.cat_group.buttonClicked.connect(self._on_category)
        root.addWidget(chip_bar)

        splitter = QSplitter()
        self.model = AssetListModel(self)
        self.view = AssetGridView()
        self.view.setModel(self.model)
        self.view.selectionModel().currentChanged.connect(self._on_select)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        splitter.addWidget(self.view)

        self.detail = DetailPanel()
        self.detail.favorite_toggled.connect(self._on_favorite)
        self.detail.tags_changed.connect(self._on_tags)
        self.detail.find_similar.connect(self.find_similar)
        self.detail.search_color.connect(lambda r, g, b: self.search_by_color((r, g, b)))
        self.detail.navigate_asset.connect(self.navigate_to_asset)
        self.detail.reveal_path.connect(self._reveal_path)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([840, 340])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        self.status = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.progress)

    # -------------------------------------------------------------- search
    def _on_search_changed(self) -> None:
        self._special_mode = None
        self._debounce.start()

    def _on_category(self) -> None:
        self._special_mode = None
        self.refresh()

    def current_category(self) -> str:
        btn = self.cat_group.checkedButton()
        return btn.property("cat") if btn else "all"

    def refresh(self, update_status: bool = True) -> None:
        if self._special_mode:
            return  # colour/similar result set stays until a new query
        rows = self.db.search(
            text=self.search_box.text(),
            category=self.current_category(),
            favorites_only=self.fav_btn.isChecked(),
            sort=self.sort_combo.currentData() or "name",
        )
        self.model.set_rows(rows)
        if update_status:
            self._update_status(len(rows))
            self._play_fade()

    def _play_fade(self) -> None:
        """Gently fade the grid in when the result set changes."""
        eff = QGraphicsOpacityEffect(self.view)
        self.view.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(170)
        anim.setStartValue(0.25)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self.view.setGraphicsEffect(None))
        self._fade_anim = anim  # keep a reference alive
        anim.start()

    def _update_status(self, shown: int) -> None:
        total = self.db.total_count()
        counts = self.db.counts_by_category()
        parts = [f"{config.CATEGORY_LABELS[c]}: {counts.get(c, 0)}" for c in config.CATEGORY_ORDER if counts.get(c)]
        self.status.setText(f"Showing {shown} of {total} assets    |    " + "   ".join(parts))

    # ----------------------------------------------------------- selection
    def _on_select(self, current, _prev) -> None:
        row = current.data(ROW_ROLE) if current.isValid() else None
        self.detail.set_row(row)
        if row is not None:
            self.detail.set_tags(self.db.tags_for(row["id"]))
            cp = row["cpath"]
            uses = self.db.dependencies(cp, forward=True) if cp else []
            used_in = self.db.dependencies(cp, forward=False) if cp else []
            self.detail.set_dependencies(uses, used_in)

    def navigate_to_asset(self, asset_id: int) -> None:
        row = self.db.get_asset(asset_id)
        if not row:
            return
        self._special_mode = "deps"
        self.model.set_rows([row])
        self.view.setCurrentIndex(self.model.index(0, 0))
        self.status.setText(
            f"Dependency view · {row['name']}   —  clear the search box to exit"
        )

    def _reveal_path(self, path: str) -> None:
        from .detail_panel import reveal_in_folder
        reveal_in_folder(path)

    def _on_double_click(self, index) -> None:
        row = index.data(ROW_ROLE)
        if row is not None:
            from .detail_panel import _os_open
            _os_open(row["path"])

    def _on_context_menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        self.view.setCurrentIndex(index)  # sync selection + detail panel
        row = index.data(ROW_ROLE)
        if row is None:
            return
        from .detail_panel import _os_open

        menu = QMenu(self)
        menu.addAction("Open", lambda: _os_open(row["path"]))
        menu.addAction("Show in folder", self.detail._reveal)
        menu.addSeparator()
        menu.addAction("Copy file", lambda: self._copy_file(row["path"]))
        menu.addAction("Copy path", lambda: QApplication.clipboard().setText(row["path"]))
        menu.addSeparator()
        fav_label = "Remove from favourites" if row["favorite"] else "Add to favourites"
        menu.addAction(fav_label, lambda: self._ctx_favorite(row))
        if row["phash"]:
            menu.addAction("Find similar images", lambda: self.find_similar(row["id"]))
        if row["color_r"] is not None:
            menu.addAction(
                "Search by this colour",
                lambda: self.search_by_color((row["color_r"], row["color_g"], row["color_b"])),
            )
        if row["cpath"]:
            menu.addAction("Show in dependency graph", lambda: self.open_graph(row["cpath"]))
        menu.addAction("Edit tags", lambda: self.detail.tags_edit.setFocus())
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _copy_file(self, path: str) -> None:
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(path)])
        md.setText(path)
        QApplication.clipboard().setMimeData(md)
        self.status.setText(f"Copied to clipboard: {path}")

    def _ctx_favorite(self, row) -> None:
        new_val = not bool(row["favorite"])
        self._on_favorite(row["id"], new_val)
        if self.detail._row is not None and self.detail._row["id"] == row["id"]:
            self.detail.fav_btn.setChecked(new_val)
            self.detail.fav_btn.setText("★ Favourite" if new_val else "☆ Favourite")

    # ------------------------------------------------------------- actions
    def _on_favorite(self, asset_id: int, value: bool) -> None:
        self.db.set_favorite(asset_id, value)
        if self.fav_btn.isChecked():
            self.refresh()

    def _on_tags(self, asset_id: int, tags: list) -> None:
        self.db.set_tags(asset_id, tags)

    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to index")
        if not path:
            return
        if path.rstrip("/\\") in ("C:", "C:/", "D:", "D:/") or len(path.rstrip("/\\")) <= 3:
            from PySide6.QtWidgets import QMessageBox
            ok = QMessageBox.question(
                self, "Index a whole drive?",
                f"“{path}” is an entire drive. Indexing it will crawl system "
                "folders and can take a very long time.\n\nIndex it anyway?",
            )
            if ok != QMessageBox.Yes:
                return
        self.db.add_root(path)
        self._start_scan([path])  # scan only the newly added folder

    def manage_folders(self) -> None:
        from .folders_dialog import FoldersDialog
        dlg = FoldersDialog(self.db, self)
        dlg.exec()
        self._special_mode = None
        self.refresh()

    def show_stats(self) -> None:
        from .detail_panel import reveal_in_folder
        from .stats_dialog import StatsDialog
        StatsDialog(self.db, reveal_in_folder, self).exec()

    def show_duplicates(self) -> None:
        from .detail_panel import _os_open, reveal_in_folder
        from .duplicates_dialog import DuplicatesDialog
        DuplicatesDialog(self.db, _os_open, reveal_in_folder, self).exec()

    def show_graph(self) -> None:
        idx = self.view.currentIndex()
        row = idx.data(ROW_ROLE) if idx.isValid() else None
        if row is None or not row["cpath"]:
            self.status.setText("Select an asset first, then open the graph")
            return
        self.open_graph(row["cpath"])

    def open_graph(self, cpath: str) -> None:
        from .graph_view import GraphDialog
        dlg = GraphDialog(self.db, cpath, self)
        dlg.show_in_app.connect(self.navigate_to_asset)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        self._graph_dialog = dlg  # keep a reference while open
        dlg.show()

    def rescan(self) -> None:
        roots = self.db.roots()
        if not roots:
            self.add_folder()
            return
        self._start_scan(roots)

    def _start_scan(self, roots: list[str]) -> None:
        if self.worker and self.worker.isRunning():
            self.status.setText("A scan is already running…")
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until we know a total
        self._last_scan_refresh = 0
        self.worker = ScanWorker(roots)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self.status.setText)
        self.worker.finished_scan.connect(self._on_scan_done)
        self.worker.start()

    def _on_progress(self, done: int, total: int, path: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)  # still discovering files
        self.status.setText(f"Indexing… {done} files found" + (f"  ·  {path}" if path else ""))
        # stream partial results into the grid so the user sees progress
        if not self._special_mode and done - self._last_scan_refresh >= 250:
            self._last_scan_refresh = done
            self.refresh(update_status=False)

    def _on_scan_done(self, indexed: int, removed: int) -> None:
        self.progress.setVisible(False)
        self._special_mode = None
        self.refresh()
        self.status.setText(f"Scan complete · {indexed} indexed/updated · {removed} removed")

    # -------------------------------------------------- colour / similar
    def pick_color(self) -> None:
        col = QColorDialog.getColor(QColor("#c0392b"), self, "Pick a colour to search")
        if col.isValid():
            self.search_by_color((col.red(), col.green(), col.blue()))

    def search_by_color(self, target) -> None:
        rows = self.db.images_with_color()
        ranked = sorted(
            rows,
            key=lambda r: color_distance(target, (r["color_r"], r["color_g"], r["color_b"])),
        )[:300]
        full = [self.db.get_asset(r["id"]) for r in ranked]
        self.model.set_rows(full)
        self._special_mode = "color"
        self.status.setText(
            f"Colour search rgb({target[0]},{target[1]},{target[2]}) · {len(full)} closest matches"
            "   —  clear the search box or pick a category to exit"
        )

    def find_similar(self, asset_id: int) -> None:
        base = self.db.get_asset(asset_id)
        if not base or not base["phash"]:
            return
        rows = self.db.images_with_phash(exclude_id=asset_id)
        threshold = max(12, int(len(base["phash"]) * 4 * 0.18))  # ~18% of hash bits
        scored = sorted(rows, key=lambda r: hamming(base["phash"], r["phash"]))
        near = [r for r in scored if hamming(base["phash"], r["phash"]) <= threshold][:200]
        full = [base] + [self.db.get_asset(r["id"]) for r in near]
        self.model.set_rows(full)
        self._special_mode = "similar"
        self.status.setText(
            f"{len(near)} images similar to “{base['name']}”"
            "   —  clear the search box or pick a category to exit"
        )

    def closeEvent(self, event):  # noqa: N802
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        self.db.close()
        super().closeEvent(event)
