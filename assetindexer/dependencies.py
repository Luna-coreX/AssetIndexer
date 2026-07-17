"""Build an asset dependency graph from Unity, Godot, glTF and OBJ/MTL files.

The graph is a set of directed edges  src --uses--> dst  (both stored as
canonical paths).  Unity is GUID-based (robust); the others resolve relative
file paths.
"""
from __future__ import annotations

import json
import os
import re

from . import config

_GUID_RE = re.compile(rb"guid:\s*([0-9a-fA-F]{32})")
_MAX_READ = 80 * 1024 * 1024  # skip absurdly large files

_UNITY_EXTS = {
    ".unity", ".prefab", ".mat", ".asset", ".controller", ".anim",
    ".overridecontroller", ".spriteatlas", ".terrainlayer", ".mask",
}


# ---------------------------------------------------------------------------
# Unity
# ---------------------------------------------------------------------------
def read_meta_guid(meta_path: str) -> str | None:
    try:
        with open(meta_path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    m = _GUID_RE.search(head)
    return m.group(1).decode("ascii").lower() if m else None


def _extract_unity_guids(path: str) -> set[str]:
    try:
        if os.path.getsize(path) > _MAX_READ:
            return set()
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return set()
    return {m.group(1).decode("ascii").lower() for m in _GUID_RE.finditer(data)}


# ---------------------------------------------------------------------------
# OBJ / MTL (Wavefront)
# ---------------------------------------------------------------------------
def _resolve(base_file: str, rel: str) -> str | None:
    rel = rel.strip().strip('"')
    if not rel:
        return None
    cand = os.path.join(os.path.dirname(base_file), rel)
    return cand if os.path.exists(cand) else None


def _extract_obj(path: str) -> set[str]:
    out: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("mtllib"):
                    for token in line.split()[1:]:
                        p = _resolve(path, token)
                        if p:
                            out.add(p)
    except OSError:
        pass
    return out


_MTL_MAP_KEYS = ("map_kd", "map_ka", "map_ks", "map_ke", "map_bump", "bump",
                 "map_d", "disp", "decal", "norm", "map_pr", "map_pm")


def _extract_mtl(path: str) -> set[str]:
    out: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                low = line.strip().lower()
                if low.split(" ", 1)[0] in _MTL_MAP_KEYS:
                    token = line.split()[-1]  # last token is the filename
                    p = _resolve(path, token)
                    if p:
                        out.add(p)
    except OSError:
        pass
    return out


# ---------------------------------------------------------------------------
# glTF (JSON)
# ---------------------------------------------------------------------------
def _extract_gltf(path: str) -> set[str]:
    out: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    for key in ("buffers", "images"):
        for item in data.get(key, []) or []:
            uri = item.get("uri", "") if isinstance(item, dict) else ""
            if uri and not uri.startswith("data:"):
                from urllib.parse import unquote
                p = _resolve(path, unquote(uri))
                if p:
                    out.add(p)
    return out


# ---------------------------------------------------------------------------
# Godot (.tscn / .tres / .escn)
# ---------------------------------------------------------------------------
_GODOT_RES_RE = re.compile(r'path\s*=\s*"res://([^"]+)"')


def _find_godot_root(path: str) -> str | None:
    d = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(d, "project.godot")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _extract_godot(path: str) -> set[str]:
    root = _find_godot_root(path)
    if not root:
        return set()
    out: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return out
    for rel in _GODOT_RES_RE.findall(text):
        cand = os.path.join(root, rel)
        if os.path.exists(cand):
            out.add(cand)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def extract_targets(ref_path: str, guid_map: dict[str, str]) -> set[str]:
    """Return the set of file paths that `ref_path` directly references."""
    ext = os.path.splitext(ref_path)[1].lower()
    targets: set[str] = set()
    if ext in _UNITY_EXTS:
        for g in _extract_unity_guids(ref_path):
            tgt = guid_map.get(g)
            if tgt and config.canonical_path(tgt) != config.canonical_path(ref_path):
                targets.add(tgt)
    elif ext == ".obj":
        targets |= _extract_obj(ref_path)
    elif ext == ".mtl":
        targets |= _extract_mtl(ref_path)
    elif ext == ".gltf":
        targets |= _extract_gltf(ref_path)
    elif ext in (".tscn", ".tres", ".escn"):
        targets |= _extract_godot(ref_path)
    return targets
