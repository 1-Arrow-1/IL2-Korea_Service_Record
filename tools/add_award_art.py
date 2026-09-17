"""
Put one decoration's artwork into the award atlas and register it.

    python tools/add_award_art.py <award id> <image.png> --at X,Y
    python tools/add_award_art.py 601042 duc.png --at 1545,1776 --dry-run
    python tools/add_award_art.py 601045 dsm.png --atlas Awards6xx3 --auto

Pastes the PNG into an award atlas at its native size, re-encodes the atlas
as BC7 with texconv, and adds the <CroppedBitmap> that awards.xaml needs to
find it. Refuses to paint over existing artwork and to run off the texture,
so a wrong --at fails loudly rather than corrupting a medal that is already
there.

--atlas names the texture (default Awards6xx2). One that does not exist yet
is created - 2048x2048, transparent - and registered in awards.xaml with the
<BitmapImage> line the crops refer to. --auto finds the first free slot on an
8 px grid (rows top to bottom, then left to right, 4 px of clearance)
instead of taking --at; --dry-run shows where that would be.

Awards6xx2 is the stock 2048x2048 atlas and is full but for one ribbon-bar
slot at (928,1832); Awards6xx3 is the mod's own, for everything after the
first three unit citations.
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
NEW_ATLAS_SIZE = 2048
GRID = 8          # placement grid for --auto
CLEARANCE = 4     # pixels kept free around a tile, as the stock atlas does


def free_slot(atlas: Image.Image, xaml: str, w: int, h: int):
    """
    First (top-most, then left-most) position where a w x h tile plus its
    clearance covers neither ink nor a rectangle awards.xaml has already
    handed out on this atlas. Both are checked: a crop can be registered on
    a still-empty rectangle, and ink can exist without a crop.
    """
    from PIL import ImageDraw
    taken = atlas.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    draw = ImageDraw.Draw(taken)
    for rect in re.findall(rf'SourceRect="([^"]+)"[^\n]*AtlasBitmap\.{ATLAS}\}}', xaml):
        rx, ry, rw, rh = (int(v) for v in rect.split(","))
        draw.rectangle((rx, ry, rx + rw - 1, ry + rh - 1), fill=255)
    W, H = w + 2 * CLEARANCE, h + 2 * CLEARANCE
    for y in range(0, atlas.height - H + 1, GRID):
        for x in range(0, atlas.width - W + 1, GRID):
            if taken.crop((x, y, x + W, y + H)).getextrema()[1] == 0:
                return x + CLEARANCE, y + CLEARANCE
    return None


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
    global ATLAS
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("award", help="award id, e.g. 601042")
    ap.add_argument("image", help="PNG with transparent background, native size")
    ap.add_argument("--at", metavar="X,Y", help="top-left in the atlas")
    ap.add_argument("--auto", action="store_true",
                    help="place in the first free slot instead of --at")
    ap.add_argument("--atlas", default=ATLAS, metavar="NAME",
                    help=f"atlas texture without extension (default {ATLAS}); "
                         "created and registered if missing")
    ap.add_argument("--width", type=int, default=None,
                    help="scale the art to this width first (generators return "
                         "~1800px; the wide slots are 456)")
    ap.add_argument("--replace", action="store_true",
                    help="the award already has a tile: clear its rectangle first")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if bool(args.at) == bool(args.auto):
        ap.error("give exactly one of --at X,Y and --auto")
    ATLAS = args.atlas

    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    res = AssetResolver(game)

    xaml = res.read_text(f"{IMAGES}/awards.xaml")
    blob = res.read(f"{IMAGES}/{ATLAS}.dds")
    if blob:
        (_s, _f, height, width, _p, _d, mips) = struct.unpack_from("<7I", blob, 4)
        atlas = Image.open(io.BytesIO(blob)).convert("RGBA")
    else:
        width = height = NEW_ATLAS_SIZE
        mips = 4
        atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        print(f"  atlas  {ATLAS}.dds does not exist: creating {width}x{height}")
    bitmap_line = f'  <BitmapImage x:Key="AtlasBitmap.{ATLAS}" UriSource="{ATLAS}.dds" />'
    if f'AtlasBitmap.{ATLAS}"' not in xaml:
        # Ahead of the other atlas lines; the crops come after all of them.
        first = re.search(r'[ \t]*<BitmapImage [^\n]*\n', xaml)
        xaml = xaml[:first.start()] + bitmap_line + "\n" + xaml[first.start():]
        print(f"  awards.xaml gains:\n{bitmap_line}")
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

    key = f'x:Key="award{args.award}"'

    if args.auto:
        slot = free_slot(atlas, xaml, art.width, art.height)
        if slot is None:
            raise SystemExit(f"  no free {art.width}x{art.height} slot left in {ATLAS}")
        x, y = slot
    else:
        x, y = (int(v) for v in args.at.split(","))

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
        for m in re.finditer(rf'[ \t]*<CroppedBitmap[^\n]*AtlasBitmap\.{ATLAS}\}}[^\n]*\n', xaml):
            last = m
        if last is None:
            # First crop on this atlas: at the end of the crop list.
            end = re.search(r'[ \t]*</app:ResourceKeyConverter>', xaml)
            xaml = xaml[:end.start()] + line + "\n" + xaml[end.start():]
        else:
            xaml = xaml[:last.end()] + line + "\n" + xaml[last.end():]
        print("  awards.xaml: entry added")
    (out_dir / "awards.xaml").write_text(xaml, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
