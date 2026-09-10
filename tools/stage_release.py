"""
Assemble everything the installer ships into one folder.

    python tools/stage_release.py            # uses the autodetected game folder
    python tools/stage_release.py --game "E:/SteamLibrary/steamapps/common/IL2Series"

Produces ``installer/payload``::

    payload/tracker/     the PyInstaller output, installed to {app}
    payload/mod/data/    the awards mod, installed into the user's game folder

Two very different kinds of thing, which is why they are staged apart.

**The tracker ships no game data at all.** It reads what it needs out of the
user's own installation at runtime, decrypting Interface.gtp as it goes, and
caches the results under %LOCALAPPDATA%. Verified by deleting the whole 35 MB
cache and running the packaged exe cold: medals, insignia, briefings and names
all came back. So nothing of 1C's is redistributed.

**The mod is the opposite** — it is precisely a set of modified game files, and
they only work as loose files because the resolver (and the engine) prefer
loose over archive. They have to be copied into ``<game>\\data\\``.

The mod is staged from the *game folder*, not from the extract in
IL2Korea-Modding: that extract has drifted badly — 11 of these 28 files are
missing from it and 9 more differ, because edits were made in place and never
mirrored back. What the user actually plays with is the truth.
"""

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / "installer" / "payload"

# Every file the awards mod adds or replaces, relative to <game>/data.
# Deliberately explicit: a glob over data/ would sweep up the player's own
# UserData settings and the .bak files left by earlier edits.
MOD_FILES = [
    "scg/2/awards.cfg",
    "nsdata/assets/images/awards.xaml",
    "nsdata/assets/images/awards6xx.dds",
    "nsdata/assets/images/awards6xx2.dds",
]
for award in ("601027", "601040", "601041"):
    for lang in ("chs", "eng", "fra", "ger", "rus", "spa"):
        MOD_FILES.append(f"nsdata/assets/awards/6xx/{award}.locale={lang}.txt")
for lang in ("chs", "eng", "fra", "ger", "rus", "spa"):
    MOD_FILES.append(f"nsdata/assets/locale/awards.locale={lang}.json")


def autodetect() -> Path:
    for drive in "CDEFGH":
        candidate = Path(f"{drive}:/SteamLibrary/steamapps/common/IL2Series")
        if (candidate / "data" / "Career").is_dir():
            return candidate
    raise SystemExit("No IL-2 Korea installation found; pass --game")


def stage_tracker() -> int:
    built = REPO / "dist" / "IL2_Korea_Service_Record"
    if not built.is_dir():
        raise SystemExit("Run: pyinstaller korea_service_record.spec --noconfirm")
    target = PAYLOAD / "tracker"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(built, target)
    return sum(1 for p in target.rglob("*") if p.is_file())


def stage_mod(game: Path) -> int:
    source = game / "data"
    target = PAYLOAD / "mod" / "data"
    if target.exists():
        shutil.rmtree(target)
    copied = 0
    for relative in MOD_FILES:
        src = source / relative
        if not src.is_file():
            print(f"  missing from the game folder: {relative}")
            continue
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", help="path to the IL-2 Korea installation")
    args = parser.parse_args()
    game = Path(args.game) if args.game else autodetect()

    PAYLOAD.mkdir(parents=True, exist_ok=True)
    tracker = stage_tracker()
    mod = stage_mod(game)

    print(f"  tracker : {tracker} files -> installer/payload/tracker")
    print(f"  mod     : {mod} of {len(MOD_FILES)} files -> installer/payload/mod/data")
    if mod != len(MOD_FILES):
        print("  WARNING: the mod is incomplete; the installer would ship a broken mod")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
