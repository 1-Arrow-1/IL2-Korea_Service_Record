"""
Cut a grid of icons out of one drawn sheet into the page's icon folder.

    python tools/slice_icon_sheet.py sheet.png ac_serviceable ac_repair ...

The artwork arrives as a single transparent sheet with the icons laid out in
a grid - eleven of them for the aircraft and materiel halves of the squadron
panel, in a 6x2 grid whose last top cell is empty. The grid is found from the
sheet rather than typed in: a column or row of fully transparent pixels is a
gutter, anything else is a cell, so a sheet drawn at a different size or with
a different number of icons needs no edit here.

Each icon is then trimmed to its own ink and padded back to a square. That
matters more than it sounds: the cells are not identical (325 to 331 px on
this sheet) and the ring is the same diameter in every icon, so trimming to
ink and squaring puts every ring at the same optical size, which centring
within the cell would not.

Names are given on the command line in reading order, left to right and top
to bottom, skipping nothing - an empty cell is not counted, so pass exactly
as many names as there are icons.
"""

import sys
from pathlib import Path

from PIL import Image
import numpy as np

REPO = Path(__file__).resolve().parent.parent
ICONS = REPO / "korea_service_record" / "static" / "images" / "icons"
SIZE = 128              # the page asks for 52 px; this leaves room for 2x


def bands(profile, gap=1):
    """Runs of occupied rows or columns, ignoring hairline noise."""
    out, start = [], None
    for i, n in enumerate(profile):
        if n > gap and start is None:
            start = i
        elif n <= gap and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(profile) - 1))
    return [(a, b) for a, b in out if b - a > 20]


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    sheet = Path(argv[0])
    names = argv[1:]
    src = Image.open(sheet).convert("RGBA")
    alpha = np.asarray(src)[..., 3]
    cols = bands((alpha > 40).sum(axis=0))
    rows = bands((alpha > 40).sum(axis=1))
    print(f"{sheet.name}: {len(cols)} columns x {len(rows)} rows")

    cells = []
    for y0, y1 in rows:
        for x0, x1 in cols:
            cell = src.crop((x0, y0, x1 + 1, y1 + 1))
            if cell.getbbox() is None:           # an empty cell is not an icon
                continue
            cells.append(cell)
    if len(cells) != len(names):
        raise SystemExit(f"{len(cells)} icons on the sheet, {len(names)} names given")

    ICONS.mkdir(parents=True, exist_ok=True)
    for name, cell in zip(names, cells):
        icon = cell.crop(cell.getbbox())
        w, h = icon.size
        side = max(w, h)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(icon, ((side - w) // 2, (side - h) // 2))
        square.resize((SIZE, SIZE), Image.LANCZOS).save(ICONS / f"{name}.png")
        print(f"  {name:16} {w}x{h} -> {SIZE}x{SIZE}")
    print(f"\n{len(names)} icons written to {ICONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
