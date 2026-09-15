"""
Put one decoration's artwork into the award atlas and register it.

    python tools/add_award_art.py <award id> <image.png> --at X,Y
    python tools/add_award_art.py 601042 duc.png --at 1545,1776 --dry-run

Pastes the PNG into Awards6xx2.dds at the given position, at its native size,
re-encodes the atlas as BC7 with texconv, and adds the <CroppedBitmap> that
awards.xaml needs to find it. Refuses to paint over existing artwork and to
run off the texture, so a wrong --at fails loudly rather than corrupting a
medal that is already there.

The atlas is 2048x2048 and mostly full. What is free is along the bottom
right, below the two pilot badges the mod added at x=1545 — room for a wide
tile like a ribbon bar, which is what a unit citation is, and not for another
full medal. tools/measure free space with the integral-image scan in the
session notes before choosing --at.
"""

import argparse
import io
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402

IMAGES = "nsdata/assets/images"
ATLAS = "Awards6xx2"


def clean_alpha(img: Image.Image) -> Image.Image:
    """
    Make generated art behave like the stock tiles under BC7 and filtering.

    Generators hand back three things a game atlas cannot tolerate, none of
    which shows on a white web page. A faint fringe of nearly transparent
    pixels carrying bright colour: BC7 rounds their alpha to zero and keeps
    the colour, and texture filtering then bleeds white into the visible
    edge — the halo the user saw around the citation. A body that is not
    quite opaque (the DUC arrived at alpha 201..254 everywhere, nothing at
    255), which renders as a ghost of the paper through the medal. And bright
    colour under fully transparent pixels, which bleeds the same way.

    The stock tiles are black wherever alpha is zero and their edge pixels are
    dark, so this matches them: cut the fringe, solidify the body, darken the
    true edge in proportion to its alpha, and black out whatever is left.
    """
    import numpy as np
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    alpha = a[..., 3]
    fringe = alpha < 24                       # the glow: drop it entirely
    body = alpha >= 200                       # the emblem: make it solid
    alpha = np.where(fringe, 0.0, alpha)
    alpha = np.where(body, 255.0, alpha)
    edge = (alpha > 0) & (alpha < 255)        # the real antialiased rim
    scale = np.where(edge, alpha / 255.0, 1.0)[..., None]
    rgb = a[..., :3] * scale                  # dark-matte the rim, as stock is
    rgb[alpha == 0] = 0.0                     # black under transparency
    out = np.concatenate([rgb, alpha[..., None]], axis=2)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("award", help="award id, e.g. 601042")
    ap.add_argument("image", help="PNG with transparent background, native size")
    ap.add_argument("--at", required=True, metavar="X,Y", help="top-left in the atlas")
    ap.add_argument("--width", type=int, default=None,
                    help="scale the art to this width first (generators return "
                         "~1800px; the wide slots are 456)")
    ap.add_argument("--replace", action="store_true",
                    help="the award already has a tile: clear its rectangle first")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    x, y = (int(v) for v in args.at.split(","))

    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    res = AssetResolver(game)

    blob = res.read(f"{IMAGES}/{ATLAS}.dds")
    (_s, _f, height, width, _p, _d, mips) = struct.unpack_from("<7I", blob, 4)
    atlas = Image.open(io.BytesIO(blob)).convert("RGBA")
    art = clean_alpha(Image.open(args.image))
    # Trim to the ink (after the fringe is gone, so the glow does not count
    # against the slot), then scale, then clean again: resampling re-creates
    # a soft rim from the hard one.
    bbox = art.getbbox()
    if bbox:
        art = art.crop(bbox)
    if args.width and art.width != args.width:
        h = max(1, round(art.height * args.width / art.width))
        art = clean_alpha(art.resize((args.width, h), Image.LANCZOS))
    print(f"  atlas  {ATLAS}.dds {width}x{height} mips={mips}")
    print(f"  art    {art.width}x{art.height}  {Path(args.image).name}")

    xaml = res.read_text(f"{IMAGES}/awards.xaml")
    key = f'x:Key="award{args.award}"'

    if x + art.width > atlas.width or y + art.height > atlas.height:
        raise SystemExit(f"  {art.width}x{art.height} at ({x},{y}) runs off the texture")
    if args.replace:
        # Clear the award's current rectangle - the one awards.xaml records,
        # which may differ in size from the new art - to transparent black.
        m = re.search(rf'{re.escape(key)} SourceRect="(\d+),(\d+),(\d+),(\d+)"', xaml)
        if not m:
            raise SystemExit(f"  --replace, but awards.xaml has no award{args.award}")
        ox, oy, ow, oh = (int(v) for v in m.groups())
        atlas.paste((0, 0, 0, 0), (ox, oy, ox + ow, oy + oh))
        print(f"  clear  ({ox},{oy}) {ow}x{oh}, the previous tile")
    region = atlas.crop((x, y, x + art.width, y + art.height))
    peak = region.getchannel("A").getextrema()[1]
    # BC7 leaves specks of alpha 1-3 in blocks next to content after a
    # round-trip; that is dust, not artwork. Anything more is.
    if peak > 8:
        raise SystemExit(f"  atlas already has artwork at ({x},{y}) (max alpha {peak}); "
                         "refusing to paint over it (--replace clears this award's own tile)")
    if peak:
        atlas.paste((0, 0, 0, 0), (x, y, x + art.width, y + art.height))
    print(f"  place  ({x},{y})  free" + (f"  (swept {peak}-alpha dust)" if peak else ""))
    line = (f'    <CroppedBitmap {key} SourceRect="{x},{y},{art.width},{art.height}" '
            f'Source="{{StaticResource AtlasBitmap.{ATLAS}}}" />')
    print("  awards.xaml gains:\n" + line)
    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    atlas.alpha_composite(art, (x, y))
    out_dir = game / "data" / Path(IMAGES)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / f"{ATLAS}.png"
        atlas.save(png)
        if shutil.which("texconv") is None:
            raise SystemExit("texconv not on PATH (winget install Microsoft.DirectXTex.Texconv)")
        done = subprocess.run(["texconv", "-nologo", "-y", "-f", "BC7_UNORM", "-m", str(mips),
                               "-dx10", "-o", tmp, str(png)], capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"texconv failed:\n{done.stdout}\n{done.stderr}")
        shutil.copy2(Path(tmp) / f"{ATLAS}.dds", out_dir / f"{ATLAS}.dds")
    print(f"\n  wrote {out_dir / (ATLAS + '.dds')}")

    if key in xaml:
        xaml = re.sub(rf'[ \t]*<CroppedBitmap {re.escape(key)}[^\n]*\n', line + "\n", xaml)
        print("  awards.xaml: replaced the existing entry")
    else:
        # After the last entry on the same atlas, so the file stays grouped.
        last = None
        for m in re.finditer(rf'[ \t]*<CroppedBitmap[^\n]*AtlasBitmap\.{ATLAS}[^\n]*\n', xaml):
            last = m
        xaml = xaml[:last.end()] + line + "\n" + xaml[last.end():]
        print("  awards.xaml: entry added")
    (out_dir / "awards.xaml").write_text(xaml, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
