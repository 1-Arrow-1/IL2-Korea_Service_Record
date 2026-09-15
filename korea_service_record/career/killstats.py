"""
Parser for the packed ``killStats`` string used by IL-2 Korea.

Great Battles stores kills as separate integer columns (``killTruck``,
``killLightTank``, ...). Korea packs them into one URL-ish string on ``pilot``,
``sortie`` and ``squadron``::

    Aircraft=5&Building=1&LightFighter=4&Materiel=1&StaticPlane=1

Two traps, both confirmed against a live career:

1. ``Aircraft`` is a **rollup**, not a peer. It equals the sum of the aircraft
   subtypes, and it includes ``StaticPlane`` (aircraft destroyed on the ground).
   Summing every key double-counts; summing subtypes and the rollup does too.

2. ``AirObjSortie`` in ``awards.cfg`` counts **airborne kills only**. The award
   engine excludes parked aircraft, so airborne = ``Aircraft - StaticPlane``.
   Do not try to derive this by classifying kill-event names instead: ground
   clutter such as ``Windsock`` carries none of the ``Static_``/``Mil_``
   prefixes and silently inflates the count.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Rollup keys: subtotals the game writes beside the categories they sum.
# Counting a rollup *and* its children double-counts, so rollups are never
# rows and never added. The grouping is the game's own, from
# nsdata/assets/worldobjects/statreporting.json ("internal"):
#
#   Aircraft = every aircraft type + StaticPlane
#   Materiel = Car, Truck, Trailer, armour, Detachment, guns, flak,
#              Searchlight, Radar, RocketLauncher, MilEquip
#   Building = MilitaryFacility, AirfieldFacility, IndustrialBuilding,
#              Fortification, Bridge, Dam, TownBuilding, RuralYard, OtherBuilding
#   Railroad = TrainLocomotive, TrainVagon, RailwayStationFacility, RailwayBridge
#
# Proven on a squadron row: Materiel=895 is exactly the sum of its members,
# Building 681 = 597 + 62 + 22, and Raildoad=20 + Railroad=23 = 43 = the four
# rail members - the rail subtotal is written under two spellings, one of
# them the game's typo. Materiel is what awards.cfg's GrObj counts.
ROLLUP_KEYS = {"Aircraft", "Materiel", "Building", "Railroad"}

# The game's own misspelt keys, folded into the right one at parse time.
KEY_FIXES = {"Raildoad": "Railroad"}

BUILDING_CHILDREN = {"MilitaryFacility", "AirfieldFacility", "IndustrialBuilding",
                     "Fortification", "Bridge", "Dam", "TownBuilding", "RuralYard",
                     "OtherBuilding"}

# Aircraft subtypes seen in live data. Used for the air-kill breakdown only;
# the airborne total is computed from the rollup, not from this set, so an
# unseen subtype cannot silently drop a kill.
AIR_SUBTYPES = {
    "LightFighter", "JetFighter", "HeavyFighter", "Bomber",
    "Attacker", "Transport", "Recon", "MediumAttackPlane",
}

STATIC_AIR_KEYS = {"StaticPlane"}

# Leaf categories only; the rollups above are skipped. Membership follows
# statreporting.json, regrouped into the six headline figures the page shows.
GROUND_CATEGORIES: Dict[str, set] = {
    "vehicles": {"Truck", "Car", "Trailer", "ArmouredVehicle", "MilEquip",
                 "Detachment"},
    "armour": {"LightTank", "MediumTank", "HeavyTank"},
    "artillery": {"HeavyFlak", "LightFlak", "HeavyGun", "LightGun",
                  "MachineGun", "Mortar", "RocketLauncher", "Searchlight", "Radar"},
    "buildings": BUILDING_CHILDREN,
    "rail": {"TrainLocomotive", "TrainVagon", "RailwayStationFacility", "RailwayBridge"},
    "naval": {"SmallCraft", "MediumCraft", "MediumShip", "LargeShip", "Destroyer",
              "Cruiser", "Battleship", "Carrier", "Submarine",
              "SeaSmallObj", "SeaCargoObj", "SeaDestrObj", "SeaSubObj"},
}


class KillStats:
    """Parsed view of one ``killStats`` string."""

    def __init__(self, raw: Optional[str]):
        self.raw = raw or ""
        self.counts: Dict[str, int] = {}
        for pair in self.raw.split("&"):
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            # The game books rail kills under two keys, one of them its own
            # typo (Raildoad=20&Railroad=23 on one squadron), and names
            # neither in any language. One row, spelt right.
            key = KEY_FIXES.get(key, key)
            try:
                self.counts[key] = self.counts.get(key, 0) + int(value)
            except ValueError:
                logger.debug("Non-integer killStats value: %s=%s", key, value)

    def get(self, key: str) -> int:
        return self.counts.get(key, 0)

    # -- aircraft -----------------------------------------------------------

    @property
    def aircraft_total(self) -> int:
        """Every aircraft destroyed, airborne and parked."""
        return self.get("Aircraft")

    @property
    def static_air(self) -> int:
        """Aircraft destroyed on the ground. Does not count toward AirObjSortie."""
        return sum(self.get(k) for k in STATIC_AIR_KEYS)

    @property
    def airborne(self) -> int:
        """
        Airborne victories — the value ``AirObjSortie``/``AirObj`` compare
        against in awards.cfg. Clamped at zero: a malformed string must not
        produce a negative kill count.
        """
        return max(0, self.aircraft_total - self.static_air)

    @property
    def air_breakdown(self) -> Dict[str, int]:
        return {k: v for k, v in self.counts.items()
                if k in AIR_SUBTYPES and v}

    # -- ground -------------------------------------------------------------

    @property
    def ground_targets(self) -> int:
        """
        The figure the game shows as GROUND TARGETS on the pilot file.

        Every leaf category that is not an airborne aircraft: vehicles,
        guns, buildings, rail, ships, and aircraft destroyed on the ground (a
        parked plane is a ground target). The rollups are skipped, since
        each is exactly the sum of its members. Matches the panel exactly
        for every pilot checked.
        """
        return sum(v for k, v in self.counts.items()
                   if k not in ROLLUP_KEYS and k not in AIR_SUBTYPES)

    @property
    def ground_total(self) -> int:
        """Kept as an alias: with the rollups understood there is no clutter."""
        return self.ground_targets

    def category_totals(self) -> Dict[str, int]:
        """Ground breakdown by leaf category; rollups and aircraft skipped."""
        out = {name: 0 for name in GROUND_CATEGORIES}
        out["other"] = 0
        for key, value in self.counts.items():
            if key in ROLLUP_KEYS or key in AIR_SUBTYPES or key in STATIC_AIR_KEYS:
                continue
            for name, members in GROUND_CATEGORIES.items():
                if key in members:
                    out[name] += value
                    break
            else:
                out["other"] += value
        return out

    def unknown_keys(self) -> set:
        """Keys not in any known bucket — surfaced so new ones get classified."""
        known = set(ROLLUP_KEYS) | AIR_SUBTYPES | STATIC_AIR_KEYS
        for members in GROUND_CATEGORIES.values():
            known |= members
        return {k for k in self.counts if k not in known}

    def __repr__(self) -> str:
        return (f"<KillStats airborne={self.airborne} static_air={self.static_air} "
                f"ground={self.ground_total}>")
