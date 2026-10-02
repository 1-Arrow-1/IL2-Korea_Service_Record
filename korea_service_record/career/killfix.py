"""
Removes the napalm re-kill inflation from ``killStats``.

Since the 29 September 2026 build (25605106), napalm burning on an airfield's
block group logs a fresh kill for the same destroyed part every 2 seconds for
the fire's whole ~178 s life: 90 kills per fire per part, and several fires
overlap. The career processor adds every one of them to ``sortie.killStats``,
and from there to ``pilot`` and ``squadron``. Mission 58 of the 12th FBS
career destroyed 13 objects and booked 867. A napalm drop on a lone 61-K AA
gun books one kill, so the fault is block-group parts under fire only. The
short bursts of re-kills in pre-update logs are the same flaw at small scale.

The ``event`` table is not inflated. Its type-0 rows name each destroyed
object once (``Mil_boxes_02``, ``Static_plane_La11``, ``61K``), and the game's
own ``statobjects.json`` files every one of those names under the killStats
category it counts as. Rebuilt that way, 266 of the 355 sorties with kill rows
across six careers reproduce their stored killStats exactly, which is what
makes the rebuild trustworthy.

The rule, per leaf category: the smaller of the stored count and the rebuilt
one.

* 84 sorties store more than they rebuild - in every category at once, never
  mixed, and only in airfield categories (MilitaryFacility, StaticPlane,
  MilEquip, IndustrialBuilding, Trailer, AirfieldFacility). Those are the
  re-kills, and the rebuilt count is the truth.
* 5 sorties rebuild MORE than they store, in LightFlak alone: a gun mounted on
  a truck (``61K-onTruck-attach``) gets its own kill row but the game counts it
  with the truck. Taking the minimum keeps the game's figure there.

A row whose name the table does not know (one blank name in 355 sorties) is
treated as slack for every category, so an unknown object can never be the
reason a real kill disappears. A sortie with kills but no kill rows at all is
left untouched; none exists today.

Award progress must NOT use the corrected figures: the game decides awards on
its own inflated counter, so a prediction made on the real count would be
wrong about when an award fires.
"""

import logging
from collections import Counter
from typing import Dict, Iterable, Optional

from .killstats import KEY_FIXES

logger = logging.getLogger(__name__)

STAT_OBJECTS = "nsdata/assets/worldobjects/statobjects.json"
STAT_REPORTING = "nsdata/assets/worldobjects/statreporting.json"

# Decoration on kill-row names that statobjects.json lists bare.
_SUFFIXES = ("-ontruck-attach", "-attach", "_npc")

# statreporting.json "internal" group -> the rollup key killStats writes.
_ROLLUP_OF_GROUP = {
    "killAircraft": "Aircraft",
    "killMateriel": "Materiel",
    "killBuilding": "Building",
    "killRailroad": "Railroad",
}


def _bare(key: str) -> str:
    """``killStaticPlane`` -> ``StaticPlane``, as killStats keys it."""
    return key[4:] if key.startswith("kill") else key


class KillCategories:
    """The game's object -> killStats category table, and the rollups."""

    def __init__(self, objects: Dict[str, str], rollup_of: Dict[str, str]):
        self.objects = objects          # lower-case object name -> leaf key
        self.rollup_of = rollup_of      # leaf key -> rollup key

    @classmethod
    def from_resolver(cls, resolver) -> Optional["KillCategories"]:
        from ..gamedata import loads_lenient
        objects_text = resolver.read_text(STAT_OBJECTS)
        reporting_text = resolver.read_text(STAT_REPORTING)
        if not objects_text or not reporting_text:
            logger.info("Kill correction off: %s or %s not found",
                        STAT_OBJECTS, STAT_REPORTING)
            return None
        objects: Dict[str, str] = {}
        for category, body in loads_lenient(objects_text).items():
            if not isinstance(body, dict):
                continue
            for name in body.get("objects", []):
                objects[str(name).lower()] = _bare(category)
        rollup_of: Dict[str, str] = {}
        internal = loads_lenient(reporting_text).get("internal", {})
        for group, members in internal.items():
            rollup = _ROLLUP_OF_GROUP.get(group)
            if rollup:
                for member in members:
                    rollup_of[_bare(member)] = rollup
        if not objects:
            return None
        return cls(objects, rollup_of)

    def category(self, name: str) -> Optional[str]:
        key = (name or "").lower()
        if key in self.objects:
            return self.objects[key]
        for suffix in _SUFFIXES:
            if key.endswith(suffix) and key[:-len(suffix)] in self.objects:
                return self.objects[key[:-len(suffix)]]
        return None


def reductions(raw: Optional[str], kill_names: Iterable[str],
               table: KillCategories) -> Counter:
    """
    How far each killStats key of one sortie is inflated.

    Keys are as stored - leaves and their rollups - so the same Counter can be
    subtracted from the sortie's string and from the pilot's and squadron's
    running totals. Empty when the sortie is clean.
    """
    names = list(kill_names)
    if not raw or not names:
        return Counter()
    rebuilt: Counter = Counter()
    unknown = 0
    for name in names:
        category = table.category(name)
        if category is None:
            unknown += 1
        else:
            rebuilt[category] += 1
    out: Counter = Counter()
    for pair in raw.split("&"):
        key, _, value = pair.partition("=")
        key = KEY_FIXES.get(key, key)
        rollup = table.rollup_of.get(key)
        if rollup is None:
            continue                    # a rollup itself, or not a leaf we know
        try:
            stored = int(value)
        except ValueError:
            continue
        excess = stored - (rebuilt[key] + unknown)
        if excess > 0:
            out[key] += excess
            out[rollup] += excess
    return out


def subtract(raw: Optional[str], cut: Counter) -> Optional[str]:
    """``raw`` with ``cut`` taken off, keys and order as stored. Never below 0."""
    if not raw or not cut:
        return raw
    left = cut.copy()
    parts = []
    for pair in raw.split("&"):
        key, sep, value = pair.partition("=")
        canonical = KEY_FIXES.get(key, key)
        if sep and left.get(canonical):
            try:
                n = int(value)
            except ValueError:
                parts.append(pair)
                continue
            # Railroad is stored under two spellings; the cut is spent across
            # both, so it is tracked by the canonical key.
            take = min(n, left[canonical])
            left[canonical] -= take
            parts.append(f"{key}={n - take}")
        else:
            parts.append(pair)
    return "&".join(parts)
