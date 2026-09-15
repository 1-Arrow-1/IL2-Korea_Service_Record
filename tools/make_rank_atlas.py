"""
Add two flag-officer ranks to a country's rank atlas.

    python tools/make_rank_atlas.py --country 601 <rank6.png> <rank7.png>
    python tools/make_rank_atlas.py --country 501 MajGen_USSR.png LtGen_USSR.png --dry-run

The game's rank ladder is not capped at the six ranks it ships. Adding a
seventh and eighth needs only a promotion pseudo-award, a locale entry, and a
tile in the country's atlas with a matching <CroppedBitmap> in ranks.xaml —
confirmed in game, where an uncatalogued rankId 6 promoted correctly and drew
``RANK6016!LOCALIZE!``, the engine's own missing-key marker.

Every atlas is 1024x1024 holding six tiles in three rows of two, and every one
has an empty band below the third row. That band takes exactly one more row —
two tiles — and no more, so this is a one-shot extension per country.

Nothing about the geometry is assumed. Tile size differs per country (the
USAF's are 467x198, the Soviet 461x207, the Chinese 460x185) and so does the
row pitch, so the layout is read back out of the country's own <CroppedBitmap>
entries. New artwork is pasted at its **native** size and the SourceRect
records that size: a Soviet general's board is drawn wider than a colonel's,
which is correct, and resampling it to the old slot would both blur it and lose
the point. The second tile goes in the stock second column where it fits and
is pushed right where it does not.

Output goes to the game folder as loose files, the same way every other part of
this mod is installed, and then into installer/mod/assets via
``stage_release.py --refresh-mod``. Requires texconv (DirectXTex) on PATH for
the BC7 re-encode; Pillow reads BC7 but cannot write it.
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
from typing import List, Tuple

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402

IMAGES = "nsdata/assets/images"
GAP = 8                     # the stock spacing between tiles, in both axes
STOCK_RANKS = 6


class Tile:
    def __init__(self, index: int, x: int, y: int, w: int, h: int):
        self.index, self.x, self.y, self.w, self.h = index, x, y, w, h


def stock_tiles(xaml: str, country: str) -> List[Tile]:
    found = re.findall(
        rf'x:Key="rank{country}(\d)" SourceRect="(\d+),(\d+),(\d+),(\d+)"', xaml)
    tiles = [Tile(int(i), int(x), int(y), int(w), int(h)) for i, x, y, w, h in found]
    if len(tiles) < STOCK_RANKS:
        raise SystemExit(f"ranks.xaml lists {len(tiles)} tiles for {country}; "
                         f"expected {STOCK_RANKS}")
    return tiles


def read_atlas(res: AssetResolver, country: str):
    blob = res.read(f"{IMAGES}/Ranks{country}.dds")
    if blob is None:
        raise SystemExit(f"Ranks{country}.dds not found")
    (_s, _f, height, width, _p, _d, mips) = struct.unpack_from("<7I", blob, 4)
    dxgi = struct.unpack_from("<I", blob, 128)[0] if blob[84:88] == b"DX10" else None
    print(f"  source atlas : Ranks{country}.dds {width}x{height}  mips={mips}  "
          f"dxgi={dxgi}{'' if dxgi == 98 else '  (not BC7 - will be written as BC7)'}")
    return Image.open(io.BytesIO(blob)).convert("RGBA"), mips


def plan_row(atlas: Image.Image, tiles: List[Tile],
             art: List[Image.Image]) -> List[Tuple[int, int]]:
    """Where the two new tiles go, from the stock layout and the art's own sizes."""
    row_y = max(t.y + t.h for t in tiles) + GAP
    columns = sorted({t.x for t in tiles})
    if len(columns) != 2:
        raise SystemExit(f"expected two columns of tiles, found x = {columns}")
    first_x = columns[0]
    # Stock second column where the first new tile leaves room for it; pushed
    # right where a wider board would otherwise overlap.
    second_x = max(columns[1], first_x + art[0].width + GAP)
    origins = [(first_x, row_y), (second_x, row_y)]

    for (x, y), img in zip(origins, art):
        if x + img.width > atlas.width or y + img.height > atlas.height:
            raise SystemExit(
                f"tile {img.width}x{img.height} at ({x},{y}) runs past the "
                f"{atlas.width}x{atlas.height} texture. No room.")
        peak = atlas.crop((x, y, x + img.width, y + img.height)).getchannel("A").getextrema()[1]
        if peak != 0:
            raise SystemExit(f"atlas already has artwork at ({x},{y}) "
                             f"(max alpha {peak}). Refusing to paint over it.")
    return origins


def load_art(path: Path, label: str) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    lo = img.getchannel("A").getextrema()[0]
    if lo == 255:
        print(f"  {label}: WARNING - fully opaque; the corners will be boxed")
    print(f"  {label:<18} {img.width}x{img.height}  {path.name}")
    return img


def to_dds(png: Path, out_dir: Path, mips: int) -> Path:
    if shutil.which("texconv") is None:
        raise SystemExit("texconv not found on PATH "
                         "(winget install Microsoft.DirectXTex.Texconv)")
    done = subprocess.run(
        ["texconv", "-nologo", "-y", "-f", "BC7_UNORM", "-m", str(mips),
         "-dx10", "-o", str(out_dir), str(png)],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"texconv failed:\n{done.stdout}\n{done.stderr}")
    return out_dir / (png.stem + ".dds")


def xaml_lines(country: str, origins, art) -> str:
    return "\n".join(
        f'    <CroppedBitmap x:Key="rank{country}{STOCK_RANKS + n}" '
        f'SourceRect="{x},{y},{img.width},{img.height}" '
        f'Source="{{StaticResource AtlasBitmap.Ranks{country}}}" />'
        for n, ((x, y), img) in enumerate(zip(origins, art)))


def patch_xaml(xaml: str, country: str, lines: str) -> str:
    if f'x:Key="rank{country}{STOCK_RANKS}"' in xaml:
        print("  ranks.xaml already has the new keys; leaving it alone")
        return xaml
    # Insert directly after the country's last existing tile, so the file
    # stays grouped by country the way it ships.
    last = None
    for m in re.finditer(rf'[ \t]*<CroppedBitmap x:Key="rank{country}\d"[^\n]*\n', xaml):
        last = m
    if last is None:
        raise SystemExit(f"no rank{country}* entries in ranks.xaml")
    return xaml[:last.end()] + lines + "\n" + xaml[last.end():]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rank6", help="PNG for the seventh rank, transparent background")
    ap.add_argument("rank7", help="PNG for the eighth rank")
    ap.add_argument("--country", required=True, help="501, 502, 503, 601, 602 or 603")
    ap.add_argument("--dry-run", action="store_true", help="check and report, write nothing")
    args = ap.parse_args()

    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    res = AssetResolver(game)
    country = args.country

    atlas, mips = read_atlas(res, country)
    xaml = res.read_text(f"{IMAGES}/ranks.xaml")
    tiles = stock_tiles(xaml, country)
    sizes = {(t.w, t.h) for t in tiles}
    print(f"  stock tiles  : {len(tiles)} of {'/'.join(f'{w}x{h}' for w, h in sizes)}, "
          f"columns x={sorted({t.x for t in tiles})}, used to y={max(t.y + t.h for t in tiles)}")

    art = [load_art(Path(args.rank6), f"rank{country}6"),
           load_art(Path(args.rank7), f"rank{country}7")]
    origins = plan_row(atlas, tiles, art)
    for (x, y), img in zip(origins, art):
        print(f"  place        : {img.width}x{img.height} at ({x},{y})  free")

    lines = xaml_lines(country, origins, art)
    print("\n  ranks.xaml gains:\n" + lines)

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    for (x, y), img in zip(origins, art):
        atlas.alpha_composite(img, (x, y))

    out_dir = game / "data" / Path(IMAGES)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / f"Ranks{country}.png"
        atlas.save(png)
        dds = to_dds(png, Path(tmp), mips)
        target = out_dir / f"Ranks{country}.dds"
        shutil.copy2(dds, target)
        print(f"\n  wrote {target}  ({target.stat().st_size:,} bytes)")

    patched = patch_xaml(xaml, country, lines)
    if patched != xaml:
        (out_dir / "ranks.xaml").write_text(patched, encoding="utf-8")
        print(f"  wrote {out_dir / 'ranks.xaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
