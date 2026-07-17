"""SQLite storage layer: schema, upserts, search, tags and favorites."""
from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (
    id       INTEGER PRIMARY KEY,
    path     TEXT UNIQUE NOT NULL,
    added_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id         INTEGER PRIMARY KEY,
    path       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    stem       TEXT NOT NULL,
    ext        TEXT NOT NULL,
    category   TEXT NOT NULL,
    size       INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    width      INTEGER,
    height     INTEGER,
    duration   REAL,
    phash      TEXT,
    color_r    INTEGER,
    color_g    INTEGER,
    color_b    INTEGER,
    favorite   INTEGER NOT NULL DEFAULT 0,
    thumb      TEXT,
    meta       TEXT,
    indexed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite);
CREATE INDEX IF NOT EXISTS idx_assets_stem     ON assets(stem);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_tags (
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (asset_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
    name, tags
);

-- dependency graph -------------------------------------------------------
CREATE TABLE IF NOT EXISTS unity_guids (
    guid TEXT PRIMARY KEY,
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dep_edges (
    src TEXT NOT NULL,   -- canonical path of the referencing file
    dst TEXT NOT NULL,   -- canonical path of the referenced asset
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_dep_dst ON dep_edges(dst);
CREATE TABLE IF NOT EXISTS dep_names (
    cpath TEXT PRIMARY KEY,  -- canonical path
    path  TEXT NOT NULL      -- real (display) path
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def searchable_text(name: str) -> str:
    """Split a filename into searchable words: camelCase, digit and separator
    boundaries all become spaces so "MetalFloor01_Normal" matches "floor"."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    s = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", s)
    s = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", s)
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return (name + " " + s).lower().strip()


class Database:
    """Thread-affine SQLite wrapper. Create one instance per thread."""

    def __init__(self, path: Optional[Path] = None):
        self.path = str(path or config.db_path())
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        # add canonical-path column to existing databases
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(assets)")}
        if "cpath" not in cols:
            self.conn.execute("ALTER TABLE assets ADD COLUMN cpath TEXT")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_cpath ON assets(cpath)")
        # backfill any missing canonical paths
        missing = self.conn.execute("SELECT id, path FROM assets WHERE cpath IS NULL").fetchall()
        for row in missing:
            self.conn.execute(
                "UPDATE assets SET cpath=? WHERE id=?",
                (config.canonical_path(row["path"]), row["id"]),
            )

    def close(self) -> None:
        self.conn.close()

    # -- settings -----------------------------------------------------------
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- roots --------------------------------------------------------------
    def add_root(self, path: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO roots(path, added_at) VALUES(?, ?)",
            (path, time.time()),
        )
        self.conn.commit()

    def remove_root(self, path: str) -> int:
        """Remove a root and delete its assets that no remaining root covers.
        Returns the number of assets pruned."""
        self.conn.execute("DELETE FROM roots WHERE path=?", (path,))
        remaining = self.roots()
        prefix = path.rstrip("/\\")
        candidates = self.all_paths_under(prefix)
        to_delete = []
        for p in candidates:
            if not any(p.startswith(r.rstrip("/\\") + os.sep) or p.startswith(r.rstrip("/\\") + "/")
                       for r in remaining):
                to_delete.append(p)
        self.delete_paths(to_delete)
        self.conn.commit()
        return len(to_delete)

    def roots(self) -> list[str]:
        return [r["path"] for r in self.conn.execute("SELECT path FROM roots ORDER BY path")]

    # -- indexing -----------------------------------------------------------
    def get_signature(self, path: str) -> Optional[tuple[int, float]]:
        row = self.conn.execute(
            "SELECT size, mtime FROM assets WHERE path=?", (path,)
        ).fetchone()
        return (row["size"], row["mtime"]) if row else None

    def upsert_asset(self, rec: dict[str, Any]) -> int:
        cols = (
            "path", "cpath", "name", "stem", "ext", "category", "size", "mtime",
            "width", "height", "duration", "phash", "color_r", "color_g",
            "color_b", "thumb", "meta", "indexed_at",
        )
        rec["cpath"] = config.canonical_path(rec["path"])
        rec.setdefault("indexed_at", time.time())
        values = [rec.get(c) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "path")
        cur = self.conn.execute(
            f"INSERT INTO assets({','.join(cols)}) VALUES({placeholders}) "
            f"ON CONFLICT(path) DO UPDATE SET {updates}",
            values,
        )
        row = self.conn.execute("SELECT id FROM assets WHERE path=?", (rec["path"],)).fetchone()
        asset_id = row["id"]
        # keep FTS row in sync (name + existing tags)
        self._reindex_fts(asset_id)
        return asset_id

    def _reindex_fts(self, asset_id: int) -> None:
        row = self.conn.execute("SELECT name FROM assets WHERE id=?", (asset_id,)).fetchone()
        if not row:
            return
        tags = " ".join(self.tags_for(asset_id))
        self.conn.execute("DELETE FROM assets_fts WHERE rowid=?", (asset_id,))
        self.conn.execute(
            "INSERT INTO assets_fts(rowid, name, tags) VALUES(?, ?, ?)",
            (asset_id, searchable_text(row["name"]), tags),
        )

    def commit(self) -> None:
        self.conn.commit()

    def all_paths_under(self, root: str) -> set[str]:
        like = root.rstrip("/\\") + "%"
        return {
            r["path"]
            for r in self.conn.execute("SELECT path FROM assets WHERE path LIKE ?", (like,))
        }

    def delete_paths(self, paths: Iterable[str]) -> None:
        for p in paths:
            row = self.conn.execute("SELECT id FROM assets WHERE path=?", (p,)).fetchone()
            if row:
                self.conn.execute("DELETE FROM assets_fts WHERE rowid=?", (row["id"],))
                self.conn.execute("DELETE FROM assets WHERE id=?", (row["id"],))
        self.conn.commit()

    # -- favorites ----------------------------------------------------------
    def set_favorite(self, asset_id: int, value: bool) -> None:
        self.conn.execute("UPDATE assets SET favorite=? WHERE id=?", (1 if value else 0, asset_id))
        self.conn.commit()

    # -- tags ---------------------------------------------------------------
    def tags_for(self, asset_id: int) -> list[str]:
        return [
            r["name"]
            for r in self.conn.execute(
                "SELECT t.name FROM tags t JOIN asset_tags a ON a.tag_id=t.id "
                "WHERE a.asset_id=? ORDER BY t.name",
                (asset_id,),
            )
        ]

    def set_tags(self, asset_id: int, tags: list[str]) -> None:
        clean = sorted({t.strip().lower() for t in tags if t.strip()})
        self.conn.execute("DELETE FROM asset_tags WHERE asset_id=?", (asset_id,))
        for name in clean:
            self.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
            tid = self.conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
            self.conn.execute(
                "INSERT OR IGNORE INTO asset_tags(asset_id, tag_id) VALUES(?, ?)",
                (asset_id, tid),
            )
        self._reindex_fts(asset_id)
        self.conn.commit()

    def all_tags(self) -> list[str]:
        return [r["name"] for r in self.conn.execute("SELECT name FROM tags ORDER BY name")]

    # -- queries ------------------------------------------------------------
    def get_asset(self, asset_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()

    def counts_by_category(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT category, COUNT(*) c FROM assets GROUP BY category")
        return {r["category"]: r["c"] for r in rows}

    def total_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM assets").fetchone()["c"]

    def search(
        self,
        text: str = "",
        category: Optional[str] = None,
        favorites_only: bool = False,
        sort: str = "name",
        limit: int = 2000,
    ) -> list[sqlite3.Row]:
        """Text + filter search. Uses FTS5 when text is present."""
        params: list[Any] = []
        where: list[str] = []
        join = ""

        if text.strip():
            join = "JOIN assets_fts f ON f.rowid = a.id"
            where.append("assets_fts MATCH ?")
            params.append(_fts_query(text))

        if category and category != "all":
            where.append("a.category = ?")
            params.append(category)
        if favorites_only:
            where.append("a.favorite = 1")

        order = {
            "name": "a.stem COLLATE NOCASE ASC",
            "newest": "a.mtime DESC",
            "size": "a.size DESC",
        }.get(sort, "a.stem COLLATE NOCASE ASC")

        # When searching text, FTS relevance can be a secondary sort key.
        sql = f"SELECT a.* FROM assets a {join}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order} LIMIT ?"
        params.append(limit)
        return list(self.conn.execute(sql, params))

    def images_with_phash(self, exclude_id: Optional[int] = None) -> list[sqlite3.Row]:
        sql = ("SELECT id, name, path, phash, thumb, category, size, "
               "color_r, color_g, color_b FROM assets WHERE phash IS NOT NULL")
        params: list[Any] = []
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return list(self.conn.execute(sql, params))

    def stats(self) -> dict[str, Any]:
        cur = self.conn
        total_n = cur.execute("SELECT COUNT(*) c FROM assets").fetchone()["c"]
        total_sz = cur.execute("SELECT COALESCE(SUM(size),0) s FROM assets").fetchone()["s"]
        per_cat = {
            r["category"]: {"count": r["c"], "size": r["s"]}
            for r in cur.execute(
                "SELECT category, COUNT(*) c, COALESCE(SUM(size),0) s "
                "FROM assets GROUP BY category"
            )
        }
        largest = list(cur.execute(
            "SELECT name, path, size, category FROM assets ORDER BY size DESC LIMIT 12"
        ))
        favourites = cur.execute("SELECT COUNT(*) c FROM assets WHERE favorite=1").fetchone()["c"]
        tags = cur.execute("SELECT COUNT(*) c FROM tags").fetchone()["c"]
        exts = list(cur.execute(
            "SELECT ext, COUNT(*) c FROM assets GROUP BY ext ORDER BY c DESC LIMIT 8"
        ))
        return {
            "total_count": total_n, "total_size": total_sz, "per_category": per_cat,
            "largest": largest, "favourites": favourites, "tags": tags, "top_exts": exts,
        }

    def images_with_color(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT id, name, path, thumb, category, color_r, color_g, color_b "
                "FROM assets WHERE color_r IS NOT NULL"
            )
        )

    # -- dependency graph ---------------------------------------------------
    def upsert_guids(self, pairs: list[tuple[str, str]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO unity_guids(guid, path) VALUES(?, ?)", pairs
        )

    def full_guid_map(self) -> dict[str, str]:
        return {r["guid"]: r["path"] for r in self.conn.execute("SELECT guid, path FROM unity_guids")}

    def clear_edges_under(self, roots: list[str]) -> None:
        for root in roots:
            like = config.canonical_path(root).rstrip("/\\") + os.sep + "%"
            self.conn.execute("DELETE FROM dep_edges WHERE src LIKE ?", (like,))

    def add_edges(self, edges: list[tuple[str, str]], names: dict[str, str]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO dep_edges(src, dst) VALUES(?, ?)", edges
        )
        self.conn.executemany(
            "INSERT OR REPLACE INTO dep_names(cpath, path) VALUES(?, ?)",
            list(names.items()),
        )

    def get_asset_by_cpath(self, cpath: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM assets WHERE cpath=?", (cpath,)).fetchone()

    def _dep_neighbors(self, cpath: str, forward: bool) -> list[str]:
        if forward:
            rows = self.conn.execute("SELECT dst FROM dep_edges WHERE src=?", (cpath,))
        else:
            rows = self.conn.execute("SELECT src FROM dep_edges WHERE dst=?", (cpath,))
        return [r[0] for r in rows]

    def dependencies(self, cpath: str, forward: bool, cap: int = 300) -> list[dict]:
        """Transitive BFS over the dependency graph. `forward=True` -> "uses";
        `forward=False` -> "used in". Direct references get depth 1."""
        from collections import deque

        seen: dict[str, int] = {cpath: 0}
        order: list[tuple[str, int]] = []
        queue: deque[str] = deque([cpath])
        while queue:
            cur = queue.popleft()
            for nb in self._dep_neighbors(cur, forward):
                if nb not in seen:
                    seen[nb] = seen[cur] + 1
                    order.append((nb, seen[nb]))
                    queue.append(nb)
                    if len(order) >= cap:
                        queue.clear()
                        break

        name_rows = {r["cpath"]: r["path"] for r in self.conn.execute("SELECT cpath, path FROM dep_names")}
        result: list[dict] = []
        for cp, depth in order:
            asset = self.get_asset_by_cpath(cp)
            disp = asset["path"] if asset else name_rows.get(cp, cp)
            result.append({
                "cpath": cp,
                "path": disp,
                "name": os.path.basename(disp),
                "depth": depth,
                "asset_id": asset["id"] if asset else None,
                "category": asset["category"] if asset else config.category_for_ext(
                    os.path.splitext(disp)[1]),
            })
        result.sort(key=lambda d: (d["depth"], d["name"].lower()))
        return result

    def dependency_subgraph(self, cpath: str, hops: int = 2, cap: int = 80) -> tuple[dict, list, bool]:
        """Neighbourhood around `cpath`: BFS `hops` steps both directions,
        capped at `cap` nodes. Returns (node_meta_by_cpath, edges, truncated)."""
        nodes: set[str] = {cpath}
        frontier: set[str] = {cpath}
        truncated = False
        for _ in range(max(1, hops)):
            nxt: set[str] = set()
            for cp in frontier:
                nxt.update(self._dep_neighbors(cp, True))
                nxt.update(self._dep_neighbors(cp, False))
            nxt -= nodes
            for cp in nxt:
                if len(nodes) >= cap:
                    truncated = True
                    break
                nodes.add(cp)
            frontier = nxt & nodes
            if truncated:
                break

        edges = [
            (r["src"], r["dst"])
            for r in self.conn.execute("SELECT src, dst FROM dep_edges")
            if r["src"] in nodes and r["dst"] in nodes
        ]
        name_rows = {r["cpath"]: r["path"] for r in self.conn.execute("SELECT cpath, path FROM dep_names")}
        metas: dict[str, dict] = {}
        for cp in nodes:
            asset = self.get_asset_by_cpath(cp)
            disp = asset["path"] if asset else name_rows.get(cp, cp)
            metas[cp] = {
                "cpath": cp,
                "path": disp,
                "name": os.path.basename(disp),
                "asset_id": asset["id"] if asset else None,
                "category": asset["category"] if asset else config.category_for_ext(
                    os.path.splitext(disp)[1]),
                "thumb": asset["thumb"] if asset else None,
            }
        return metas, edges, truncated


def _fts_query(text: str) -> str:
    """Turn free text into a forgiving FTS5 prefix query."""
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in text).split() if t]
    if not tokens:
        return '""'
    return " ".join(f'"{t}"*' for t in tokens)
