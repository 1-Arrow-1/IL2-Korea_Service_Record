"""
Bring a drawn medal base back in step with the game's atlas.

    python tools/refresh_medal_art.py 601008 601018 [--dry-run] [--sheet out.png]

The full-size medals on the record and the dress tunic are composed by
``medals.MedalRenderer`` from bases in ``static/images/medals``: a 224x474
drape with the ribbon full-width at the top, the devices laid over its first
``DRAPE_LENGTH`` rows, and the medal hanging below. The shadowbox takes the
atlas tiles instead, so when the mod's award art is remodelled the atlas
moves and these bases do not - the Bronze Star went bronze in the game while
the record still showed the old brass one.

Only the pendant is taken across. The ribbon is not remodelled with the
medal, and the drape's ribbon is deliberately longer than the atlas tile's
so devices have somewhere to sit, so rebuilding it from the tile would
change the composition for no reason. Everything above the waist - the
ribbon, its fold and its chevron - is kept exactly as it was.

The waist is the narrowest row between the ribbon and the medal: the
suspension ring or the clasp. It is found in both pictures, the tile's
pendant is scaled to the width the old one had (or to the height left in
the canvas, whichever is the tighter fit), and it is hung centred with its
top on the old waist.

DO NOT run this over the set. The atlas is not a general source for these
bases: they were painted for the dress coat and the atlas tiles are a
different rendering, systematically brighter and not always the same
design. The Legion of Merit is the plain case - the drawn one has the green
laurel wreath and no atlas tile has a single green pixel in it. Reach for
this only when a particular medal has been remodelled in the mod and the
tile is the wanted picture, and look at --sheet before writing.

Used so far for 601008 and 601018, whose drawn bases were a brass Bronze
Star and the old Silver Star.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record import medals                       # noqa: E402
from korea_service_record.career.aggregator import CareerAggregator  # noqa: E402
from korea_service_record.locate import find_game_dir         # noqa: E402

ART = REPO / "korea_service_record" / "static" / "images" / "medals"

# The waist is looked for between these fractions of the picture's height.
# Above is ribbon, below is medal; every drape and every tile in the set has
# its suspension well inside this band.
WAIST_BAND = (0.30, 0.72)


def waist(img) -> int:
    """The row where the ribbon hands over to the medal."""
    import numpy as np

    opaque = np.asarray(img.convert("RGBA"))[..., 3] > 100
    widths = opaque.sum(axis=1)
    lo, hi = (int(len(widths) * f) for f in WAIST_BAND)
    return lo + int(np.argmin(widths[lo:hi]))


def pendant(img):
    """The medal below the waist, trimmed to its own ink."""
    cut = img.convert("RGBA").crop((0, waist(img), img.width, img.height))
    box = cut.getbbox()
    return cut.crop(box) if box else None


def refresh(base: int, tile, dry_run: bool = False):
    """Rebuild one base from its atlas tile. Returns (old, new) for a sheet."""
    from PIL import Image

    path = ART / f"{base}.png"
    if not path.is_file():
        print(f"  {base}: no drawn base to refresh")
        return None
    old = Image.open(path).convert("RGBA")
    if old.size != medals.DRAPE:
        old = old.resize(medals.DRAPE, Image.LANCZOS)
    new_pendant = pendant(tile)
    old_pendant = pendant(old)
    if new_pendant is None or old_pendant is None:
        print(f"  {base}: cannot find a pendant in one of the two")
        return None

    cut = waist(old)
    room_h = medals.DRAPE[1] - cut
    # Match the width the old medal had, unless that would not fit the rows
    # left under the ribbon - the drape is a fixed canvas and a medal drawn
    # past its bottom edge is worse than one a few per cent small.
    scale = min(old_pendant.width / new_pendant.width, room_h / new_pendant.height)
    size = (max(1, round(new_pendant.width * scale)),
            max(1, round(new_pendant.height * scale)))
    if size[0] > medals.DRAPE[0]:
        scale *= medals.DRAPE[0] / size[0]
        size = (medals.DRAPE[0], max(1, round(new_pendant.height * scale)))
    scaled = new_pendant.resize(size, Image.LANCZOS)

    out = Image.new("RGBA", medals.DRAPE, (0, 0, 0, 0))
    out.alpha_composite(old.crop((0, 0, medals.DRAPE[0], cut)), (0, 0))
    out.alpha_composite(scaled, ((medals.DRAPE[0] - size[0]) // 2, cut))
    print(f"  {base}: waist y {cut}, pendant {new_pendant.size} -> {size} "
          f"(x{scale:.3f}){' [dry run]' if dry_run else ''}")
    if not dry_run:
        out.save(path, optimize=True)
    return old, out


def main() -> int:
    from PIL import Image

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", type=int, help="base award ids; default every drawn base")
    ap.add_argument("--dry-run", action="store_true", help="measure and draw, write nothing")
    ap.add_argument("--sheet", type=Path, help="write a before/after picture here")
    ap.add_argument("--per-row", type=int, default=5, help="pairs per row on the sheet")
    args = ap.parse_args()

    game = find_game_dir()
    if game is None:
        print("No IL-2 Korea installation found")
        return 1
    print(f"Atlas from {game}")
    agg = CareerAggregator(game, lang="eng")

    ids = args.ids or sorted(medals.DRAWN)
    pairs = []
    for base in ids:
        data = agg.icons.png("award", str(base))
        if data is None:
            print(f"  {base}: no atlas tile")
            continue
        import io
        got = refresh(base, Image.open(io.BytesIO(data)), args.dry_run)
        if got:
            pairs.append((base, *got))

    if args.sheet and pairs:
        # Wrapped, and labelled: a single row of seventeen pairs is 8000px
        # wide and nothing in it can be judged.
        from PIL import ImageDraw
        cell, pad, per_row, label = medals.DRAPE[0], 14, args.per_row, 22
        cols = min(per_row, len(pairs))
        rows = (len(pairs) + per_row - 1) // per_row
        pair_w = cell * 2 + pad
        sheet = Image.new("RGBA", (cols * (pair_w + pad) + pad,
                                   rows * (medals.DRAPE[1] + label + pad) + pad),
                          (242, 236, 220, 255))
        draw = ImageDraw.Draw(sheet)
        for i, (base, before, after) in enumerate(pairs):
            cx = pad + (i % per_row) * (pair_w + pad)
            cy = pad + (i // per_row) * (medals.DRAPE[1] + label + pad)
            draw.text((cx, cy + 4), f"{base}   before | after", fill=(90, 70, 40, 255))
            sheet.alpha_composite(before, (cx, cy + label))
            sheet.alpha_composite(after, (cx + cell + pad, cy + label))
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(args.sheet)
        print(f"Sheet: {args.sheet} ({len(pairs)} pairs, before then after)")

    if not args.dry_run and pairs:
        print("\nBump medals.REVISION so the render cache and the browser "
              "both let go of the old pictures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
