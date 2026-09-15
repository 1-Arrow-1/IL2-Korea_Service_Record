"""
Find the IL-2 Korea installation.

The first release guessed ``<drive>:\\SteamLibrary\\steamapps\\common\\IL2Series``
on drives C to H and gave up if that missed, which fails for everyone who does
not own the game through Steam — reported on the forum by a user whose copy sat
in ``F:\\IL2Series``. Worse, setup *asks* for the game folder and writes it to
the registry to place the mod, so the tracker was ignoring an answer the user
had already given.

So the order below runs from "told" to "guessed", and every source is tried
before any guessing starts:

1. ``--game`` on the command line
2. ``KOREA_GAME_DIR`` in the environment
3. ``game_dir.txt`` beside the exe, written by setup
4. the registry key setup writes
5. every Steam library on the machine, read out of ``libraryfolders.vdf``
   rather than assumed — Steam libraries can sit anywhere, under any name
6. the handful of places a manual installation usually lands

A folder counts as the game when ``data`` holds the ``.gtp`` archives. That is
true of every installation, Steam or not, played or not. ``data\\Career`` — the
old test — only appears once a career has been flown, so a fresh install was
rejected as "not IL-2 Korea".
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterator, List, Optional

logger = logging.getLogger(__name__)

# Written by the installer next to the exe, alongside locale_setting.txt.
INSTALL_GAME_FILE = "game_dir.txt"
GAME_ENV_VAR = "KOREA_GAME_DIR"
REGISTRY_KEY = r"Software\IL-2 Korea Service Record"
REGISTRY_VALUE = "IL2Path"

# Folder names a manual install is plausibly given, checked at each drive root
# and under the usual parents.
FOLDER_NAMES = ("IL2Series", "IL-2 Korea", "IL2Korea",
                "IL-2 Sturmovik Korea", "Sturmovik Korea")
PARENTS = ("", "Games", "Program Files", "Program Files (x86)",
           "SteamLibrary/steamapps/common", "Steam/steamapps/common")

# The copy sold direct by the developer nests everything one level deeper than
# the Steam copy: F:\IL2Series\game\data, where Steam has F:\...\IL2Series\data.
# So every candidate is tried twice, once as given and once with this appended,
# and a folder the user picks is checked the same way. Missing this is what
# stopped hawax270 installing at all: F:\IL2Series is the right answer to the
# question the wizard asks, and it has no data folder in it.
NESTED = "game"


def looks_like_game(path: Path) -> bool:
    """True when this folder is an IL-2 installation root."""
    data = path / "data"
    if not data.is_dir():
        return False
    try:
        # any() over the iterator: 24 archives, and this runs against every
        # candidate drive, so do not build the whole list.
        return any(data.glob("*.gtp")) or (data / "Career").is_dir()
    except OSError:
        return False


def normalise(start: Path) -> Optional[Path]:
    """
    Accept the root, its ``data`` folder, or anything below, and return the
    root. Users point at ``data\\Career`` because that is the folder they know,
    and at the folder above ``game`` because that is what they chose when they
    installed the game.
    """
    try:
        path = Path(start).expanduser().resolve()
    except (OSError, ValueError):
        return None
    for candidate in (path, *path.parents):
        for probe in (candidate, candidate / NESTED):
            if looks_like_game(probe):
                return probe
    return None


def _from_file() -> Optional[str]:
    """What setup recorded next to the exe."""
    base = (Path(sys.executable).parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent)
    try:
        return (base / INSTALL_GAME_FILE).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None


def _from_registry() -> Optional[str]:
    """What setup wrote to the registry. Per-user first, then machine-wide."""
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, REGISTRY_KEY) as key:
                value = winreg.QueryValueEx(key, REGISTRY_VALUE)[0]
            if value:
                return str(value)
        except OSError:
            continue
    return None


def _steam_root() -> Optional[Path]:
    try:
        import winreg
    except ImportError:
        return None
    for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam",
             "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(hive, key) as handle:
                found = winreg.QueryValueEx(handle, value)[0]
            if found:
                return Path(found)
        except OSError:
            continue
    return None


def steam_libraries() -> List[Path]:
    """
    Every Steam library folder on this machine.

    ``libraryfolders.vdf`` lists them, one ``"path"`` per library, and they can
    live on any drive under any name — which is why guessing "SteamLibrary" at
    a drive root was never reliable even for Steam owners.
    """
    root = _steam_root()
    if root is None:
        return []
    libraries = [root]
    manifest = root / "steamapps" / "libraryfolders.vdf"
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libraries
    for raw in re.findall(r'"path"\s*"([^"]+)"', text):
        try:
            libraries.append(Path(raw.replace("\\\\", "\\")))
        except (OSError, ValueError):
            continue
    return libraries


def _candidates() -> Iterator[Path]:
    """Places to look, cheapest and most likely first."""
    for library in steam_libraries():
        for name in FOLDER_NAMES:
            root = library / "steamapps" / "common" / name
            yield root
            yield root / NESTED

    drives = [Path(f"{letter}:/") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
    for drive in drives:
        if not drive.exists():
            continue
        for parent in PARENTS:
            base = drive / parent if parent else drive
            for name in FOLDER_NAMES:
                yield base / name
                yield base / name / NESTED


def find_game_dir(explicit: Optional[Path] = None) -> Optional[Path]:
    """The installation root, or None when nothing was found."""
    told = [
        ("--game", str(explicit) if explicit else None),
        (GAME_ENV_VAR, os.environ.get(GAME_ENV_VAR)),
        (INSTALL_GAME_FILE, _from_file()),
        ("registry", _from_registry()),
    ]
    for source, value in told:
        if not value:
            continue
        found = normalise(Path(value))
        if found:
            logger.info("Game directory from %s: %s", source, found)
            return found
        # Being told and being wrong is worth a line in the log — this is
        # exactly the case a bug report needs to distinguish from "not set".
        logger.warning("%s is set to %s, which is not an IL-2 installation",
                       source, value)

    for candidate in _candidates():
        try:
            if looks_like_game(candidate):
                logger.info("Game directory found at %s", candidate)
                return candidate
        except OSError:
            continue

    logger.warning("No IL-2 Korea installation found. Searched Steam's "
                   "libraries and the usual folders on every drive.")
    return None
