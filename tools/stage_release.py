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
    # The mod's own atlas, created by add_award_art.py --atlas Awards6xx3 for
    # everything the stock atlases had no room for (second-batch unit
    # citations, Silver Star rungs 4-6, Commendation, NDSM, DSM).
    "awards6xx3.dds": "nsdata/assets/images",
    # Flag rank for all six ladders. Each atlas carries two more ranks in the
    # one free row a 1024x1024 texture had left, ranks.xaml crops them, and
    # each locale names them - without which the game draws RANK6016!LOCALIZE!.
    "ranks.xaml": "nsdata/assets/images",
}
for country in ("501", "502", "503", "601", "602", "603"):
    MOD_FILES[f"Ranks{country}.dds"] = "nsdata/assets/images"
for lang in ("chs", "eng", "fra", "ger", "rus", "spa"):
    MOD_FILES[f"ranks.locale={lang}.json"] = "nsdata/assets/locale"
# 601042 is the Distinguished Unit Citation - the squadron-level award that
# proved IsSquadron=1 works - and 601043 the Republic of Korea Presidential
# Unit Citation beside it, 601044 the DUC's oak leaf cluster. Their
# description files ship like any other's.
for award in ("601027", "601040", "601041", "601042", "601043", "601044",
              # second batch (2026-09-16): unit-citation rungs, Silver Star 4-5,
              # DSM, NDSM, Commendation ladder - tools/add_awards_batch2.py
              "601045", "601046", "601047", "601048", "601049", "601050", "601051",
              "601052", "601053", "601054", "601055", "601056", "601057",
              "601058", "601059", "601060", "601061", "601062",
              # Navy / USMC additions, shared 602 IDs for both services.
              "602031", "602032", "602033", "602034", "602035", "602036",
              "602037", "602038", "602039", "602040", "602041", "602042",
              "602043", "602044", "602045", "602046", "602047",
              # Naval Bronze Star with Combat V: five logic ids share three tiles.
              "602048", "602049", "602050", "602051", "602052"):
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


# The installer offers two promotion systems and ships one awards.cfg for
# each. They differ ONLY in the promotion block; every medal fix is shared.
# So the stock-corrected variant is never edited by hand — it is derived from
# the extended file (the one in the game folder) by swapping that one block,
# which makes it impossible for the two to drift apart on anything else.
STOCK_AWARDS = "awards.stock.cfg"

# The stock game's own promotion criteria, with the one rung it forgot
# restored on the same terms. Sorties, not ComplSorties; CareerDays, not PCP;
# IsCommander only on the way into Colonel, so AI pilots rise to Lieutenant
# Colonel and the ladder ends where the stock game ends it. No 601985/601986.
STOCK_PROMOTION_BLOCK = """\
//// Promotion - the stock criteria, with the missing rung restored.
//// The extended merit ladder is the other installer choice.

[Award=601980]
\tname="Promote from Rank0"
\tIsPromotion=1
\tAwardInProc="(RankID=0)&(Sorties>=25)"
[end]

[Award=601981]
\tname="Promote from Rank1"
\tIsPromotion=1
\tAwardInProc="(RankID=1)&(Sorties>=50)"
[end]

[Award=601982]
\tname="Promote from Rank2"
\tIsPromotion=1
\tAwardInProc="(RankID=2)&(Sorties>=100)"
[end]

[Award=601983]
\tname="Promote from Rank3"
\tIsPromotion=1
\tAwardInProc="(RankID=3)&(CareerDays>=75)"
\tAwardByDef="(RND<0)"
[end]

[Award=601984]
\tname="Commander Promotion from Rank4"
\tIsPromotion=1
\tAwardInProc="(RankID=4)&(IsCommander)&(CareerDays>=150)"
[end]

"""

STOCK_PROMOTION_NOTES = """\
// Promotion, stock corrected
//
// This is the "stock promotions, corrected" variant. The criteria are the
// game's own - sorties for the first three rungs, career days for the rest -
// with one change: stock ships no 601983, the promotion out of Major, and a
// player who starts as commander at Major can therefore never be promoted in
// an unmodified game. It is restored here on the same terms as its
// neighbours. IsCommander guards only the rung into Colonel, so AI pilots
// can rise to Lieutenant Colonel. The ladder ends at Colonel, as stock does.
//
// The other installer choice, "extended promotions", replaces this block with
// a merit ladder on PCP and two flag ranks per nation. Everything else in the
// file - every medal fix - is identical between the two.
"""


def derive_stock_awards(extended: Path, out: Path) -> None:
    """Write the stock-promotion variant from the extended awards.cfg."""
    # Bytes, not read_text(): universal newlines would quietly turn the file's
    # CRLF into LF on the way in, and the variant would ship with the wrong
    # line endings while looking identical in an editor.
    text = extended.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"

    # The promotion block runs from the file's first line to the first
    # country section; the notes run from their own heading to the end.
    head = text.find("//// Eastern Bloc")
    notes = text.find("// Promotion, as modified")
    if head < 0 or notes < 0:
        raise SystemExit("awards.cfg no longer has the markers the stock "
                         "variant is cut at ('//// Eastern Bloc', "
                         "'// Promotion, as modified')")
    block = STOCK_PROMOTION_BLOCK.replace("\n", newline)
    tail = STOCK_PROMOTION_NOTES.replace("\n", newline)
    result = block + text[head:notes] + tail

    # Nothing from the extended ladder may survive the swap.
    for token in ("PCP", "601985", "601986", "ComplSorties>=25"):
        if token in result[: result.find("//// Eastern Bloc")]:
            raise SystemExit(f"stock variant still contains {token!r}")
    out.write_bytes(result.encode("utf-8"))


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
    derive_stock_awards(MOD_ASSETS / "awards.cfg", MOD_ASSETS / STOCK_AWARDS)
    print(f"  derived {STOCK_AWARDS} from awards.cfg")
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
        "There are two versions of awards.cfg. Install ONE of them, renamed to",
        "awards.cfg:",
        "",
        "    awards.cfg         extended promotions - a merit ladder on the",
        "                       game's career points, and two flag ranks for",
        "                       every nation (the installer's default)",
        f"    {STOCK_AWARDS:<18} stock promotions, corrected - the original",
        "                       criteria, with the missing promotion out of",
        "                       Major restored; the ladder ends at Colonel",
        "",
        "Both carry the same medal fixes. Only the promotion block differs.",
        "",
    ]
    for where in sorted(set(MOD_FILES.values())):
        names = sorted(n for n, w in MOD_FILES.items() if w == where)
        if "awards.cfg" in names:
            names.insert(names.index("awards.cfg") + 1,
                         f"{STOCK_AWARDS}  (alternative - see above)")
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
