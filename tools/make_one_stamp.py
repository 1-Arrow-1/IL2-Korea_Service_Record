"""
Cut a single stamp impression out of its cream field.

    python tools/make_one_stamp.py <image> <name>
    python tools/make_one_stamp.py ~/Downloads/MIA.png missing --saturation 0.52

make_stamps.py does the same for a *sheet* of impressions, splitting it at the
blank columns between them. A generator asked for one stamp returns one stamp,
with nothing to split, so this shares the cut-out but skips the splitting: alpha
from distance to the measured background, speckle removed by an erode then an
over-dilate, trimmed to the ink and scaled to the same height as the rest.

The ink keeps its own colour unless ``--saturation`` is given. The three stamps
already in the set measure 0.31, 0.57 and 0.31 saturated — all pulled towards
the page, because full-strength colour glares against this sepia ground. A
generator will happily return something far brighter (the MIA stamp arrived at
0.71), and that one stamp then reads as a sticker on a page of rubber
impressions. The option rescales saturation while leaving the alpha, and so the
worn texture, untouched.
"""

import argparse
import colorsys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "korea_service_record" / "static" / "images" / "stamps"

TARGET_H = 220          # matches the existing stamps
COLOURS = 96            # a single-ink impression needs no more


def cut_out(path: Path):
    """Alpha from distance to the background sampled at the four corners."""
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
    return a, alpha, bg


def measure(rgb: np.ndarray, alpha: np.ndarray) -> tuple:
    """Mean colour of the dense ink, ignoring the feathered edges."""
    solid = alpha > 0.8
    if not solid.any():
        return (0.0, 0.0, 0.0), 0.0
    mean = rgb[solid].mean(axis=0)
    _h, s, _v = colorsys.rgb_to_hsv(*(v / 255.0 for v in mean))
    return mean, s


def retone(rgb: np.ndarray, alpha: np.ndarray, target: float) -> np.ndarray:
    """Rescale saturation towards `target`, leaving hue and lightness alone."""
    _mean, current = measure(rgb, alpha)
    if current <= 0.001:
        return rgb
    factor = target / current
    a = rgb / 255.0
    high = a.max(axis=2)
    # Pull each pixel towards its own grey by the same proportion; that scales
    # saturation without touching value, which is what keeps the ink's tooth.
    grey = high[..., None]
    scaled = grey - (grey - a) * factor
    out = np.where(high[..., None] > 0, scaled, a)
    return np.clip(out, 0.0, 1.0) * 255.0


def darken(rgb: np.ndarray, alpha: np.ndarray, target: float) -> np.ndarray:
    """
    Scale the ink's value towards `target`.

    Desaturating preserves lightness, so a bright red pulled to a modest
    saturation lands on salmon rather than on a deep seal red. Value is the
    other half of the same adjustment: bring it down and the ink reads as
    ink again. Scales every channel alike, so hue is untouched.
    """
    mean, _s = measure(rgb, alpha)
    current = mean.max() / 255.0
    if current <= 0.001:
        return rgb
    return np.clip(rgb * (target / current), 0.0, 255.0)


def main(src: str, name: str, saturation, height: int = TARGET_H,
         value=None) -> int:
    path = Path(src).expanduser()
    if not path.is_file():
        raise SystemExit(f"not found: {path}")
    rgb, alpha, bg = cut_out(path)
    mean, before = measure(rgb, alpha)
    v_before = mean.max() / 255.0
    if saturation is not None:
        rgb = retone(rgb, alpha, saturation)
    if value is not None:
        rgb = darken(rgb, alpha, value)
    mean, after = measure(rgb, alpha)
    v_after = mean.max() / 255.0
    print(f"  saturation  {before:.2f} -> {after:.2f}"
          f"{'' if saturation is None else f'  (asked {saturation:.2f})'}")
    print(f"  value       {v_before:.2f} -> {v_after:.2f}"
          f"{'' if value is None else f'  (asked {value:.2f})'}")
    ink = alpha > 0.3
    if not ink.any():
        raise SystemExit("no ink found - is the background really a flat field?")

    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    top, bot = int(rows.min()), int(rows.max()) + 1
    left, right = int(cols.min()), int(cols.max()) + 1

    piece = np.dstack([rgb[top:bot, left:right],
                       alpha[top:bot, left:right] * 255.0])
    img = Image.fromarray(piece.astype(np.uint8), "RGBA")
    scale = height / img.height
    img = img.resize((max(1, round(img.width * scale)), height), Image.LANCZOS)

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"{name}.png"
    img.quantize(colors=COLOURS, method=Image.FASTOCTREE).save(dst, optimize=True)
    print(f"  background  rgb{tuple(int(v) for v in bg)}")
    print(f"  trimmed     {right - left}x{bot - top} of {rgb.shape[1]}x{rgb.shape[0]}")
    print(f"  {dst.relative_to(REPO)}  {img.size[0]}x{img.size[1]}  "
          f"{dst.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", help="the generated stamp, on a flat field")
    ap.add_argument("name", help="output name, e.g. 'missing' for missing.png")
    ap.add_argument("--saturation", type=float, default=None,
                    help="rescale the ink to this saturation (the existing "
                         "stamps sit between 0.31 and 0.57)")
    ap.add_argument("--value", type=float, default=None,
                    help="scale the ink's value (lightness) to this; bright "
                         "reds desaturate to salmon unless also brought down "
                         "to about 0.7")
    ap.add_argument("--height", type=int, default=TARGET_H,
                    help=f"output height in px (default {TARGET_H}, the status "
                         "stamps; the photo seals use 400 as they show larger "
                         "and over a face)")
    args = ap.parse_args()
    raise SystemExit(main(args.image, args.name, args.saturation, args.height,
                          args.value))
