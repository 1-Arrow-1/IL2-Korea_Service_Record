"""
Notice when a game update has changed a screen the mod replaces.

The installer puts two of the game's own UI files loose under ``data\\`` so
custom portraits show on the career screens (the pilot photo binding reads
``/Assets/PilotPhotos/{0}.dds`` instead of the SmallPhotos atlas). A loose file
always wins over the archives, so when a game update changes one of these
screens, the mod's copy silently hides the change - 2.2.2 and 2.2.3 shipped
copies older than 1.004b's, which hid its pending-awards dot.

The mod's copies are now rebuilt from the game's own file with only the
photo binding changed. ``BASES`` holds the SHA-256 of the game original each
copy was built from. If the archive's file no longer matches while the mod's
loose copy is installed, the game has moved on and the copy is stale; the
career page says so.
"""

import hashlib
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Game build 1.004b (hotfix of 2026-10-02), Interface.gtp.
BASES: Dict[str, str] = {
    "nsdata/controls/career/career.rdict.xaml":
        "8afd0ae5c215c2ef368bfcb075cf746a90658c39e2a623401e158f4139cbcdb8",
    "nsdata/controls/career/events/eventsnotificationcontrol.xaml":
        "a17426263fbd92831042eb497c4408a47e2e5137fe7e34d56d4e5ea3355bba04",
}


def stale(resolver) -> List[str]:
    """
    File names of installed overrides whose game original has changed.
    Reads the archive itself, never the loose copy. An override that is not
    installed, or an original the archive does not hold, is not reported.
    """
    out = []
    for vpath, base in BASES.items():
        try:
            if not resolver._loose_path(vpath).is_file():
                continue
            original = resolver._extract(vpath)
        except Exception as exc:              # noqa: BLE001 - a check must never break the page
            logger.info("UI override check skipped for %s: %s", vpath, exc)
            continue
        if original is None:
            continue
        if hashlib.sha256(original).hexdigest() != base:
            logger.warning("Game update changed %s; the mod's loose copy now hides it", vpath)
            out.append(vpath.rsplit("/", 1)[-1])
    return out
