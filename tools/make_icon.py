"""
Draw the application icon.

    python tools/make_icon.py            # write the .ico and the web icon
    python tools/make_icon.py --preview  # also write a sheet of every size

A struck five-pointed star hanging from a service ribbon. The star is the one
emblem all four air forces in this game share — USAF, VVS, PLAAF and KPAF — so
it suits a record that might belong to any of them, where wings or a named
decoration would pick a side. The ribbon is what keeps it from reading as the
"favourite" star every other application uses.

Two things are drawn per size rather than scaled from one master, because a
16px icon is a different drawing from a 256px one:

  * The star is faceted like a real medal, each of the ten triangles shaded by
    its angle to a light from the upper left. That is for Explorer's 256px
    view; by 24px it has averaged into flat gold, so it is dropped there.
  * Below 48px the ribbon becomes a smear a few pixels tall and takes the star
    down with it, so it goes and the star grows to fill the frame instead.
    Losing detail is a simplification of the same mark; keeping an unreadable
    ribbon would just be mush.

Everything is rendered supersampled and reduced with LANCZOS. The ink outline
is held near a pixel at every size instead of thinning away to grey, which is
what separates the star from a dark taskbar.
"""

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
ICO = REPO / "installer" / "IL2_Korea_Service_Record.ico"
WEB = REPO / "korea_service_record" / "static" / "images" / "icon.png"
PREVIEW = REPO / "installer" / "icon-preview.png"

# The tracker's own palette. The star's three stops are a ramp, not a
# gradient: every facet lands on one interpolated point along it.
INK = (44, 34, 18)
GOLD_DARK = (146, 108, 38)
GOLD_MID = (220, 181, 72)
GOLD_LIGHT = (247, 227, 156)
RIBBON = (122, 43, 36)
RIBBON_PALE = (228, 214, 186)
PAPER = (248, 242, 224)          # preview sheet only

LIGHT = (-0.55, -0.84)           # upper left, in screen coords (y grows down)

# Windows picks the nearest size and scales the rest, so ship the ones it
# actually asks for: 16 in the taskbar, 32 in the Start Menu, 48 in Explorer's
# medium view, 256 in its large one.
SIZES = (256, 128, 64, 48, 32, 24, 16)


def ramp(t: float) -> tuple:
    """Dark -> mid -> light, with t clamped into the ramp."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        lo, hi, f = GOLD_DARK, GOLD_MID, t * 2
    else:
        lo, hi, f = GOLD_MID, GOLD_LIGHT, (t - 0.5) * 2
    return tuple(round(a + (b - a) * f) for a, b in zip(lo, hi))


def draw_star(d: ImageDraw.ImageDraw, cx, cy, r_out, outline, facets):
    outer, inner = [], []
    for i in range(5):
        a = -math.pi / 2 + i * 2 * math.pi / 5
        outer.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
        b = a + math.pi / 5
        inner.append((cx + r_out * 0.415 * math.cos(b),
                      cy + r_out * 0.415 * math.sin(b)))
    silhouette = []
    for i in range(5):
        silhouette += [outer[i], inner[i]]

    # Flat first, facets over the top: adjacent polygons would otherwise leave
    # hairline seams where their antialiased edges meet.
    d.polygon(silhouette, fill=GOLD_MID)

    if facets:
        for i in range(5):
            rx, ry = (outer[i][0] - cx) / r_out, (outer[i][1] - cy) / r_out
            # Each facet tilts away from the ridge running centre -> point, so
            # its normal leans to one side of that ridge. Perpendicular left
            # and right of the ridge give the two facets opposite shading.
            for normal, far in (((-ry, rx), inner[i]),
                                ((ry, -rx), inner[i - 1])):
                lit = normal[0] * LIGHT[0] + normal[1] * LIGHT[1]
                d.polygon([(cx, cy), outer[i], far], fill=ramp(0.5 + 0.62 * lit))

    d.line(silhouette + [silhouette[0]], fill=INK,
           width=max(1, round(outline)), joint="curve")


def render(size: int) -> Image.Image:
    ss = max(4, min(16, 2048 // size))
    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    ribbon = size >= 48
    facets = size >= 32
    edge = max(1.0, n * (0.019 if ribbon else 0.030))

    if ribbon:
        rw, rh = n * 0.46, n * 0.255
        x0, y0 = (n - rw) / 2, n * 0.05
        stripes = (RIBBON, RIBBON_PALE, RIBBON, RIBBON_PALE, RIBBON)
        for i, colour in enumerate(stripes):
            d.rectangle((x0 + rw * i / len(stripes), y0,
                         x0 + rw * (i + 1) / len(stripes), y0 + rh), fill=colour)
        d.rectangle((x0, y0, x0 + rw, y0 + rh), outline=INK, width=round(edge))
        # The star hangs from the ribbon: its top point meets the bar's lower
        # edge rather than crossing it.
        radius, cy = n * 0.33, y0 + rh + n * 0.33
    else:
        radius, cy = n * 0.465, n * 0.50

    draw_star(d, n / 2, cy, radius, edge * 1.1, facets)
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="write a sheet showing every size on both grounds")
    args = ap.parse_args()

    frames = {s: render(s) for s in SIZES}
    ICO.parent.mkdir(parents=True, exist_ok=True)
    frames[256].save(ICO, format="ICO", sizes=[(s, s) for s in sorted(SIZES)])
    WEB.parent.mkdir(parents=True, exist_ok=True)
    frames[256].save(WEB, optimize=True)
    print(f"  {ICO.relative_to(REPO)}  "
          f"{', '.join(str(s) for s in sorted(SIZES))}  "
          f"{ICO.stat().st_size // 1024} KB")
    print(f"  {WEB.relative_to(REPO)}  256x256")

    if args.preview:
        # Both grounds, because the taskbar is dark and Explorer is light and
        # an ink outline can vanish into either one.
        pad, gap = 24, 20
        row = sum(SIZES) + gap * (len(SIZES) - 1)
        sheet = Image.new("RGB", (row + pad * 2, 256 * 2 + pad * 3), PAPER)
        ImageDraw.Draw(sheet).rectangle(
            (0, 256 + pad + pad // 2, sheet.width, sheet.height), fill=(32, 32, 34))
        for top in (pad, 256 + pad * 2):
            x = pad
            for s in SIZES:
                sheet.paste(frames[s], (x, top + 256 - s), frames[s])
                x += s + gap
        sheet.save(PREVIEW)
        print(f"  {PREVIEW.relative_to(REPO)}  preview sheet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
