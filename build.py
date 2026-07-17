import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "AssetIndexer"

ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / f"{PROJECT_NAME}.spec"

MAIN = ROOT / "main.py"
ICON = ROOT / "build_assets" / "icon.png"      # если появится
VERSION = ROOT / "version_info.txt"      # если появится

# -----------------------------------------

for p in (DIST, BUILD):
    if p.exists():
        shutil.rmtree(p)

if SPEC.exists():
    SPEC.unlink()

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",

    str(MAIN),

    "--noconfirm",
    "--clean",

    "--windowed",
    "--onefile",

    "--name",
    PROJECT_NAME,

    "--collect-all", "PySide6",
    "--collect-submodules", "assetindexer",

    "--hidden-import", "sqlite3",
    "--hidden-import", "PIL",
    "--hidden-import", "imagehash",
    "--hidden-import", "networkx",

    "--optimize", "2",
]

if ICON.exists():
    cmd += ["--icon", str(ICON)]

if VERSION.exists():
    cmd += ["--version-file", str(VERSION)]

subprocess.run(cmd, check=True)

print()
print("=" * 60)
print("Build complete!")
print(DIST / f"{PROJECT_NAME}.exe")
print("=" * 60)