"""
Turn the generated aircraft illustrations into header art.

The generator hands back a large picture of an aeroplane centred on a flat
cream field, and the page needs a small transparent cut-out that sits in the
header gap. Four things happen here:

  * the cream is measured from the corners rather than assumed - each render
    comes back a slightly different shade;
  * alpha is derived from every pixel's distance from that cream. Blending the
    cream away with `mix-blend-mode: multiply` almost works, but the two creams
    differ by a couple of values and that was enough to print a faint rectangle
    on the page. A real cut-out also survives whatever background the page
    grows later;
  * every aircraft is scaled so its *own* length fills the same fraction of the
    canvas. Fitting each picture to the box instead would make the long-winged
    machines look further away than the short ones;
  * the result is quantised. These are near-monochrome sepia images, so 224
    colours is generous and cuts the file by about five times - worth doing
    when eight of them ship inside an installer.

Usage:  python tools/make_plane_art.py <folder-with-the-pngs>
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = (Path(__file__).resolve().parent.parent
       / "korea_service_record" / "static" / "images" / "planes")

# The band in the record header. Every aircraft is drawn onto this canvas so
# one CSS aspect-ratio holds for the whole set.
CANVAS = (1100, 412)
FILL = 0.90          # of the canvas width the aircraft itself should span
COLOURS = 224

# The game's own plane keys, which are also the file names the page looks up.
KEYS = ["f51d", "f80c10", "f84e", "f86a5", "mig15bis", "la11", "yak9p", "il10"]


def cut_out(path: Path) -> Image.Image:
    """Isolate the aircraft from its cream field, as RGBA."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)

    # Sample all four corners: a vignette or a stray mark in one of them would
    # otherwise set the background colour for the whole picture.
    corners = np.concatenate([a[:12, :12].reshape(-1, 3), a[:12, -12:].reshape(-1, 3),
                              a[-12:, :12].reshape(-1, 3), a[-12:, -12:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)

    dist = np.abs(a - bg).max(axis=2)
    alpha = np.clip((dist - 5.0) / 26.0, 0.0, 1.0)      # soft ramp keeps the AA

    # The cream is not quite spotless: the bulk of it sits within 1-2 values of
    # the median, but every render carries a handful of isolated specks up to
    # 138 values out. Those are invisible on the page and yet they decide the
    # bounding box, which had four of the eight aircraft scaled as though they
    # filled the whole frame. Eroding and then over-dilating deletes anything
    # smaller than the erosion window while leaving the aircraft's soft edge
    # comfortably inside the mask.
    mask = Image.fromarray((alpha * 255).astype(np.uint8))
    keep = (mask.filter(ImageFilter.MinFilter(7))
                .filter(ImageFilter.MaxFilter(15))
                .filter(ImageFilter.GaussianBlur(2)))
    alpha = alpha * np.clip(np.asarray(keep).astype(np.float32) / 255.0 * 1.6, 0, 1)

    return Image.fromarray(
        np.dstack([a, alpha * 255.0]).astype(np.uint8), "RGBA"), bg, alpha


def place(rgba: Image.Image, alpha: np.ndarray) -> Image.Image:
    """Trim to the aircraft, scale it to a constant length, centre on canvas."""
    solid = alpha > 0.35
    cols = np.where(solid.any(axis=0))[0]
    rows = np.where(solid.any(axis=1))[0]
    if not len(cols) or not len(rows):
        raise ValueError("no aircraft found - is the background really flat?")
    box = (int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1)
    plane = rgba.crop(box)

    scale = min(CANVAS[0] * FILL / plane.width, CANVAS[1] * 0.94 / plane.height)
    plane = plane.resize((max(1, round(plane.width * scale)),
                          max(1, round(plane.height * scale))), Image.LANCZOS)

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.paste(plane, ((CANVAS[0] - plane.width) // 2,
                         (CANVAS[1] - plane.height) // 2), plane)
    return canvas


def main(folder: str) -> int:
    src_dir = Path(folder)
    OUT.mkdir(parents=True, exist_ok=True)
    missing = []
    for key in KEYS:
        src = src_dir / f"{key}.png"
        if not src.is_file():
            missing.append(key)
            continue
        rgba, bg, alpha = cut_out(src)
        art = place(rgba, alpha)
        dst = OUT / f"{key}.png"
        art.quantize(colors=COLOURS, method=Image.FASTOCTREE).save(dst, optimize=True)
        cream = "#%02X%02X%02X" % tuple(int(c) for c in bg)
        print(f"  {key:<9} cream {cream}  ->  {dst.name:<14} "
              f"{dst.stat().st_size // 1024:4d} KB")
    if missing:
        print(f"\n  not found: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1
                          else str(Path.home() / "Downloads")))
