"""
Cut an object out of a flat photographic background.

    python tools/cut_out.py <in.png> <out.png> [--thresh 45]

For artwork that arrives without an alpha channel — a ribbon bar photographed
on studio card, say. Flood-fills from the four corners over everything within
`thresh` of that corner's colour, so only background *connected to the edge*
is removed: a gold highlight in the middle of the emblem that happens to be
near beige is never touched, because the fill cannot reach it. The result is
then feathered by a pixel so the cut edge is not a staircase.

Prints how much was removed, so a fill that broke through into the object
(too high a threshold) or barely started (too low) is obvious from the number.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SENTINEL = (255, 0, 255)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--thresh", type=int, default=45,
                    help="max per-channel distance from the corner colour to "
                         "count as background")
    args = ap.parse_args()

    img = Image.open(args.src).convert("RGB")
    w, h = img.size
    work = img.copy()
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if work.getpixel((x, y)) != SENTINEL:
            ImageDraw.floodfill(work, (x, y), SENTINEL, thresh=args.thresh)

    a = np.asarray(work)
    bg = np.all(a == SENTINEL, axis=2)
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    # A one-pixel feather: the fill's edge is binary, and a hard edge shimmers
    # once the atlas is filtered. clean_alpha in add_award_art.py then treats
    # the feathered rim exactly as it treats a generator's antialiasing.
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))

    out = img.convert("RGBA")
    out.putalpha(alpha)
    out.save(args.dst)
    print(f"  {w}x{h}: {bg.mean() * 100:.1f}% removed as background "
          f"(corners {[img.getpixel(p) for p in ((0, 0), (w - 1, h - 1))]})")
    print(f"  -> {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
