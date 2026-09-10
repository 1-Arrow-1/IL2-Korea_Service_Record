"""
Assemble what the installer ships, and keep the mod's source in the repo.

    python tools/stage_release.py                 # stage the tracker for packaging
    python tools/stage_release.py --refresh-mod   # re-copy the mod out of the game

Two payloads, kept apart because they are different kinds of thing.

**The tracker ships no game data at all.** It reads what it needs out of the
user's own installation at runtime, decrypting Interface.gtp as it goes, and
caches the result under %LOCALAPPDATA%. Verified by deleting the whole 35 MB
cache and running the packaged exe cold. So nothing of 1C's is redistributed,
and the build output is simply copied into installer/payload/tracker.

**The mod is the opposite** — it is exactly a set of modified game files. Those
live in ``installer/mod/assets`` and are committed, so the release is
reproducible and the history shows when a decoration changed. Flat, because
there are no name collisions and the destination is the installer's business,
not the folder's; ``installer/mod/README.txt`` records where each one goes for
anyone installing by hand.

``--refresh-mod`` is the only way files enter that folder, and it reads the
*game* folder rather than the extract in IL2Korea-Modding — that extract has
drifted badly, missing 11 of these 28 files and differing on 9 more, because
edits were made in place and never mirrored back.
"""

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / "installer" / "payload"
MOD_ASSETS = REPO / "installer" / "mod" / "assets"

# Every file the awards mod adds, and where the game expects it. Explicit
# rather than a glob over data\: a glob would sweep up the player's own
# UserData settings and the .bak files left by earlier edits.
MOD_FILES = {
    "awards.cfg": "scg/2",
    "awards.xaml": "nsdata/assets/images",
    "awards6xx.dds": "nsdata/assets/images",
    "awards6xx2.dds": "nsdata/assets/images",
}
for award in ("601027", "601040", "601041"):
    for lang in ("chs", "eng", "fra", "ger", "rus", "spa"):
        MOD_FILES[f"{award}.locale={lang}.txt"] = "nsdata/assets/awards/6xx"
for lang in ("chs", "eng", "fra", "ger", "rus", "spa"):
    MOD_FILES[f"awards.locale={lang}.json"] = "nsdata/assets/locale"


def autodetect() -> Path:
    for drive in "CDEFGH":
        candidate = Path(f"{drive}:/SteamLibrary/steamapps/common/IL2Series")
        if (candidate / "data" / "Career").is_dir():
            return candidate
    raise SystemExit("No IL-2 Korea installation found; pass --game")


def refresh_mod(game: Path) -> int:
    """Pull the current mod files out of the game folder into the repo."""
    MOD_ASSETS.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name, where in MOD_FILES.items():
        src = game / "data" / where / name
        if not src.is_file():
            print(f"  missing from the game folder: {where}/{name}")
            continue
        shutil.copy2(src, MOD_ASSETS / name)
        copied += 1
    write_manifest()
    return copied


def write_manifest() -> None:
    """Where each file goes, for anyone installing the mod by hand."""
    lines = [
        "IL-2 Korea Awards Mod",
        "=====================",
        "",
        "Copy each file below into the folder shown, under your IL-2 Korea",
        "installation. Enable modifications in the game first:",
        "",
        "    Settings -> General -> Enable modifications",
        "",
        "With modifications enabled the game reads these files in preference to",
        "the .gtp archives. To uninstall, delete them: the game finds nothing",
        "loose and goes back to the archives on its own. Nothing else changes.",
        "",
    ]
    for where in sorted(set(MOD_FILES.values())):
        names = sorted(n for n, w in MOD_FILES.items() if w == where)
        lines.append(f"<IL-2 Korea>\\data\\{where.replace('/', chr(92))}\\")
        lines.extend(f"    {n}" for n in names)
        lines.append("")
    (MOD_ASSETS.parent / "README.txt").write_text(
        "\r\n".join(lines), encoding="utf-8")


def stage_tracker() -> int:
    built = REPO / "dist" / "IL2_Korea_Service_Record"
    if not built.is_dir():
        raise SystemExit("Run: pyinstaller korea_service_record.spec --noconfirm")
    target = PAYLOAD / "tracker"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(built, target)
    return sum(1 for p in target.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", help="path to the IL-2 Korea installation")
    parser.add_argument("--refresh-mod", action="store_true",
                        help="re-copy the mod files out of the game folder")
    args = parser.parse_args()

    if args.refresh_mod:
        game = Path(args.game) if args.game else autodetect()
        copied = refresh_mod(game)
        print(f"  mod  : {copied} of {len(MOD_FILES)} files -> installer/mod/assets")
        return 0 if copied == len(MOD_FILES) else 1

    PAYLOAD.mkdir(parents=True, exist_ok=True)
    tracker = stage_tracker()
    print(f"  tracker : {tracker} files -> installer/payload/tracker")

    have = sum(1 for name in MOD_FILES if (MOD_ASSETS / name).is_file())
    print(f"  mod     : {have} of {len(MOD_FILES)} files in installer/mod/assets")
    if have != len(MOD_FILES):
        print("  WARNING: run --refresh-mod; the installer would ship a broken mod")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
