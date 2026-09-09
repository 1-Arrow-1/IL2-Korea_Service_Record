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
import urllib.parse
from pathlib import Path
from typing import Dict, NamedTuple, Optional

from .gamedata import loads_lenient

logger = logging.getLogger(__name__)

INDEX_VERSION = 3
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

    Some ids arrive url-encoded a second time: mission.result is unquoted as a
    whole, which leaves ``t34%2d85`` still holding an escaped hyphen. Those
    were failing every lookup and being written off as scenery, which quietly
    lost a T-34-85, a BM-13 Katyusha, the DShK guns and a locomotive from the
    log. Unquoting again is safe for the ids that were only encoded once,
    since none of them contain a percent sign.
    """
    key = urllib.parse.unquote(raw or "").strip().lower()
    for prefix in _PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    for suffix in _SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key


# ---------------------------------------------------------------------------
# Scenery
# ---------------------------------------------------------------------------

# Scenery has no info.locale entry, so the log used to print the engine id:
# "Mil_ammoBoxes_02", "Static_munition_SU_FAB100Stack_Full_A". These stay
# unnamed in the sense that matters — the game does not count them as targets
# and neither do we — but a debrief a person reads should still say what was
# hit. Keys are the id with its group prefix and its count/variant suffixes
# stripped; anything missing falls through to a generic word-split.
SCENERY_GROUPS = {
    "arf": "Airfield",
    "port_yard": "Dockside",
    "rw": "Railway",
    "ind": "",
    "mil": "",
}

SCENERY_NOUNS = {
    "boxes": "supply crates",
    "ammoboxes": "ammunition crates",
    "barrels": "fuel barrels",
    "coil": "cable coils",
    "coils": "cable coils",
    "coils_barrels": "coils and barrels",
    "tent": "tent",
    "crane": "crane",
    "hangar": "hangar",
    "nissenhut": "Nissen hut",
    "barrack": "barracks",
    "dugout": "dugout",
    "camonet": "camouflage netting",
    "shower": "washhouse",
    "warehouse": "warehouse",
    "storage": "storage tank",
    "reservoir": "reservoir",
    "cistern": "fuel cistern",
    "fuelcisterns": "fuel cisterns",
    "fuelstorage": "fuel storage",
    "watertower": "water tower",
    "coaltower": "coal tower",
    "lighttower": "signal tower",
    "controltower": "control tower",
    "crossing_cabin": "crossing cabin",
    "tower": "tower",
    "tower_auxiliary": "auxiliary tower",
    "trailer_generator": "generator trailer",
    "trailer_cistern": "tanker trailer",
    "trailer_cargo": "cargo trailer",
    "mine_office": "mine office",
    "mine_warehouse": "mine warehouse",
    "sawmill_logs": "log stack",
    "sawmill_planks": "plank stack",
    "cargocart_m5_ammo": "ammunition cart",
    "bridge_rw_cptl": "railway bridge",
    # munition dumps, named for what is stacked rather than the stack state
    "fab100stack": "FAB-100 bomb stack",
    "fueltank250stack": "fuel tank stack",
    "fueltankstack": "drop tank stack",
    # infantry: real enough to shoot at, but the game ships no name for them
    "squad-rifle": "rifle squad",
    "squad-mg": "machine-gun squad",
    "squad-smg": "submachine-gun squad",
}

# _01, _2x, _05x, _4xA, _block_02, and the _Full/_Half/_Empty fill states.
_DECORATION = re.compile(
    r"(_block)?(_\d+)?(_\d*x[a-z]?)?(_(full|half|empty))?(_[a-z])?$", re.I)
_NATIONS = {"prc": "PRC", "dprk": "DPRK", "su": "Soviet", "us": "US"}


def humanise(raw: str) -> str:
    """A readable label for an object the game ships no name for."""
    key = urllib.parse.unquote(raw or "").strip()
    key = re.sub(r"^static_(munition|car|equipment|plane)_", "", key, flags=re.I)

    group = ""
    for prefix, word in SCENERY_GROUPS.items():
        if key.lower().startswith(prefix + "_"):
            key = key[len(prefix) + 1:]
            group = word
            break

    # Nation and year tags carried by the infantry ids: squad-rifle-1950-prc
    nation = ""
    parts = key.split("-")
    if len(parts) > 2 and parts[-1].lower() in _NATIONS:
        nation = _NATIONS[parts[-1].lower()]
        key = "-".join(parts[:-1])
    key = re.sub(r"-(19|20)\d\d$", "", key)
    # SU/US tags on munition stacks: SU_FAB100Stack_Full
    match = re.match(r"^(su|us)_(.*)$", key, re.I)
    if match:
        key = match.group(2)

    # Decorations stack: "boxes_02_block_02" carries an index, a block tag and
    # another index, so they come off one layer at a time.
    stripped = key
    for _ in range(4):
        shorter = _DECORATION.sub("", stripped)
        if shorter == stripped or not shorter:
            break
        stripped = shorter
    noun = (SCENERY_NOUNS.get(stripped.lower())
            or SCENERY_NOUNS.get(key.lower()))
    if noun is None:
        # Unknown: split Camel_case_01 into words rather than print the id.
        words = re.sub(r"[_-]+", " ", stripped).strip()
        words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words)
        noun = words.lower() or raw

    label = f"{group} {noun}".strip() if group else noun
    if nation:
        label = f"{label} ({nation})"
    return label[:1].upper() + label[1:]


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
            return {"named": False, "name": humanise(raw), "category": "scenery",
                    "parked": parked, "aircraft": False}
        return {"named": True, "name": obj.name, "category": obj.category,
                "parked": parked, "aircraft": obj.is_aircraft}
