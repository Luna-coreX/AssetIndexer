"""Configuration: file-type categories, extension mapping, and app paths."""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Categories and their file extensions (lowercase, with leading dot).
# ---------------------------------------------------------------------------
CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "texture": {
        ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp",
        ".gif", ".dds", ".exr", ".hdr", ".psd", ".svg", ".ktx", ".ktx2",
    },
    "model": {
        ".obj", ".fbx", ".gltf", ".glb", ".blend", ".dae", ".3ds", ".stl",
        ".ply", ".usd", ".usda", ".usdc", ".usdz", ".max", ".ma", ".mb",
        ".c4d", ".abc", ".x3d",
    },
    "music": {
        ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wma", ".aac", ".alac",
    },
    "sound": {
        ".wav", ".aiff", ".aif", ".aifc", ".caf",
    },
    "font": {
        ".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc", ".fon", ".pfb",
    },
    "document": {
        ".pdf", ".txt", ".md", ".rst", ".doc", ".docx", ".rtf", ".odt",
        ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp", ".csv", ".json",
        ".xml", ".html", ".htm", ".epub", ".tex", ".yaml", ".yml", ".ini",
    },
    # engine / scene / material files (Unity, Godot, Wavefront) — these mostly
    # reference other assets, so they anchor the dependency graph.
    "project": {
        ".unity", ".prefab", ".mat", ".asset", ".controller", ".anim",
        ".overridecontroller", ".spriteatlas", ".terrainlayer", ".mask",
        ".tscn", ".tres", ".escn", ".mtl",
    },
}

# Reverse lookup: extension -> category.
EXT_TO_CATEGORY: dict[str, str] = {
    ext: cat for cat, exts in CATEGORY_EXTENSIONS.items() for ext in exts
}

# Extensions we can render an image thumbnail from directly (via Pillow).
IMAGE_PREVIEW_EXTS: set[str] = {
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp",
    ".gif", ".ppm", ".ico",
}

AUDIO_CATEGORIES = {"music", "sound"}

CATEGORY_ORDER = ["texture", "model", "music", "sound", "font", "document", "project", "other"]

CATEGORY_LABELS = {
    "texture": "Textures",
    "model": "Models",
    "music": "Music",
    "sound": "Sounds",
    "font": "Fonts",
    "document": "Documents",
    "project": "Project",
    "other": "Other",
}

# Emoji-ish glyph fallbacks used when no image thumbnail is available.
CATEGORY_GLYPHS = {
    "texture": "🖼",
    "model": "◈",
    "music": "♪",
    "sound": "🔊",
    "font": "A",
    "document": "📄",
    "project": "⬡",
    "other": "•",
}


def category_for_ext(ext: str) -> str:
    return EXT_TO_CATEGORY.get(ext.lower(), "other")


# ---------------------------------------------------------------------------
# Dependency-graph inputs. `.meta` files (Unity) map asset paths to GUIDs;
# reference files contain references to other assets that we resolve into edges.
# ---------------------------------------------------------------------------
DEP_META_EXT = ".meta"
DEP_REF_EXTS: set[str] = {
    # Unity YAML assets
    ".unity", ".prefab", ".mat", ".asset", ".controller", ".anim",
    ".overridecontroller", ".spriteatlas", ".terrainlayer", ".mask",
    # Godot scenes / resources
    ".tscn", ".tres", ".escn",
    # Wavefront / glTF
    ".obj", ".mtl", ".gltf",
}


def canonical_path(path: str) -> str:
    """Normalised absolute path for matching across resolvers and the index."""
    return os.path.normcase(os.path.abspath(path))


# ---------------------------------------------------------------------------
# Application data directory (database + thumbnail cache).
# ---------------------------------------------------------------------------
def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = Path(base) / "AssetIndexer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "index.db"


def thumbs_dir() -> Path:
    d = data_dir() / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


THUMB_SIZE = 256  # px, longest edge of cached thumbnails
GRID_ICON_SIZE = 160  # px, displayed icon size in the grid
