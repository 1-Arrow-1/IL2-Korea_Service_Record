"""
Build the archive that goes on the forum.

    python tools/make_release_zip.py

The setup program is self-contained — it carries the tracker, the mod (41
files, two of them alternative awards.cfg variants) and the manual-install
list, and the tracker in turn carries its own C runtime,
so there is no redistributable to chase. So the zip is that one file, plus a
README at the root: a download outlives the thread it came from, and a reader
who finds this file with the forum post long scrolled away should still be able
to work out what it is.

An earlier version also shipped the mod loose, for readers who would not run an
installer against their game folder. Dropped — the author is known on that
forum, which was the whole force of the argument, and it cost 4.2 MB. Anyone
who does want to install by hand can be sent the files in the thread; the
authoritative copy is installer/mod/assets either way.
"""

import hashlib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION = "1.4.0"
SETUP = REPO / "installer" / "Output" / f"IL2_Korea_Service_Record_Setup_v{VERSION}.exe"
OUT = REPO / "installer" / "Output" / f"IL-2 Korea Service Record v{VERSION}.zip"
ROOT = f"IL-2 Korea Service Record v{VERSION}"

README = f"""IL-2 KOREA SERVICE RECORD  v{VERSION}
A service record for your IL-2 Sturmovik: Korea career, with an optional fix
for the game's award definitions.


INSTALLING

  Everything is in IL2_Korea_Service_Record_Setup_v{VERSION}.exe.

  1. Run the setup program. Choose your language, then choose both
     components: the Service Record and the Awards Mod.

     Under the Awards Mod, pick one promotion system:

       Extended (recommended)  Rank is earned on merit, using the game's own
                               career points, and every nation gets two flag
                               ranks above Colonel.
       Stock, corrected        The game's original criteria, with one fix:
                               the stock game has no promotion out of Major,
                               so a commander could never rise. That rung is
                               restored; the ladder still ends at Colonel.

     Both carry the same medal fixes. You can switch by running setup again.
  2. Point it at your IL-2 Korea folder. Setup usually finds it by itself,
     Steam or not. If your copy came direct from the developer the game lives
     in a "game" subfolder - setup accepts either that or the folder above.
  3. In the game, switch modifications on:
         Settings -> General -> Enable modifications
     Without this the game ignores modded files entirely and the awards mod
     does nothing at all.
  4. Fly a mission, then open the Service Record from the Start Menu.

It opens in your browser and puts a small star in the notification area, by
the clock. Right-click that to close it - shutting the browser tab leaves it
running in the background.


NOTES

  * Windows only. Nothing else to install - no Python, no Visual C++
    redistributable.
  * If something goes wrong, %LOCALAPPDATA%\\IL2KoreaTracker\\tracker.log has
    the details from the last run. Please include it with any bug report.
  * The Service Record is read-only. It never writes to a career file and
    cannot cost you a campaign. Its own settings and any pilot photographs
    you add live under %LOCALAPPDATA%\\IL2KoreaTracker.
  * No game content is redistributed here. The application reads the art and
    text it needs from your own installation.
  * Uninstalling removes both. The mod is additions only, so deleting its
    files simply returns the game to reading its own archives. Your careers
    and the medals in them are untouched either way.
  * Verifying game files in Steam removes loose mod files. If your medals
    stop appearing after a game update, run setup again.
  * Windows Defender may flag the setup program on download as
    "Trojan:Script/Wacatac" or similar. That is its machine-learning
    heuristic reacting to an unsigned program built with PyInstaller, a
    well-known false positive; the same heuristic flags PyInstaller's own
    source download. The program is Python and Flask in a folder; you can
    verify what you have against the checksum below, or upload it to
    virustotal.com.

    SHA-256 of IL2_Korea_Service_Record_Setup_v{VERSION}.exe:
    {{sha256}}
"""


def main() -> int:
    if not SETUP.is_file():
        raise SystemExit(f"Not built yet: {SETUP.name}\n"
                         "Run: iscc installer\\IL2_Korea_Service_Record.iss")

    digest = hashlib.sha256(SETUP.read_bytes()).hexdigest()
    readme = README.replace("{sha256}", digest)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{ROOT}/README.txt", readme.replace("\n", "\r\n"))
        zf.write(SETUP, f"{ROOT}/{SETUP.name}")

    size = OUT.stat().st_size / 1024 / 1024
    print(f"  {OUT.name}")
    print(f"     {size:.1f} MB")
    print(f"     setup sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
