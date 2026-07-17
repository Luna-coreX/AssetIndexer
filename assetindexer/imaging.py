"""Image analysis: thumbnails, perceptual hashing, dominant colour, font previews."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

Image.MAX_IMAGE_PIXELS = None  # allow large textures; we downscale immediately


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------
def _thumb_path(src: str) -> Path:
    digest = hashlib.sha1(src.encode("utf-8", "surrogatepass")).hexdigest()
    return config.thumbs_dir() / f"{digest}.png"


def make_image_thumbnail(src: str) -> Optional[str]:
    """Create (and cache) a thumbnail for an image file. Returns the thumb path."""
    out = _thumb_path(src)
    if out.exists():
        return str(out)
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
            im.thumbnail((config.THUMB_SIZE, config.THUMB_SIZE), Image.LANCZOS)
            bg = Image.new("RGB", im.size, (43, 45, 51))
            if im.mode == "RGBA":
                bg.paste(im, mask=im.split()[-1])
            else:
                bg.paste(im)
            bg.save(out, "PNG")
        return str(out)
    except Exception:
        return None


def make_font_thumbnail(src: str) -> Optional[str]:
    """Render a small specimen of the font as a thumbnail."""
    out = _thumb_path(src)
    if out.exists():
        return str(out)
    try:
        canvas = Image.new("RGB", (config.THUMB_SIZE, config.THUMB_SIZE), (43, 45, 51))
        draw = ImageDraw.Draw(canvas)
        try:
            big = ImageFont.truetype(src, 108)
            small = ImageFont.truetype(src, 30)
        except Exception:
            big = ImageFont.truetype(src, 90, index=0)
            small = ImageFont.truetype(src, 26, index=0)
        draw.text((config.THUMB_SIZE / 2, 96), "Ag", font=big, fill=(235, 235, 240), anchor="mm")
        draw.text(
            (config.THUMB_SIZE / 2, 190),
            "abcdef\n123456",
            font=small, fill=(150, 200, 255), anchor="mm", align="center",
        )
        canvas.save(out, "PNG")
        return str(out)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Perceptual hash (dHash, 64-bit) — robust for "find similar images"
# ---------------------------------------------------------------------------
def perceptual_hash(src: str) -> Optional[str]:
    """128-bit difference hash (horizontal + vertical gradients)."""
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("L").resize((9, 9), Image.LANCZOS)
            px = np.asarray(im, dtype=np.int16)
        horiz = px[:8, 1:] > px[:8, :-1]   # 8x8
        vert = px[1:, :8] > px[:-1, :8]    # 8x8
        bits = 0
        for b in np.concatenate([horiz.flatten(), vert.flatten()]):
            bits = (bits << 1) | int(b)
        return f"{bits:032x}"
    except Exception:
        return None


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# ---------------------------------------------------------------------------
# Dominant colour (robust via palette quantisation)
# ---------------------------------------------------------------------------
def dominant_color(src: str) -> Optional[tuple[int, int, int]]:
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((96, 96), Image.LANCZOS)
            pal = im.quantize(colors=6, method=Image.MEDIANCUT)
            palette = pal.getpalette()
            counts = pal.getcolors()  # list of (count, palette_index)
        if not counts:
            return None
        counts.sort(reverse=True)
        # skip near-white / near-black backgrounds when a colourful option exists
        for count, idx in counts:
            r, g, b = palette[idx * 3: idx * 3 + 3]
            if 18 < (r + g + b) / 3 < 240:
                return (r, g, b)
        count, idx = counts[0]
        return tuple(palette[idx * 3: idx * 3 + 3])  # type: ignore[return-value]
    except Exception:
        return None


def color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    # weighted RGB approximation of perceptual distance
    rmean = (c1[0] + c2[0]) / 2
    dr, dg, db = c1[0] - c2[0], c1[1] - c2[1], c1[2] - c2[2]
    return ((2 + rmean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rmean) / 256) * db * db) ** 0.5
