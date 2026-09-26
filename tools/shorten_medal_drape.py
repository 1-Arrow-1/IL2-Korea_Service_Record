"""
Take ribbon cloth off the top of every drawn medal, so the medal is a
larger share of its drape.

    python tools/shorten_medal_drape.py <rows> [--dry-run] [--sheet out.png]

The full-size medals on the dress coat are composed from bases in
``static/images/medals``: a drape ``medals.DRAPE`` wide and tall, with the
ribbon full-width at the top, the devices laid over its first
``DRAPE_LENGTH`` rows, and the medal hanging below. The ribbon was drawn
long, and against it the medal reads small.

Cloth is taken from the *top*, never from the medal. Scaling the pendant up
instead is not open to us: several are already the full width of the drape,
so there is nowhere sideways for them to go, and stretching the canvas back
to height after a crop would only distort them. Cutting the ribbon is also
what a mounter does - the drop is shortened at the bar, not at the medal.

``DRAPE`` and ``DRAPE_LENGTH`` must come down by the same number of rows, or
the devices would be centred over cloth that is no longer there. This script
reports the new values; medals.py is edited by hand so the change shows in
the diff rather than hiding in a generated constant.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record import medals                       # noqa: E402

ART = REPO / "korea_service_record" / "static" / "images" / "medals"

# How tall a row of devices runs on the drape. Clusters are the big ones;
# this is the height that has to sit on solid cloth.
DEVICE_H = 60


def solid_ribbon(img) -> int:
    """
    The last row where the ribbon still runs its own full width.

    Measured against the widest the picture gets, not against the canvas:
    the Navy Cross ribbon is 208 across on a 224 drape, and a test against
    the canvas says it is never solid at all.
    """
    import numpy as np

    opaque = np.asarray(img.convert("RGBA"))[..., 3] > 100
    widths = opaque.sum(axis=1)
    if not widths.max():
        return 0
    full = np.where(widths >= 0.95 * widths.max())[0]
    return int(full.max()) if len(full) else 0


def max_crop(solid: int) -> int:
    """
    The deepest cut this picture can take.

    After cutting c rows the device zone is ``DRAPE_LENGTH - c`` and the
    cloth runs to ``solid - c``. A device row is centred in the zone, so its
    bottom edge falls at ``(DRAPE_LENGTH - c + DEVICE_H) / 2``, and that has
    to stay on the cloth.
    """
    return int(2 * solid - medals.DRAPE_LENGTH - DEVICE_H)


def main() -> int:
    from PIL import Image

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rows", type=int, help="rows of ribbon to remove from the top")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="comma-separated stems, default every drawn base")
    ap.add_argument("--sheet", type=Path)
    args = ap.parse_args()

    wanted = set(args.only.split(",")) if args.only else None
    bases = [p for p in sorted(ART.glob("[0-9]*.png"))
             if p.stem.isdigit() and (wanted is None or p.stem in wanted)]

    pairs, worst, worst_who = [], None, None
    for path in bases:
        img = Image.open(path).convert("RGBA")
        if img.size != medals.DRAPE:
            img = img.resize(medals.DRAPE, Image.LANCZOS)
        solid = solid_ribbon(img)
        allowed = max_crop(solid)
        if worst is None or allowed < worst:
            worst, worst_who = allowed, path.stem
        out = img.crop((0, args.rows, img.width, img.height))
        flag = "" if args.rows <= allowed else "   <- devices would overhang"
        print(f"  {path.stem}: cloth solid to {solid:3d}, takes up to {allowed:3d} rows{flag}")
        pairs.append((path.stem, img, out))
        if not args.dry_run:
            out.save(path, optimize=True)

    print(f"\ndeepest cut every picture can take: {worst} rows ({worst_who})")
    if args.rows > worst:
        print(f"asked for {args.rows}")
    print(f"then in medals.py:  DRAPE = ({medals.DRAPE[0]}, {medals.DRAPE[1] - args.rows})"
          f"   DRAPE_LENGTH = {medals.DRAPE_LENGTH - args.rows}")

    if args.sheet and pairs:
        from PIL import ImageDraw
        cell, pad, per_row, label = medals.DRAPE[0], 14, 6, 20
        cols = min(per_row, len(pairs))
        nrows = (len(pairs) + per_row - 1) // per_row
        pw, h = cell * 2 + pad, medals.DRAPE[1]
        sheet = Image.new("RGBA", (cols * (pw + pad) + pad,
                                   nrows * (h + label + pad) + pad), (242, 236, 220, 255))
        draw = ImageDraw.Draw(sheet)
        for i, (name, before, after) in enumerate(pairs):
            cx = pad + (i % per_row) * (pw + pad)
            cy = pad + (i // per_row) * (h + label + pad)
            draw.text((cx, cy + 3), f"{name}  before | after", fill=(90, 70, 40, 255))
            sheet.alpha_composite(before, (cx, cy + label))
            sheet.alpha_composite(after, (cx + cell + pad, cy + label))
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(args.sheet)
        print(f"Sheet: {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
