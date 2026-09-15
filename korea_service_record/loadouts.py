"""
What each pilot carried on a mission.

``mission.pilotsList`` records, per aircraft on the mission, the ammunition
scheme (``payloadId``), the fuel fraction and what it all cost the squadron::

    ammoCost,fuel,fuelCost,guns,mods,payloadId,pilotId,planeId|10,0.67800,690,belt,load|0,0|0,1|...|0,-1,30,12,3|...

The ``guns`` field is a nested table (belt and load per gun station) whose
own separators are the same ``|`` and ``,`` as the outer record's, and it
is not escaped, so the format cannot be split naively. The header is fixed,
though: three numeric fields open a record and three close it, so a record
is found by its ends and the guns table is whatever lies between.

``payloadId`` is the ``[Ammunition=N]`` block of the plane's script,
``luascripts/worldobjects/planes/<stem>.txt`` (Scripts.gtp). Each block
lists its stores as ``Bomb<i>=<holder>, "<object path>"``; the object's file
stem is the key the game names in every language in
``nsdata/assets/ammunition/info.locale=<lang>.json`` — ``BOMB_238kg_USA_M64``
is "AN-M64A1 500 lb". Count the stems and the loadout reads as the hangar
shows it: "2 × AN-M64A1 500 lb, 6 × HVAR SAP 5\"". Drop tanks are stores
too (``FTANK_...``) and are listed the same way. Scheme 0 is "Empty":
guns only.
"""

import logging
import re
import urllib.parse
from collections import Counter, OrderedDict
from pathlib import PurePath
from typing import Dict, List, Optional, Tuple

from .gamedata import loads_lenient

logger = logging.getLogger(__name__)

_RECORD = re.compile(
    r"(?P<ammoCost>-?\d+),(?P<fuel>-?[\d.]+),(?P<fuelCost>-?\d+),"
    r"(?P<guns>.*?),"
    r"(?P<payloadId>-?\d+),(?P<pilotId>-?\d+),(?P<planeId>-?\d+)"
    r"(?=\|-?\d+,-?[\d.]+,-?\d+,|$)")

_BLOCK = re.compile(r"^\[Ammunition=(\d+)\](.*?)^\[end\]", re.M | re.S | re.I)
_STORE = re.compile(r'^\s*Bomb\d+\s*=\s*-?\d+\s*,\s*"([^"]+)"', re.M | re.I)
_NAME = re.compile(r'^\s*name\s*=\s*"([^"]*)"', re.M | re.I)


def parse_pilots_list(raw: Optional[str]) -> List[Dict[str, object]]:
    """The per-aircraft records of one mission, keyed by pilot id."""
    if not raw:
        return []
    text = urllib.parse.unquote(raw)
    head, _, body = text.partition("|")
    if not head.startswith("ammoCost,fuel,fuelCost"):
        logger.debug("Unexpected pilotsList header: %s", head[:60])
        return []
    out = []
    for m in _RECORD.finditer(body):
        try:
            out.append({
                "pilot_id": int(m.group("pilotId")),
                "plane_id": int(m.group("planeId")),
                "payload_id": int(m.group("payloadId")),
                "fuel": float(m.group("fuel")),
                "fuel_cost": int(m.group("fuelCost")),
                "ammo_cost": int(m.group("ammoCost")),
            })
        except ValueError:
            continue
    return out


class AmmoSchemes:
    """Ammunition schemes per aircraft type, named in the game's words."""

    def __init__(self, resolver, lang: str = "eng"):
        self.resolver = resolver
        self.lang = lang
        self._schemes: Dict[str, Dict[int, List[Tuple[str, int]]]] = {}
        self._names: Optional[Dict[str, str]] = None

    def _store_names(self) -> Dict[str, str]:
        if self._names is None:
            text = self.resolver.read_text(
                f"nsdata/assets/ammunition/info.locale={self.lang}.json")
            self._names = loads_lenient(text) if text else {}
        return self._names

    def _load(self, plane: str) -> Dict[int, List[Tuple[str, int]]]:
        plane = plane.lower()
        if plane in self._schemes:
            return self._schemes[plane]
        schemes: Dict[int, List[Tuple[str, int]]] = {}
        text = self.resolver.read_text(f"luascripts/worldobjects/planes/{plane}.txt")
        if text:
            for m in _BLOCK.finditer(text):
                body = m.group(2)
                counts: "OrderedDict[str, int]" = OrderedDict()
                for path in _STORE.findall(body):
                    stem = PurePath(path.replace("\\", "/")).stem
                    counts[stem] = counts.get(stem, 0) + 1
                schemes[int(m.group(1))] = list(counts.items())
        else:
            logger.info("No plane script for %s; loadouts unnamed", plane)
        self._schemes[plane] = schemes
        return schemes

    def stores(self, plane: str, payload_id: int) -> List[Dict[str, object]]:
        """[{name, count}] for a scheme, in the script's own order; [] for guns only."""
        scheme = self._load(plane).get(payload_id)
        if not scheme:
            return []
        names = self._store_names()
        # Left and right drop tanks are separate objects with one name
        # (FTANK_454L_USA_F86L / ...F86R, both "Drop Tank 120 gal"), so the
        # merge is by name, not stem.
        merged: "OrderedDict[str, int]" = OrderedDict()
        for stem, n in scheme:
            name = names.get(stem) or stem
            merged[name] = merged.get(name, 0) + n
        return [{"name": name, "count": n} for name, n in merged.items()]

    def describe(self, plane: str, payload_id: int) -> str:
        """'2 × AN-M64A1 500 lb, 6 × HVAR SAP 5"' — empty for guns only."""
        return ", ".join(f"{s['count']} × {s['name']}" for s in self.stores(plane, payload_id))
