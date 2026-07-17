"""Background indexing worker: walks roots and populates the database."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import config, imaging
from .database import Database

# Directory names skipped anywhere in the tree (case-insensitive). Keeps a
# whole-disk scan from drowning in OS/system/dev junk.
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "$recycle.bin", ".idea", "venv",
    ".venv", "env", "site-packages", ".cache", ".tox", "dist", "build",
    "windows", "winsxs", "program files", "program files (x86)", "programdata",
    "appdata", "system volume information", "$windows.~bt", "$windows.~ws",
    "recovery", "perflogs", "msocache", "intel", "amd", "nvidia",
}


class ScanWorker(QThread):
    progress = Signal(int, int, str)   # done, total(-0 if unknown), current path
    finished_scan = Signal(int, int)   # indexed, removed
    message = Signal(str)

    def __init__(self, roots: list[str], parent=None):
        super().__init__(parent)
        self.roots = roots
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        db = Database()
        try:
            seen = 0        # matching files encountered
            indexed = 0     # newly indexed or updated
            meta_files: list[str] = []   # Unity *.meta (guid map)
            ref_files: list[str] = []    # files that reference other assets
            # Stream: index each file as it is discovered, committing in
            # batches, so results and progress appear immediately even on
            # enormous trees (no giant up-front file list).
            for root in self.roots:
                if self._cancel:
                    break
                self.message.emit(f"Scanning {root}…")
                for dirpath, dirnames, filenames in os.walk(root):
                    if self._cancel:
                        break
                    dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
                    for fn in filenames:
                        ext = os.path.splitext(fn)[1].lower()
                        path = os.path.join(dirpath, fn)
                        if ext == config.DEP_META_EXT:
                            meta_files.append(path)
                            continue
                        if ext in config.DEP_REF_EXTS:
                            ref_files.append(path)
                        if ext not in config.EXT_TO_CATEGORY:
                            continue
                        seen += 1
                        if seen % 20 == 0:
                            self.progress.emit(seen, 0, path)
                        try:
                            if self._index_one(db, path):
                                indexed += 1
                        except Exception as exc:  # keep going on failures
                            self.message.emit(f"Skip {fn}: {exc}")
                        if seen % 150 == 0:
                            db.commit()
                            self.progress.emit(seen, 0, path)  # nudge the UI
            db.commit()

            # prune deleted files (only when the scan completed, not cancelled)
            removed = 0
            if not self._cancel:
                for root in self.roots:
                    known = db.all_paths_under(root)
                    gone = [p for p in known if not os.path.exists(p)]
                    if gone:
                        db.delete_paths(gone)
                        removed += len(gone)

            # build the asset dependency graph
            if not self._cancel and (meta_files or ref_files):
                self.message.emit("Analysing dependencies…")
                self._build_dependencies(db, meta_files, ref_files)

            self.progress.emit(seen, seen, "")
            self.finished_scan.emit(indexed, removed)
        finally:
            db.close()

    def _build_dependencies(self, db: Database, meta_files: list[str], ref_files: list[str]) -> None:
        from . import dependencies as deps

        # 1) refresh the Unity GUID -> path map
        pairs = []
        for mp in meta_files:
            g = deps.read_meta_guid(mp)
            if g:
                pairs.append((g, mp[: -len(config.DEP_META_EXT)]))
        if pairs:
            db.upsert_guids(pairs)
            db.commit()
        guid_map = db.full_guid_map()

        # 2) rebuild edges originating under the scanned roots
        db.clear_edges_under(self.roots)

        # 3) resolve references into edges
        edges: list[tuple[str, str]] = []
        names: dict[str, str] = {}
        for i, rf in enumerate(ref_files):
            if self._cancel:
                break
            if i % 50 == 0:
                self.progress.emit(i, 0, rf)
            targets = deps.extract_targets(rf, guid_map)
            if not targets:
                continue
            src_c = config.canonical_path(rf)
            names[src_c] = rf
            for t in targets:
                dst_c = config.canonical_path(t)
                names[dst_c] = t
                edges.append((src_c, dst_c))
            if len(edges) > 4000:
                db.add_edges(edges, names)
                db.commit()
                edges, names = [], {}
        if edges:
            db.add_edges(edges, names)
        db.commit()

    def _index_one(self, db: Database, path: str) -> bool:
        st = os.stat(path)
        sig = db.get_signature(path)
        if sig and sig[0] == st.st_size and abs(sig[1] - st.st_mtime) < 1e-6:
            return False  # unchanged

        ext = os.path.splitext(path)[1].lower()
        category = config.category_for_ext(ext)
        name = os.path.basename(path)
        rec: dict = {
            "path": path,
            "name": name,
            "stem": os.path.splitext(name)[0],
            "ext": ext,
            "category": category,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "width": None, "height": None, "duration": None,
            "phash": None, "color_r": None, "color_g": None, "color_b": None,
            "thumb": None, "meta": None,
        }

        if category == "texture" and ext in config.IMAGE_PREVIEW_EXTS:
            self._enrich_image(rec, path)
        elif category == "font":
            self._enrich_font(rec, path)
        elif category in config.AUDIO_CATEGORIES:
            self._enrich_audio(rec, path)

        db.upsert_asset(rec)
        return True

    def _enrich_image(self, rec: dict, path: str) -> None:
        try:
            from PIL import Image
            with Image.open(path) as im:
                rec["width"], rec["height"] = im.size
        except Exception:
            pass
        rec["thumb"] = imaging.make_image_thumbnail(path)
        rec["phash"] = imaging.perceptual_hash(path)
        col = imaging.dominant_color(path)
        if col:
            rec["color_r"], rec["color_g"], rec["color_b"] = col

    def _enrich_font(self, rec: dict, path: str) -> None:
        rec["thumb"] = imaging.make_font_thumbnail(path)
        try:
            from fontTools.ttLib import TTFont
            font = TTFont(path, fontNumber=0, lazy=True)
            family = _name_record(font, 1)
            style = _name_record(font, 2)
            font.close()
            if family:
                rec["meta"] = json.dumps({"family": family, "style": style})
        except Exception:
            pass

    def _enrich_audio(self, rec: dict, path: str) -> None:
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(path)
            if mf is not None:
                if mf.info is not None:
                    rec["duration"] = float(getattr(mf.info, "length", 0.0))
                meta = {}
                for key, tag in (("title", "TIT2"), ("artist", "TPE1"), ("album", "TALB")):
                    val = mf.tags.get(tag) if getattr(mf, "tags", None) else None
                    if val:
                        meta[key] = str(val)
                if meta:
                    rec["meta"] = json.dumps(meta)
        except Exception:
            pass


def _name_record(font, name_id: int) -> str:
    try:
        rec = font["name"].getDebugName(name_id)
        return rec or ""
    except Exception:
        return ""
