"""
Names and categories for the things a pilot destroys.

Kill events record a raw object id — ``Yak9P``, ``DShK``, ``StudebakerUS6``,
``Mil_boxes_04``. The game ships a proper name and a category for each *real*
target under ``nsdata/assets/worldobjects/<group>/<object>/``::

    info.json              {"worldObject": {"category": "artillery", ...}}
    info.locale=eng.json   {"name": "12.7-mm DShK machine gun", ...}

99 objects have them: aircraft, vehicles, artillery, ships and trains.

Scenery does not, and that is informative rather than a gap. Crates, coils,
barrels, tents and windsocks live in ``luascripts/worldobjects/blocks/`` with no
name and no category — the same things ``killStats`` lumps into ``Materiel``
and excludes from the GROUND TARGETS figure. So "has an info.locale entry" is
the game's own answer to "is this a target worth naming", and the debriefing
uses it to separate real kills from the scenery a napalm run flattens.

Building the index needs one pass over Interface.gtp's ~9000-entry FAT, so the
result is cached on disk and rebuilt only when missing.
"""

import logging
import re
from pathlib import Path
from typing import Dict, NamedTuple, Optional

from .gamedata import loads_lenient

logger = logging.getLogger(__name__)

INDEX_VERSION = 2
WORLDOBJECT_ROOT = "nsdata/assets/worldobjects"

# Raw ids carry decoration the folder names do not.
_PREFIXES = ("static_plane_", "static_car_", "static_munition_", "static_")
_SUFFIXES = ("-ontruck-attach", "-attach", "_npc")


class WorldObject(NamedTuple):
    key: str
    name: str
    category: str
    group: str          # fixedobjects | vehicles | ships | planes | trains

    @property
    def is_aircraft(self) -> bool:
        return self.group == "planes"


def normalise(raw: str) -> str:
    """
    Reduce a kill-event target id to the folder name the game uses.

    ``Static_plane_Yak9P`` -> ``yak9p``; ``61K-onTruck-attach`` -> ``61k``;
    ``DShK-AA`` -> ``dshk-aa``, which is tried before falling back to ``dshk``.
    """
    key = (raw or "").strip().lower()
    for prefix in _PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    for suffix in _SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key


class WorldObjectIndex:
    """Lookup from raw kill-event names to a display name and category."""

    _INFO_RE = re.compile(
        r"^/?nsdata/assets/worldobjects/([^/]+)/([^/]+)/info(\.locale=(\w+))?\.json$",
        re.I)

    def __init__(self, resolver, lang: str = "eng"):
        self.resolver = resolver
        self.lang = lang
        self.objects: Dict[str, WorldObject] = {}
        self._load()

    # -- build / cache -----------------------------------------------------

    def _cache_file(self) -> Path:
        return (self.resolver.cache_dir / "index"
                / f"worldobjects.{self.lang}.v{INDEX_VERSION}.json")

    def _load(self) -> None:
        cache = self._cache_file()
        if cache.is_file():
            try:
                data = loads_lenient(cache.read_text(encoding="utf-8"))
                self.objects = {k: WorldObject(**v) for k, v in data.items()}
                logger.info("World object index: %d entries (cached)", len(self.objects))
                return
            except (OSError, TypeError, ValueError) as exc:
                logger.warning("Rebuilding world object index: %s", exc)
        self._build()
        self._save(cache)

    def _build(self) -> None:
        from .gtp.archive import GtpArchive, find_archives

        found: Dict[str, Dict[str, str]] = {}
        for archive_path in find_archives(self.resolver.game_dir):
            try:
                with GtpArchive(archive_path) as archive:
                    paths = [e.vpath for e in archive.entries()
                             if self._INFO_RE.match(e.vpath)]
            except (OSError, ValueError):
                continue
            if not paths:
                continue
            for vpath in paths:
                match = self._INFO_RE.match(vpath)
                group, key, _, lang = match.groups()
                if lang and lang.lower() != self.lang:
                    continue
                entry = found.setdefault(key.lower(),
                                         {"key": key.lower(), "name": "",
                                          "category": "", "group": group.lower()})
                data = loads_lenient(
                    self.resolver.read_text(vpath.lstrip("/")) or "{}")
                if lang:
                    entry["name"] = data.get("name") or entry["name"]
                else:
                    entry["category"] = (data.get("worldObject", {})
                                         .get("category") or entry["category"])
            break   # every info.json lives in the same archive

        self.objects = {k: WorldObject(**v) for k, v in found.items() if v["name"]}
        logger.info("World object index: %d entries (built)", len(self.objects))

    def _save(self, cache: Path) -> None:
        import json
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({k: v._asdict() for k, v in self.objects.items()},
                           indent=1),
                encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot cache world object index: %s", exc)

    # -- lookup ------------------------------------------------------------

    def lookup(self, raw: str) -> Optional[WorldObject]:
        key = normalise(raw)
        hit = self.objects.get(key)
        if hit is not None:
            return hit
        # "DShK-AA" has no folder of its own; fall back to the base weapon.
        if "-" in key:
            return self.objects.get(key.rsplit("-", 1)[0])
        return None

    def describe(self, raw: str) -> Dict[str, object]:
        """
        Classify one kill-event target.

        ``named`` is False for scenery, which the caller should count rather
        than list.
        """
        obj = self.lookup(raw)
        parked = (raw or "").lower().startswith("static_")
        if obj is None:
            return {"named": False, "name": raw, "category": "scenery",
                    "parked": parked, "aircraft": False}
        return {"named": True, "name": obj.name, "category": obj.category,
                "parked": parked, "aircraft": obj.is_aircraft}
