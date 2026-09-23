"""
Replace the artwork of awards that already have a tile, across all three
award atlases, without recompressing anything that is not being replaced.

    python tools/replace_award_art.py <folder> [--dry-run] [--sheet out.png]

The folder holds PNGs named after the medal and its devices; the MAPPING
table below turns each file into one or more xaml keys (a base shared by
the Air Force and the Navy becomes one tile with two keys). For every key:
the old rectangle is cleared, the new art is cleaned (add_award_art.clean_alpha)
and trimmed, placed at its old origin if it still fits clear of every
neighbour, else in the first free slot (same atlas first), and awards.xaml
is rewritten to the new rectangle.

BC7 is spliced, not re-encoded wholesale: the modified atlas is encoded with
texconv, and only the 32-px-aligned cells covering the old and new
rectangles are copied into the original DDS at each of the four mips, so
everything else stays byte-identical and the file size never changes.
"""

import argparse
import io
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tools.add_award_art import clean_alpha          # noqa: E402

STAGED = REPO / "installer" / "mod" / "assets"
GAME = Path(r"E:\SteamLibrary\steamapps\common\IL2Series\data")
LIVE_IMAGES = GAME / "nsdata" / "assets" / "images"
ATLASES = ("Awards6xx", "Awards6xx2", "Awards6xx3")
ATLAS_FILE = {"Awards6xx": "awards6xx.dds", "Awards6xx2": "awards6xx2.dds", "Awards6xx3": "awards6xx3.dds"}
SIZE = 2048
MIPS = 4
CELL = 32          # a BC7 block at mip 3 is 32 px at mip 0
GRID = 8
CLEARANCE = 4
DDS_BYTES = 5_570_708

# file stem -> xaml keys. USAF ids 601xxx, Navy/USMC 602xxx; a base drawn
# once serves both services.
MAPPING: Dict[str, Tuple[int, ...]] = {
    "AF_Commendation_1BOC": (601055,), "AF_Commendation_2BOC": (601056,), "AF_Commendation_3BOC": (601057,),
    "AirMedal_1BOC": (601003,), "AirMedal_2BOC": (601004,), "AirMedal_3BOC": (601005,),
    "AirMedal_4BOC": (601006,), "AirMedal_1SOC": (601007,),
    "AirMedal_1GS": (602003,), "AirMedal_2GS": (602004,), "AirMedal_3GS": (602005,),
    "AirMedal_4GS": (602006,), "AirMedal_1SS": (602007,),
    "Bronze_Star": (601008, 602008), "Bronze_Star_1BOC": (601009,), "Bronze_Star_2BOC": (601010,),
    "Bronze_Star_1GS": (602009,), "Bronze_Star_2GS": (602010,),
    "Bronze_Star_V": (601058, 602048),
    "Bronze_Star_V_1BOC": (601059, 601061), "Bronze_Star_V_2BOC": (601060, 601062),
    "Bronze_Star_V_1GS": (602049, 602051), "Bronze_Star_V_2GS": (602050, 602052),
    "DFC_1BOC": (601012,), "DFC_2BOC": (601013,), "DFC_3BOC": (601014,), "DFC_4BOC": (601015,),
    "DFC_1SOC": (601016,),
    "DFC_1GS": (602012,), "DFC_2GS": (602013,), "DFC_3GS": (602014,), "DFC_4GS": (602015,),
    "DFC_1SS": (602016,),
    "DSC": (601021,), "DSC_1BOC": (601022,), "DSC_2BOC": (601023,), "DSC_3BOC": (601024,),
    "DSC_4BOC": (601025,),
    "Korean_service_Medal_1BS": (601032,), "Korean_service_Medal_2BS": (601033,),
    "Korean_service_Medal_3BS": (601034,), "Korean_service_Medal_4BS": (601035,),
    "Korean_service_Medal_1SS": (601036,), "Korean_service_Medal_1SS_1BS": (601037,),
    "Korean_service_Medal_1SS_2BS": (601038,),
    "Navy_Commendation_1BOC": (602035,), "Navy_Commendation_2BOC": (602036,),
    "Navy_Commendation_3BOC": (602037,),
    "Navy_Cross_1GS": (602022,), "Navy_Cross_2GS": (602023,), "Navy_Cross_3GS": (602024,),
    "Navy_Cross_4GS": (602025,), "Navy_Cross_1SS": (602026,),
    "Navy_MoH": (602027,), "Navy_MoH_1GS": (602038,),
    "Navy_PUC_1GS": (602039,), "Navy_PUC_2GS": (602040,), "Navy_PUC_3GS": (602041,),
    "Navy_Ribbon_unit_commendation_1GS": (602044,), "Navy_Ribbon_unit_commendation_2GS": (602045,),
    "Navy_Ribbon_unit_commendation_3GS": (602046,), "Navy_Ribbon_unit_commendation_4GS": (602047,),
    "Purple_Heart": (601028, 602028), "Purple_Heart_1BOC": (601029,), "Purple_Heart_2BOC": (601030,),
    "Purple_Heart_1GS": (602029,), "Purple_Heart_2GS": (602030,),
    "SilverStar": (601018, 602018), "SilverStar_1BOC": (601019,), "SilverStar_2BOC": (601020,),
    "SilverStar_3BOC": (601050,), "SilverStar_4BOC": (601051,),
    "SilverStar_1GS": (602019,), "SilverStar_2GS": (602020,), "SilverStar_3GS": (602042,),
    "SilverStar_4GS": (602043,),
}

Rect = Tuple[int, int, int, int]      # x, y, w, h
CROP_RE = re.compile(r'x:Key="award(\d+)" SourceRect="(\d+),(\d+),(\d+),(\d+)" '
                     r'Source="\{StaticResource AtlasBitmap\.(\w+)\}"')


def read_dds(blob: bytes) -> Image.Image:
    assert blob[:4] == b"DDS " and blob[84:88] == b"DX10" and len(blob) == DDS_BYTES
    assert struct.unpack_from("<2I", blob, 12) == (SIZE, SIZE)
    assert struct.unpack_from("<I", blob, 28)[0] == MIPS
    assert struct.unpack_from("<I", blob, 128)[0] == 98          # BC7_UNORM
    return Image.open(io.BytesIO(blob)).convert("RGBA")


def encode(img: Image.Image, tmp: Path, name: str) -> bytes:
    png = tmp / f"{name}.png"
    img.save(png)
    done = subprocess.run(["texconv", "-nologo", "-y", "-f", "BC7_UNORM", "-m", str(MIPS),
                           "-dx10", "-o", str(tmp), str(png)], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"texconv failed:\n{done.stdout}\n{done.stderr}")
    out = (tmp / f"{name}.dds").read_bytes()
    assert len(out) == DDS_BYTES, len(out)
    return out


def aligned(rect: Rect) -> Tuple[int, int, int, int]:
    """The 32-px-aligned cell (l, t, r, b) covering a rectangle."""
    x, y, w, h = rect
    return (x // CELL * CELL, y // CELL * CELL,
            min(SIZE, -(-(x + w) // CELL) * CELL), min(SIZE, -(-(y + h) // CELL) * CELL))


def splice(original: bytes, encoded: bytes, cells: List[Tuple[int, int, int, int]]) -> bytes:
    """Copy the BC7 blocks under the given aligned cells, at every mip."""
    result = bytearray(original)
    offset = 148
    for level in range(MIPS):
        scale = 1 << level
        columns = SIZE // scale // 4
        size = columns * columns * 16
        for left, top, right, bottom in cells:
            assert all(v % CELL == 0 for v in (left, top)) and all(v % CELL == 0 or v == SIZE for v in (right, bottom))
            for by in range(top // scale // 4, bottom // scale // 4):
                start = offset + (by * columns + left // scale // 4) * 16
                end = offset + (by * columns + right // scale // 4) * 16
                result[start:end] = encoded[start:end]
        offset += size
    assert offset == len(result) == DDS_BYTES
    return bytes(result)


class Atlas:
    def __init__(self, name: str, blob: bytes):
        self.name = name
        self.blob = blob
        self.img = read_dds(blob)
        self.work = self.img.copy()
        self.cells: List[Tuple[int, int, int, int]] = []
        self.mask: Optional[np.ndarray] = None      # occupied, with clearance
        self.kept: Optional[np.ndarray] = None      # occupied by kept tiles only (aligned cell test)

    def build_masks(self, kept_rects: List[Rect]) -> None:
        ink = np.asarray(self.work.getchannel("A")) > 8
        kept = np.zeros((SIZE, SIZE), bool)
        for x, y, w, h in kept_rects:
            kept[y:y + h, x:x + w] = True
        occ = ink | kept
        # clearance: dilate by CLEARANCE on each side
        pad = np.zeros((SIZE + 2 * CLEARANCE, SIZE + 2 * CLEARANCE), bool)
        for dy in range(-CLEARANCE, CLEARANCE + 1):
            for dx in range(-CLEARANCE, CLEARANCE + 1):
                pad[CLEARANCE + dy:CLEARANCE + dy + SIZE, CLEARANCE + dx:CLEARANCE + dx + SIZE] |= occ
        self.mask = pad[CLEARANCE:CLEARANCE + SIZE, CLEARANCE:CLEARANCE + SIZE]
        self.kept = occ

    def free(self, rect: Rect, strict: bool) -> bool:
        x, y, w, h = rect
        if x < 0 or y < 0 or x + w > SIZE or y + h > SIZE:
            return False
        if self.mask[y:y + h, x:x + w].any():
            return False
        if strict:
            l, t, r, b = aligned(rect)
            if self.kept[t:b, l:r].any():
                return False
        return True

    def find(self, w: int, h: int, strict: bool) -> Optional[Tuple[int, int]]:
        # integral image of the mask for O(1) window tests
        cum = np.pad(self.mask.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        for y in range(0, SIZE - h + 1, GRID):
            for x in range(0, SIZE - w + 1, GRID):
                s = cum[y + h, x + w] - cum[y, x + w] - cum[y + h, x] + cum[y, x]
                if s == 0 and self.free((x, y, w, h), strict):
                    return x, y
        return None

    def place(self, art: Image.Image, rect: Rect) -> None:
        x, y, w, h = rect
        self.work.paste((0, 0, 0, 0), (x, y, x + w, y + h))
        self.work.alpha_composite(art, (x, y))
        self.mask[max(0, y - CLEARANCE):y + h + CLEARANCE, max(0, x - CLEARANCE):x + w + CLEARANCE] = True
        self.cells.append(aligned(rect))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--only", metavar="STEM[,STEM...]",
                    help="replace just these files (by stem), leaving every "
                         "other tile exactly as it is")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sheet", help="write a contact sheet of every replaced crop")
    ap.add_argument("--backup", help="folder for the original dds/xaml")
    args = ap.parse_args()
    folder = Path(args.folder)

    xaml_bytes = (STAGED / "awards.xaml").read_bytes()
    assert xaml_bytes == (LIVE_IMAGES / "awards.xaml").read_bytes(), "xaml: staged != live"
    assert b"\r\n" in xaml_bytes and xaml_bytes[:3] != b"\xef\xbb\xbf"
    xaml = xaml_bytes.decode("utf-8")
    crops: Dict[int, Tuple[Rect, str]] = {}
    for m in CROP_RE.finditer(xaml):
        crops[int(m.group(1))] = ((int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))), m.group(6))

    atlases: Dict[str, Atlas] = {}
    for name in ATLASES:
        blob = (STAGED / ATLAS_FILE[name]).read_bytes()
        assert blob == (LIVE_IMAGES / ATLAS_FILE[name]).read_bytes(), f"{name}: staged != live"
        atlases[name] = Atlas(name, blob)

    # What is being replaced, and what stays.
    wanted = {n.strip() for n in args.only.split(",")} if args.only else None
    if wanted:
        missing = wanted - set(MAPPING)
        if missing:
            raise SystemExit(f"not in the mapping: {', '.join(sorted(missing))}")
    jobs = []
    for stem, keys in MAPPING.items():
        if wanted and stem not in wanted:
            continue
        p = folder / f"{stem}.png"
        if not p.is_file():
            raise SystemExit(f"missing {p.name}")
        for k in keys:
            if k not in crops:
                raise SystemExit(f"awards.xaml has no award{k} (for {stem})")
        art = clean_alpha(Image.open(p))
        box = art.getbbox()
        art = art.crop(box)
        jobs.append((stem, keys, art))
    replaced = {k for _, keys, _ in jobs for k in keys}
    kept = {k: v for k, v in crops.items() if k not in replaced}

    # Clear the old tiles (only where no kept key still uses that rectangle).
    kept_rects = {(a, r) for r, a in kept.values()}
    for k in replaced:
        rect, a = crops[k]
        if (a, rect) in kept_rects:
            continue
        atl = atlases[a]
        x, y, w, h = rect
        atl.work.paste((0, 0, 0, 0), (x, y, x + w, y + h))
        atl.cells.append(aligned(rect))
    for a in atlases.values():
        a.build_masks([r for r, an in kept.values() if an == a.name])

    # Two passes. First, everything that still fits at its old origin stays
    # there - that cell is spliced anyway (it was cleared), so staying put
    # costs no extra re-encoding. Then the pieces that outgrew their cell,
    # largest first: a slot whose aligned cell is clear of kept art if there
    # is one (same atlas first), else any free slot.
    new_crops: Dict[int, Tuple[Rect, str]] = {}
    report = {}
    movers = []
    for stem, keys, art in jobs:
        w, h = art.size
        old_rect, old_atlas = crops[keys[0]]
        cand = (old_rect[0], old_rect[1], w, h)
        if atlases[old_atlas].free(cand, strict=False):
            atlases[old_atlas].place(art, cand)
            for k in keys:
                new_crops[k] = (cand, old_atlas)
            report[stem] = f"  {stem:36s} {'/'.join(map(str, keys)):14s} {old_atlas:10s} {cand[0]:4d},{cand[1]:4d} {w}x{h}"
        else:
            movers.append((stem, keys, art))
    for stem, keys, art in sorted(movers, key=lambda j: -(j[2].width * j[2].height)):
        w, h = art.size
        old_rect, old_atlas = crops[keys[0]]
        placed = None
        for strict in (True, False):
            for name in [old_atlas] + [n for n in ATLASES if n != old_atlas]:
                pos = atlases[name].find(w, h, strict)
                if pos:
                    placed = (name, pos[0], pos[1]); break
            if placed:
                break
        if placed is None:
            raise SystemExit(f"no room for {stem} {w}x{h}")
        name, x, y = placed
        rect = (x, y, w, h)
        atlases[name].place(art, rect)
        for k in keys:
            new_crops[k] = (rect, name)
        report[stem] = (f"  {stem:36s} {'/'.join(map(str, keys)):14s} {name:10s} {x:4d},{y:4d} {w}x{h}"
                        f"  <- was {old_atlas} {old_rect[0]},{old_rect[1]}")
    print("\n".join(report[s] for s, _, _ in jobs))

    # Rewrite the xaml lines in place, preserving everything else byte for byte.
    def sub(m):
        k = int(m.group(1))
        if k not in new_crops:
            return m.group(0)
        (x, y, w, h), name = new_crops[k]
        return f'x:Key="award{k}" SourceRect="{x},{y},{w},{h}" Source="{{StaticResource AtlasBitmap.{name}}}"'
    new_xaml = CROP_RE.sub(sub, xaml)
    out_xaml = new_xaml.encode("utf-8")
    assert out_xaml.count(b"\r\n") == xaml_bytes.count(b"\r\n") and out_xaml.count(b"\n") == xaml_bytes.count(b"\n")

    # Encode and splice.
    results: Dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, atl in atlases.items():
            if not atl.cells:
                continue
            enc = encode(atl.work, Path(tmp), name)
            results[name] = splice(atl.blob, enc, atl.cells)
    # Verify: untouched bytes identical; kept crops pixel-identical unless
    # they overlap a spliced cell (then report); new crops close to the art.
    for name, blob in results.items():
        atl = atlases[name]
        final = read_dds(blob)
        cellmask = np.zeros((SIZE, SIZE), bool)
        for l, t, r, b in atl.cells:
            cellmask[t:b, l:r] = True
        before, after = np.asarray(atl.img), np.asarray(final)
        outside = ~cellmask
        assert np.array_equal(before[outside], after[outside]), f"{name}: pixels outside the cells changed"
        touched_kept = []
        for k, (r, an) in kept.items():
            if an != name:
                continue
            x, y, w, h = r
            if cellmask[y:y + h, x:x + w].any():
                d = np.abs(before[y:y + h, x:x + w].astype(int) - after[y:y + h, x:x + w].astype(int)).max()
                touched_kept.append((k, int(d)))
        if touched_kept:
            print(f"  {name}: kept tiles inside re-encoded cells (max channel delta): {touched_kept}")
        for k, (r, an) in new_crops.items():
            if an != name:
                continue
            x, y, w, h = r
            want = np.asarray(atl.work.crop((x, y, x + w, y + h))).astype(int)
            got = after[y:y + h, x:x + w].astype(int)
            mean = np.abs(want - got).mean()
            assert mean < 4, f"{name} award{k}: BC7 error too large ({mean:.2f})"
        print(f"  {name}: {len(atl.cells)} cells spliced, {len(blob)} bytes")

    if args.sheet:
        finals = {n: read_dds(results[n]) if n in results else atlases[n].img for n in ATLASES}
        items = sorted({tuple(v): k for k, v in new_crops.items()}.items(), key=lambda kv: kv[1])
        cols, cw, ch = 10, 240, 500
        rows = -(-len(items) // cols)
        sheet = Image.new("RGBA", (cols * cw, rows * ch), (80, 86, 96, 255))
        draw = ImageDraw.Draw(sheet)
        for i, ((rect, name), k) in enumerate(items):
            x, y, w, h = rect
            crop = finals[name].crop((x, y, x + w, y + h))
            if crop.height > ch - 30:
                crop = crop.resize((round(crop.width * (ch - 30) / crop.height), ch - 30))
            px, py = (i % cols) * cw, (i // cols) * ch
            sheet.alpha_composite(crop, (px + (cw - crop.width) // 2, py + 24))
            keys = "/".join(str(kk) for kk, v in new_crops.items() if v == (rect, name))
            draw.text((px + 4, py + 4), keys, fill="white")
        sheet.convert("RGB").save(args.sheet)
        print(f"  sheet {args.sheet}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if args.backup:
        bk = Path(args.backup); bk.mkdir(parents=True, exist_ok=True)
        for name in results:
            (bk / ATLAS_FILE[name]).write_bytes(atlases[name].blob)
        (bk / "awards.xaml").write_bytes(xaml_bytes)
    for name, blob in results.items():
        for dest in (STAGED, LIVE_IMAGES):
            (dest / ATLAS_FILE[name]).write_bytes(blob)
    for dest in (STAGED, LIVE_IMAGES):
        (dest / "awards.xaml").write_bytes(out_xaml)
    print(f"\n  wrote {len(results)} atlases + awards.xaml to staged and live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
