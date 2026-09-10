"""
Split a sheet of rubber-stamp impressions into one transparent PNG each.

The generator returns a row of stamps on a flat cream field. Each one is cut
out the same way the aircraft are — alpha from distance to the measured cream,
speckle removed by an erode/over-dilate pass — and then the row is divided at
the empty columns between impressions rather than at fixed fractions, so it
does not matter whether the generator spaced them evenly.

The ink keeps its own colour; the page tints nothing, so the green, red and
near-black the stamps were drawn in are what appear on screen.

Usage:  python tools/make_stamps.py <folder-with-the-sheets>
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = (Path(__file__).resolve().parent.parent
       / "korea_service_record" / "static" / "images" / "stamps")

# Sheet -> the names of the impressions on it, left to right. The status words
# match pilot.state; the classification names match the country's language.
SHEETS = {
    "status_stamps": ["active", "wounded", "kia"],
    "confidential_stamps": ["eng", "rus", "chi", "kor"],
}

TARGET_H = 220          # tall enough for the table and the corner overlay
COLOURS = 96            # single-ink impressions: the palette barely matters


def alpha_of(path: Path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    corners = np.concatenate([a[:12, :12].reshape(-1, 3), a[:12, -12:].reshape(-1, 3),
                              a[-12:, :12].reshape(-1, 3), a[-12:, -12:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    dist = np.abs(a - bg).max(axis=2)
    alpha = np.clip((dist - 5.0) / 26.0, 0.0, 1.0)

    mask = Image.fromarray((alpha * 255).astype(np.uint8))
    keep = (mask.filter(ImageFilter.MinFilter(5))
                .filter(ImageFilter.MaxFilter(11))
                .filter(ImageFilter.GaussianBlur(2)))
    alpha = alpha * np.clip(np.asarray(keep).astype(np.float32) / 255.0 * 1.6, 0, 1)
    return a, alpha


def columns_of_ink(alpha: np.ndarray, count: int):
    """The horizontal span of each impression, split at the empty columns."""
    ink = (alpha > 0.3).sum(axis=0)
    # A column counts as blank when it is almost empty; a stamp's distressed
    # border leaves a few stray pixels, so this is a threshold, not zero.
    blank = ink <= max(1, int(alpha.shape[0] * 0.002))
    spans, start = [], None
    for x, is_blank in enumerate(blank):
        if not is_blank and start is None:
            start = x
        elif is_blank and start is not None:
            spans.append((start, x))
            start = None
    if start is not None:
        spans.append((start, len(blank)))
    # Merge the small gaps inside a stamp; keep the big ones between them.
    merged = [spans[0]]
    for lo, hi in spans[1:]:
        if lo - merged[-1][1] < alpha.shape[1] * 0.02:
            merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    merged = [s for s in merged if s[1] - s[0] > alpha.shape[1] * 0.02]
    if len(merged) != count:
        raise ValueError(f"found {len(merged)} impressions, expected {count}")
    return merged


def main(folder: str) -> int:
    src_dir = Path(folder)
    OUT.mkdir(parents=True, exist_ok=True)
    for sheet, names in SHEETS.items():
        src = src_dir / f"{sheet}.png"
        if not src.is_file():
            print(f"  {sheet}: not found")
            continue
        rgb, alpha = alpha_of(src)
        spans = columns_of_ink(alpha, len(names))
        print(f"  {sheet}: {len(spans)} impressions")
        for (lo, hi), name in zip(spans, names):
            band = alpha[:, lo:hi]
            rows = np.where((band > 0.3).any(axis=1))[0]
            top, bot = int(rows.min()), int(rows.max()) + 1
            piece = np.dstack([rgb[top:bot, lo:hi], alpha[top:bot, lo:hi] * 255.0])
            img = Image.fromarray(piece.astype(np.uint8), "RGBA")
            scale = TARGET_H / img.height
            img = img.resize((max(1, round(img.width * scale)), TARGET_H), Image.LANCZOS)
            dst = OUT / f"{name}.png"
            img.quantize(colors=COLOURS, method=Image.FASTOCTREE).save(dst, optimize=True)
            print(f"     {name:<8} {img.size[0]:>4}x{img.size[1]:<4} "
                  f"{dst.stat().st_size // 1024:3d} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1
                          else str(Path.home() / "Downloads")))
