"""
CareerAggregator: turns the raw tables into the shapes the front end renders.

The detail payload follows the Great Battles tracker's three-column service
record rather than inventing a new one:

    left    pilot information, other incidences, promotions & awards
    middle  career summary — combat results, air kills by type, missions flown,
            career progression
    right   mission debriefings, newest first
    bottom  squadron statistics (the full roster)

Awards and promotions live in the left column only. Earlier drafts also listed
them in a "service record" panel, which said the same thing twice; the
incidences list now carries only what is *not* an award — wounds, hospital
spells, aircraft lost, arrivals.

Everything here is derived, never stored. The decoding lives in the sibling
modules (killstats, attributes, events) so this file stays about assembly.
"""

import html
import json
import math
import logging
import os
import re
import urllib.parse
from collections import Counter, OrderedDict
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

from ..assets import AssetResolver
from ..flightlog import SELF as SELF_DAMAGE, FlightLogIndex
from ..gamedata import (COUNTRY_FLAGS, COUNTRY_NAMES, COUNTRY_SEALS, COUNTRY_STAMPS, AwardsConfig, FrontLines,
                        LocaleStrings, MissionDescriptions, DEFAULT_TVD, PLANE_TYPES)
from ..geo import (MapTiles, Overlay, WAYPOINT_TAKEOFF, WAYPOINT_LANDING,
                   parse_point, parse_route)
from ..icons import IconLibrary
from ..diary import DiaryBuilder
from .. import citations, corrections, custombio, ribbons, wwii_awards
from .. import medals as medal_art

# KOREA_PREVIEW_RACK=all|navy|usmc|sov|dprk: every ladder of that country at its top
# rung (plus the Command Pilot badge for the USAF), for looking at a complete
# rack and coat without a career that earned one. Or a list of award ids,
# comma-separated, for any other set.
PREVIEW_RACK = {
    "all": (601041, 601025, 601052, 601051, 601017, 601016, 601063, 601062,
            601007, 601057, 601030, 601064, 601068, 601075, 601076, 601077,
            601053, 601038, 601039, 601040),
    "navy": (602038, 602026, 602031, 602043, 602017, 602016, 602053, 602052,
             602007, 602037, 602030, 601053, 601038, 601039, 602001),
    "usmc": (602038, 602026, 602031, 602043, 602017, 602016, 602053, 602052,
             602007, 602037, 602030, 601053, 601038, 601039, 602001),
    "sov": (501022, 501024, 501020, 501014, 501012, 501006, 501002, 501004,
            501050, 501051, 501052, 501053, 501054, 501049, 501038),
    "dprk": (503007, 503006, 503005, 503004, 503003, 503002, 503008, 503001),
}

USAF_RANK_OVERLAYS = {
    0: "usaf_2nd_Lt.png",
    1: "usaf_1st_Lt.png",
    2: "usaf_capt.png",
    3: "usaf_major.png",
    4: "usaf_Lt_Col.png",
    5: "usaf_Col.png",
    6: "usaf_brig_gen.png",
    7: "usaf_maj_gen.png",
}

# Service dress for the Air Force is the silver-tan coat; the blue one is
# what carries the full-size medals. The shoulder loops take their own
# insignia on it - the same eight files with _ST before the extension -
# because the tan loop wants a different rendering from the blue.
USAF_SERVICE_COAT = "tunic_usaf_silver_tan.jpg"
# The lapel cut-out is a piece of its own coat's photograph, drawn back over
# the ribbons so they tuck under it as on a real coat. It therefore belongs
# to the coat, not to the service: the blue one would paint a blue lapel on
# the silver-tan. Named only when the art is actually there, so the view
# falls back to no lapel rather than a broken picture.
LAPELS = {"tunic_usaf.jpg": "lapel_usaf.png",
          "tunic_usaf_silver_tan.jpg": "lapel_usaf_ST.png",
          "tunic_usmc.jpg": "lapel_usmc.png"}


def _lapel(coat_file: Optional[str]) -> Optional[str]:
    """The lapel art for a coat, if that coat wears one and we have it."""
    name = LAPELS.get(coat_file or "")
    if name is None:
        return None
    art = Path(__file__).resolve().parent.parent / "static" / "images" / name
    return name if art.is_file() else None
USAF_ST_RANK_OVERLAYS = {r: n.replace(".png", "_ST.png")
                         for r, n in USAF_RANK_OVERLAYS.items()}

NAVY_RANK_OVERLAYS = {
    0: "navy_ensign.png",
    1: "navy_lieutenant_jr_grade.png",
    2: "navy_lieutenant.png",
    3: "navy_lt_commander.png",
    4: "navy_commander.png",
    5: "navy_captain.png",
    6: "navy_rear_adm_LH.png",
    7: "navy_rear_adm_UH.png",
}

# Service dress for the Navy is the khaki coat, not the white one: the white
# is Service Dress White and carries the full-size medals. The boards are the
# same eight files on both coats, but khaki is worn with a shirt collar, so
# the rank is shown twice - gold on the boards and a device on each collar
# point. Those are the same eight names with _khaki before the extension.
NAVY_SERVICE_COAT = "tunic_navy_khaki_template.jpg"

USMC_RANK_OVERLAYS = {
    0: "usmc_2nd_Lt.png",
    1: "usmc_1st_Lt.png",
    2: "usmc_capt.png",
    3: "usmc_major.png",
    4: "usmc_Lt_Col.png",
    5: "usmc_Col.png",
    6: "usmc_brig_gen.png",
    7: "usmc_maj_gen.png",
}
# Full-size medals belong to Blue Dress "A", not the green service coat, so
# the Marine full-dress view swaps coat, shoulder ranks and neck art. The
# blue boards are the same eight files with _BD before the extension.
USMC_BD_RANK_OVERLAYS = {r: n.replace(".png", "_BD.png") for r, n in USMC_RANK_OVERLAYS.items()}
NAVY_COLLAR_OVERLAYS = {r: n.replace(".png", "_khaki.png")
                        for r, n in NAVY_RANK_OVERLAYS.items()}
USMC_DRESS_COAT = "tunic_dress_blue_usmc.jpg"
from ..loadouts import AmmoSchemes, parse_pilots_list
from ..worldobjects import WorldObjectIndex, normalise as normalise_object
from .attributes import PilotAttributes
from .database import CareerFile, KoreaCareerDatabase, find_careers
from .events import describe, is_award_event
from .killfix import KillCategories
from .killstats import ROLLUP_KEYS, KillStats
from .operations import Operations
from .missionresult import MissionResult, _number

logger = logging.getLogger(__name__)

# pilot.state, all four confirmed against a real career:
#
#   0  active
#   2  killed     — every state-2 pilot has a type-3 KIA event and health 0
#   3  missing    — shot down over enemy territory and not recovered
#   4  wounded    — in hospital, with a stateEndDate to return on; NOT a
#                   prisoner, which is what an earlier guess had it as
#
# 3 is the one that reads like death but is not. Manuel Rivera, 1951.06.22:
# a type-4 event rather than type-3, health **100** rather than 0, and a
# sortie.status of 3 rather than 2 — the only such sortie in 500. He is gone
# for good (stateEndDate is zeroed, as for the dead, and his slot is moved out
# of the squadron's range) but he was not killed. The game's own strings say
# as much: carCharacterDetails_MIA "Missing in action",
# carAutoMissionMIA_Text "$[name] shot down over enemy territory", and
# carCommanderMIA, which is captioned "Commander Captured" — so the game
# treats missing and taken prisoner as one outcome.
PILOT_STATE = {0: "active", 2: "kia", 3: "missing", 4: "wounded"}

# pilot.slot bands, matched against the game's "Combat units" screen on a
# fresh career (17 in service, 3 "in reserve - not ready", 5 unseen):
#
#   0..19       Combat units in service - the line-up (16..19 the "watchmen")
#   1000..1999  Combat units in reserve, NOT READY - a pilot moved out with
#               his aircraft while it is in repair; back when it is
#   2000..4999  the replacement pool: on strength, no aircraft, not shown on
#               that screen at all
#   5000+       the dead and the missing
NOT_READY_SLOTS = range(1000, 2000)
RESERVE_SLOTS = range(2000, 5000)


def _in_reserve(row) -> bool:
    return row["state"] == 0 and row["slot"] in RESERVE_SLOTS


def _not_ready(row) -> bool:
    return row["state"] == 0 and row["slot"] in NOT_READY_SLOTS


def _pilot_state(row) -> str:
    """The roster's state word: PILOT_STATE, with the two benches told apart."""
    if _not_ready(row):
        return "not_ready"
    if _in_reserve(row):
        return "reserve"
    # An unmapped value is shown as its number rather than swallowed, so the
    # next unknown state arrives in a screenshot with its value attached.
    return PILOT_STATE.get(row["state"], f"state {row['state']}")

# sortie.planeStatus, from the live career: 21 sorties at 0, 8 at 2, 2 at 3,
# and the two 3s line up with the player's two "aircraft lost" events.
PLANE_OUTCOME = {0: "returned", 2: "damaged", 3: "lost"}

# The headline category strip, mirroring the GB tracker's six icons.
COMBAT_CATEGORIES = OrderedDict([
    ("aircraft", ("Aircraft", ("air",))),
    ("vehicles", ("Vehicles", ("vehicles", "armour"))),
    ("rail", ("Railroad", ("rail",))),
    ("armaments", ("Armaments", ("artillery",))),
    ("buildings", ("Buildings", ("buildings",))),
    ("naval", ("Marine", ("naval",))),
])

# supply.type, in the words of the game's Resources screen.
SUPPLY_KINDS = {1: "aircraft", 2: "pilots", 3: "fuel", 4: "ordnance", 5: "equipment"}

# plane.tcode is the tail number as glyph indices into the type's own
# tail-code font: digits 0..9 are chr(33)..chr(42) in every font seen, '_'
# is the dash, and the leading letters are glyphs of that font, so "::_"
# on an F-51D and "BN_" on an F-86 are both the buzz-number prefix. The
# prefixes are the USAF's own: FF for the F-51, FU for the F-86, FT for
# the F-80, FS for the F-84. A type not listed keeps its raw letters.
BUZZ_PREFIX = {"f51d": "FF", "f86a5": "FU", "f86e": "FU", "f86f": "FU",
               "f80c10": "FT", "f84e": "FS", "f84g": "FS"}


def _tail_code(raw: Optional[str], plane_key: str) -> str:
    text = urllib.parse.unquote(raw or "")
    if not text:
        return ""
    letters, _, digits = text.partition("_")
    if not digits:
        return text
    # The F-84E carries a third segment (":D_\"\"*_7"); only the second is the
    # number, or its digits never decode and the raw glyphs show.
    digits = digits.split("_", 1)[0]
    # The player's own aircraft can carry a code typed in the hangar; its
    # letters arrive as plain letters and its digits one glyph block up
    # (chr(43)..chr(52)), so the base is whichever block the digits sit in.
    codes = [ord(ch) for ch in digits]
    base = 33 if all(33 <= o <= 42 for o in codes) else 43 if all(43 <= o <= 52 for o in codes) else None
    number = "".join(str(o - base) for o in codes) if base else digits
    # Letters count as typed only beside typed digits. The F-86's font glyphs
    # are "BN", which pass isalpha() and showed as BN-174 instead of FU-174.
    # Both fixes from Hector (hjbb1975), 2026-10-02.
    if base == 43 and letters.isalpha():
        prefix = letters
    else:
        prefix = BUZZ_PREFIX.get(plane_key.lower(), letters if letters.isalpha() else "")
    return f"{prefix}-{number}" if prefix else number

# Promotion pseudo-awards 601980..601984 confer rank 1..5.
PROMOTION_BASE = 601980

# Top of each country's valour ladder. Everything above it in the same block is
# a service medal, campaign star, wound badge or qualification badge, none of
# which is a "highest combat award" however senior the id looks — the USAF
# ladder runs Air Medal 601002 to Medal of Honor 601026, with the Purple Heart
# at 601028 and the UN Service Medal at 601039 sitting above but outranking
# nothing.
VALOUR_LADDER = {601: (601002, 601026), 602: (602002, 602027),
                 603: (602002, 602027), 501: (501002, 501026),
                 502: (502002, 502026), 503: (503002, 503026)}


# USAF order of precedence, lowest first, for the ids the mod added outside the
# stock 601002..601026 block: the Commendation below the Air Medal, the Bronze
# Star "V" ladder above the merit Bronze Star, the Silver Star's fourth and
# fifth rungs with the Silver Star. Ids not listed keep their numeric order
# inside the stock block, which happens to be precedence order there.
USAF_PRECEDENCE = [
    601054, 601055, 601056, 601057,                     # Commendation Ribbon
    601002, 601003, 601004, 601005, 601006, 601007,     # Air Medal
    601008, 601009, 601010,                             # Bronze Star, merit
    601058, 601059, 601061, 601060, 601062,             # Bronze Star with V
    601011, 601012, 601013, 601014, 601015, 601016,     # DFC
    601017,                                             # Legion of Merit
    601018, 601019, 601020, 601050, 601051,             # Silver Star
    601021, 601022, 601023, 601024, 601025,             # DSC
    601026, 601041,                                     # Medal of Honor
]
_USAF_RANK = {a: i for i, a in enumerate(USAF_PRECEDENCE)}


def _top_combat_award(country: int, award_ids) -> Optional[int]:
    if country == 601:
        return max((a for a in award_ids if a in _USAF_RANK),
                   key=_USAF_RANK.get, default=None)
    lo, hi = VALOUR_LADDER.get(country, (0, 10 ** 9))
    return max((a for a in award_ids if lo <= a <= hi), default=None)


def _pilot_description(raw: str) -> Dict[str, str]:
    """
    Unpack pilot.description, which is url-encoded key=value pairs:

        biographyId=601006&birthDate=1921%2e02%2e23
    """
    out = {}
    for pair in urllib.parse.unquote(raw or "").split("&"):
        key, _, value = pair.partition("=")
        if key:
            out[key] = value
    return out


# The game's small HTML biography as safe, plain-text paragraphs; shared
# with the Career Helper, which edits the same text.
_biography_paragraphs = custombio.html_paragraphs


def _humanise(key: str) -> str:
    """IndustrialBuilding -> Industrial Building; Raildoad -> Raildoad (sic)."""
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key)


def _hours(seconds: Optional[int]) -> float:
    return round((seconds or 0) / 3600.0, 1)


def _thin(fixes, point, step_m: float = 150.0, step_s: float = 15.0) -> List[list]:
    """The fixes worth drawing: the first, the last, and any at least
    step_m from the last kept or step_s after it - a straight leg at 30
    fixes a second would otherwise be thousands of points."""
    if not fixes:
        return []
    kept = [fixes[0]]
    for f in fixes[1:-1]:
        last = kept[-1]
        if math.hypot(f[1] - last[1], f[2] - last[2]) >= step_m or f[0] - last[0] >= step_s:
            kept.append(f)
    if len(fixes) > 1:
        kept.append(fixes[-1])
    return [point(f) for f in kept]


def _pos_at(fixes, t: float):
    """Where the aircraft was at t, interpolated between the fixes round it."""
    import bisect
    times = [f[0] for f in fixes]
    i = bisect.bisect_left(times, t)
    if i <= 0:
        return fixes[0][1], fixes[0][2], fixes[0][3]
    if i >= len(fixes):
        return fixes[-1][1], fixes[-1][2], fixes[-1][3]
    a, b = fixes[i - 1], fixes[i]
    k = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
    return a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k


# The mission symbol the AF Form 5 carried in its remarks: the USAF's own
# operational shorthand of the period for the game's mission types -
# intercepts, combat air patrol, close air support, fighter sweep, armed
# reconnaissance, escort, ground attack, interdiction, airfield strike.
MISSION_SYMBOL = {
    1101: "INT", 1102: "INT", 1103: "INT", 1104: "INT", 1108: "INT", 1105: "CAP",
    1121: "CAP", 1124: "CAP", 1125: "CAP", 1122: "CAS", 1123: "FS", 1126: "FS", 1128: "AR", 1207: "AR",
    1151: "ESC", 1152: "ESC", 1153: "ESC", 1154: "ESC", 1155: "ESC", 1156: "ESC",
    1201: "GA", 1202: "GA", 1203: "GA", 1204: "CAS", 1208: "GA", 1209: "GA",
    1205: "INTD", 1215: "INTD", 1206: "AF",
}


# The Navy's flight classification (Naval Aircraft Flight Classification
# System, condensed): condition 1 day visual / 3 night visual, then the
# general purpose letter and the specific purpose number. Combat letters:
# T attack on non-ASC targets, U counter-air offensive, V reconnaissance,
# W air defence of own base, X air defence of other forces.
NAVY_FLIGHT_CODE = {
    1101: "X7", 1102: "X7", 1103: "X7", 1104: "X7", 1108: "X7",     # intercept (scramble)
    1105: "W2",                                                      # CAP over own base
    1121: "X4", 1124: "X4", 1125: "X4",                              # CAP over friendly forces
    1123: "U1", 1126: "U1", 1206: "U1",                              # sweep, intruder, airfield strike
    1122: "T1", 1201: "T1", 1202: "T1", 1203: "T1", 1204: "T1",      # pre-assigned target
    1205: "T1", 1208: "T1", 1209: "T1",
    1128: "T2", 1207: "T2", 1215: "T2",                              # armed reconnaissance
    1151: "U8", 1156: "U8", 1153: "U9",                              # escort of bombers, transports
    1152: "T9", 1154: "V9", 1155: "V9",                              # escort of attack, recon
    1139: "X4",                                                      # cover of a strategic object
    1217: "S1",                                                      # harbour strike: ASC targets
    1301: "T2", 1302: "T2", 1304: "T2",                              # close support: targets given airborne
    1501: "T1", 1502: "T1", 1503: "T1", 1504: "U1", 1505: "T1",      # bombing, pre-assigned
    1506: "T1", 1507: "T1", 1508: "T1", 1513: "T1",
    1901: "J1", 1902: "J1",                                          # ferry
}


def navy_flight_code(mission_type: int, night_share: float) -> str:
    """'1T1': day or night, then the purpose of the flight."""
    purpose = NAVY_FLIGHT_CODE.get(int(mission_type or 0), "Q5")
    return ("3" if night_share > 0.5 else "1") + purpose


def bureau_number(plane_id: int, plane_key: str, career_key: str) -> str:
    """A Navy Bureau Number for an aircraft the game knows only by its
    tail code: six digits, fixed per airframe, in the block the type was
    built in (F9F Panthers 122xxx-127xxx, F4U-4 and AD 81xxx-97xxx,
    129xxx for the later Corsairs and Skyraiders)."""
    import hashlib
    key = (plane_key or "").lower()
    lo, hi = (122560, 127430) if key.startswith(("f9f", "f2h")) else              (129318, 133890) if key.startswith(("f4u5", "f4u-5", "au1", "ad4")) else (81000, 97500)
    n = int(hashlib.sha1(f"{career_key}|{plane_id}".encode()).hexdigest()[:8], 16)
    return str(lo + n % (hi - lo))


def _seconds(clock: str) -> float:
    """'HH:MM[:SS]' as seconds of the day."""
    try:
        parts = [int(n) for n in clock.split(":")]
    except ValueError:
        return 0.0
    while len(parts) < 3:
        parts.append(0)
    return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]


def _clock(start: str, offset_s: Optional[float]) -> str:
    """Mission start time plus an offset in seconds, as HH:MM:SS."""
    if offset_s is None:
        return ""
    try:
        hh, mm = (int(n) for n in start.split(":")[:2])
    except (ValueError, IndexError):
        return ""
    total = hh * 3600 + mm * 60 + int(offset_s)
    return f"{total // 3600 % 24:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def _hm(seconds: Optional[int]) -> str:
    total = int(seconds or 0)
    return f"{total // 3600}h {total % 3600 // 60:02d}m"


def _landing_clock(start: str, flight, secs: Optional[float]) -> str:
    """
    When the wheels touched: take-off plus the sortie's credited duration.

    The flight log's own landing event is the obvious thing to print, and on
    almost every sortie it is the same moment - the game's `flightTime` equals
    the log's take-off-to-landing span to the second. On a few it does not.
    The career file and the flight log then disagree about the same sortie
    before anything here touches it, and a row that takes its clock from one
    and its hours from the other does not add up: 07:26 to 08:09 against
    0h 57m, on the 12th FBS airfield attack of 1951.05.01.

    The hours are the figure that has to stand - they are what the career file
    carries, what the pilot screen shows and what the hours-based awards read
    - so the landing is the one that moves. On that sortie it also lands on
    the game's own corrected mission end, which the log's landing does not.

    A man who did not come back has no landing in the log, and is not given
    one here either.
    """
    if flight is None or flight.takeoff_s is None or flight.landing_s is None:
        return _clock(start, flight.landing_s) if flight is not None else ""
    total = float(secs or 0)
    if total <= 0:
        return _clock(start, flight.landing_s)
    return _clock(start, flight.takeoff_s + total)


def _days_between(start: str, end: str) -> int:
    """Whole days between two 'YYYY.MM.DD[ HH:MM:SS]' stamps, by the date."""
    from datetime import date
    try:
        a = date(*(int(v) for v in start[:10].split(".")))
        b = date(*(int(v) for v in end[:10].split(".")))
    except (ValueError, TypeError):
        return 0
    return (b - a).days


class CareerAggregator:
    """Builds the API payloads for one game installation."""

    def __init__(self, game_dir: Path, lang: str = "eng", corrections_on=None):
        self.game_dir = Path(game_dir)
        self.lang = lang
        # A callable answering "are corrected flight times switched on?" -
        # read per request so the header switch takes effect at once.
        self.corrections_on = corrections_on or (lambda: False)
        self.resolver = AssetResolver(self.game_dir)
        self.locale = LocaleStrings(self.game_dir, lang, resolver=self.resolver)
        self.objects = WorldObjectIndex(self.resolver, lang)
        self.ammo = AmmoSchemes(self.resolver, lang)
        self.tiles = MapTiles(self.resolver)
        self.overlay = Overlay(self.resolver, lang)
        self.icons = IconLibrary(self.resolver)
        # The game's object -> kill category table, for removing the napalm
        # re-kills from every kill figure (killfix.py). None leaves them in.
        self.kill_categories = KillCategories.from_resolver(self.resolver)
        self.ribbons = ribbons.RibbonRenderer(self.resolver.cache_dir)
        self.medals = medal_art.MedalRenderer(self.resolver.cache_dir, self.ribbons, self.icons)
        self.flightlogs = FlightLogIndex(self.game_dir)
        self.descriptions = MissionDescriptions(self.resolver, lang, DEFAULT_TVD)
        # Through the resolver: a stock installation keeps awards.cfg inside
        # Missions.gtp and has no loose copy to read.
        self.awards_cfg = AwardsConfig(
            self.game_dir / "data" / "scg" / str(DEFAULT_TVD) / "awards.cfg",
            resolver=self.resolver)
        self.frontlines = FrontLines(self.resolver)

    # -- helpers -----------------------------------------------------------

    def _career_files(self) -> Dict[str, CareerFile]:
        return {c.path.stem: c for c in find_careers(self.game_dir)}

    def _attacker_name(self, attacker: str) -> str:
        """
        The game's own name for whatever hit the aircraft, or "" for the 91%
        of hits that record nobody. Own-ordnance damage is not named here — the
        front end labels it in the reader's language from `self_inflicted`,
        since "hit by F-51D" for a pilot's own bomb blast was actively wrong.
        """
        if not attacker or attacker == SELF_DAMAGE:
            return ""
        return self.objects.describe(attacker)["name"]

    def award_name(self, award_id: int) -> str:
        prior = wwii_awards.name(award_id, self.lang)
        if prior:
            return prior
        defn = self.awards_cfg.get(award_id)
        return self.locale.award_name(award_id, defn.name if defn else "")

    def _pilot_row(self, row, awards_by_pilot: Dict[int, List],
                   current_id: Optional[int] = None) -> Dict[str, Any]:
        kills = KillStats(row["killStats"])
        attrs = PilotAttributes(row["persLevel"], row["leadLevel"])
        held = awards_by_pilot.get(row["id"], [])
        described = _pilot_description(row["description"])
        medals = [a for a in held if a["category"] != 1 and not a["isPending"]]
        top = _top_combat_award(row["country"], (a["type"] for a in medals))
        # pilot.isPlayer stays set on a dead predecessor after the career
        # carries on with a successor; only career.playerId says who the
        # human is now, and the roster highlights that one man.
        is_player = (row["id"] == current_id if current_id is not None
                     else bool(row["isPlayer"]))
        return {
            "id": row["id"],
            "name": f"{row['name']} {row['lastName']}".strip(),
            "is_player": is_player,
            "country": row["country"],
            "rank_id": row["rankId"],
            # pilot.rankId is authoritative. The game's own Award and Promotion
            # panel shifts ranks up by the number of promotions a pilot has had.
            "rank": self.locale.rank_name(row["country"], row["rankId"]),
            "state": _pilot_state(row),
            # The squadron's line-up is slots 0..19; the reserve pool sits at
            # 2000..2019 and the dead and missing are moved to 5000+. A pilot
            # in the pool is available but not flying, and a roster that calls
            # him "active" beside the men in the line-up misleads — a forum
            # reader counted 47 "active" pilots in a 19-slot squadron.
            "reserve": _in_reserve(row),
            "state_until": (row["stateEndDate"][:10]
                            if row["state"] == 4
                            and not row["stateEndDate"].startswith("0000") else ""),
            # For the dead and the missing alike, stateDate is the day they
            # were lost, and stateEndDate is zeroed — neither is coming back.
            "state_since": (row["stateDate"][:10]
                            if row["state"] in (2, 3)
                            and not row["stateDate"].startswith("0000") else ""),
            "health": row["health"],
            "sorties": row["sorties"],
            "good_sorties": row["goodSorties"],
            "flight_hours": _hours(row["flightTime"]),
            "flight_time": _hm(row["flightTime"]),
            "airborne": kills.airborne,
            "ground_targets": kills.ground_targets,
            "attributes": attrs.display_rows(),
            # False for the commander: he has boosters, not skill levels.
            "has_levels": attrs.has_levels,
            "awards_held": len(medals),
            "awards_pending": sum(1 for a in held if a["isPending"]),
            "top_award": self.award_name(top) if top else "",
            "top_award_id": top,
            # Sort key for the roster: precedence, not the name's first letter
            # (which put "Bronze Oak Leaf Cluster in Lieu of 2nd Silver Star"
            # under the DFC). USAF ids rank by the explicit list; the other
            # nations' stock blocks happen to be in precedence order by id.
            "top_award_rank": (_USAF_RANK.get(top, -1) if row["country"] == 601
                               else (top or 0)) if top else -1,
            # rank icon keys are rank<country><index>
            "rank_key": f"{row['country']}{row['rankId']}",
            "promotions": sum(1 for a in held if a["category"] == 1),
            "slot": row["slot"],
            "birth_date": described.get("birthDate", ""),
            "biography_id": described.get("biographyId", ""),
            # The game ships a portrait for every pilot; a user upload overrides it.
            "avatar": row["avatarPath"] or "",
        }

    # A description file may redirect instead of holding text:
    #     #601002 // Использовать описание от другой награды
    # ("use the description from another award"). 80 of the 99 USAF/Navy award
    # descriptions are redirects — every cluster points at the base decoration,
    # which is why they looked like untranslated Russian stubs.
    _REDIRECT = re.compile(r'^\s*#(\d+)')

    def award_description(self, award_id: int, depth: int = 0) -> Dict[str, Any]:
        """Award description text, following redirects to the base decoration."""
        ident = str(award_id)
        vpath = f"nsdata/assets/awards/{ident[0]}xx/{ident}.locale={self.lang}.txt"
        text = (self.resolver.read_text(vpath) or "").strip()
        match = self._REDIRECT.match(text)
        if match and depth < 5:
            target = int(match.group(1))
            if target != award_id:
                inherited = self.award_description(target, depth + 1)
                # Say whose text this is; the reader should not think the
                # citation was written for the cluster.
                inherited["inherited_from"] = self.award_name(target)
                return inherited
        return {"description": "" if match else text, "inherited_from": ""}

    def _rank_texts(self) -> Dict[str, str]:
        """The tracker's own rank descriptions for this language; English
        when the language has none."""
        cached = getattr(self, "_rank_text_cache", None)
        if cached is not None:
            return cached
        folder = Path(__file__).resolve().parent.parent / "locales" / "ranks"
        texts: Dict[str, str] = {}
        for lang in (self.lang, "eng"):
            path = folder / f"{lang}.json"
            if path.is_file():
                try:
                    texts = json.loads(path.read_text(encoding="utf-8"))
                    break
                except (OSError, ValueError) as exc:
                    logger.warning("Rank texts %s unreadable: %s", path.name, exc)
        self._rank_text_cache = texts
        return texts

    def emblem_detail(self, kind: str, ident: str) -> Optional[Dict[str, Any]]:
        """
        Name, description and full-size art for one medal, rank or emblem.

        Descriptions live beside the artwork in the archives:

            awards      nsdata/assets/awards/<6xx>/<id>.locale=<lang>.txt
            squadrons   nsdata/assets/squadrons/<601>/<id>.locale=<lang>.txt

        Ranks have artwork but no description anywhere in the game, so the
        tracker carries its own, per language, in locales/ranks/<lang>.json
        keyed like the game's rank keys (6013 = USAF Major).
        """
        # An id with no artwork is not a thing the user can click, so 404
        # rather than returning an empty shell.
        if not ident.isdigit() or not self.icons.has(kind, ident):
            return None
        name, vpath, inherited = "", "", ""
        if kind == "award":
            name = self.award_name(int(ident))
            found = self.award_description(int(ident))
            text, inherited = found["description"], found["inherited_from"]
            return {"kind": kind, "id": ident, "name": name,
                    "description": text, "inherited_from": inherited,
                    "image": f"/api/icon/{kind}/{ident}"}
        elif kind == "squadron":
            # The readable squadron name lives in the career file name, which
            # this call has no access to; the caller supplies it and this is
            # only the fallback.
            name = f"Squadron {ident}"
            vpath = (f"nsdata/assets/squadrons/{ident[:3]}/"
                     f"{ident}.locale={self.lang}.txt")
        elif kind == "rank":
            # rank keys are <country><index>, e.g. 6013
            try:
                name = self.locale.rank_name(int(ident[:3]), int(ident[3:]))
            except ValueError:
                return None
        else:
            return None

        text = self.resolver.read_text(vpath) if vpath else None
        if kind == "rank":
            text = self._rank_texts().get(ident, "")
        return {
            "kind": kind,
            "id": ident,
            "name": name,
            "description": (text or "").strip(),
            "inherited_from": inherited,
            "image": f"/api/icon/{kind}/{ident}",
        }

    # -- landing page ------------------------------------------------------

    def _open(self, meta) -> KoreaCareerDatabase:
        """A career file, with the flight-time corrections attached when the
        user has switched them on and the helper has computed any."""
        db = KoreaCareerDatabase(meta.path)
        if self.kill_categories is not None:
            db.set_kill_categories(self.kill_categories)
        data = corrections.load(Path(meta.path).stem)
        # Once the credited hours are in the file, the clock must follow or the
        # record shows a hybrid - so an applied career is always re-timed,
        # whatever the switch says; the switch only governs the others.
        if data and (self.corrections_on() or corrections.is_applied(data)):
            db.set_corrections(data)
        return db

    def _shifted_log(self, db, mission_id, flight):
        """The flight log's offsets re-timed for a corrected mission, so the
        take-off, landing and damage timeline agree with the events."""
        entry = db.correction_for(mission_id) if flight is not None else None
        if not entry:
            return flight
        warps = corrections.warps_of(entry)
        fix = lambda t: None if t is None else corrections.offset(warps, t)   # noqa: E731
        return flight._replace(
            takeoff_s=fix(flight.takeoff_s),
            landing_s=fix(flight.landing_s),
            damage=[b._replace(at_s=fix(b.at_s)) for b in flight.damage],
            damage_by_pilot={k: [b._replace(at_s=fix(b.at_s)) for b in v]
                             for k, v in flight.damage_by_pilot.items()},
            weapon_hits=[h._replace(at_s=fix(h.at_s))
                         for h in flight.weapon_hits])

    @staticmethod
    def _weapon_kind(weapon: str) -> str:
        upper = (weapon or "").upper()
        if upper.startswith(("BULLET_", "SHELL_")):
            return "guns"
        if upper.endswith("_HIT") and upper.startswith(("RKT_", "ROCKET_")):
            return "rockets"
        return ""

    def _gunnery(self, flight, start: str = "") -> Dict[str, Any]:
        """A factual weapons account from one human player's binary log.

        AType 10 and 4 hold the four ammunition counters before and after the
        sortie.  AType 1 holds projectile contacts.  Generic explosion and
        napalm contacts were discarded by flightlog.py; treating those as
        rounds would turn one bomb into thousands of apparent hits.
        """
        empty = {"available": False, "complete": False, "gun_loaded": None,
                 "gun_returned": None, "gun_fired": None, "gun_hits": 0,
                 "gun_rate": None, "bombs_loaded": None,
                 "bombs_returned": None, "bombs_expended": None,
                 "rockets_loaded": None, "rockets_returned": None,
                 "rockets_expended": None, "rocket_impacts": 0,
                 "passes": [], "targets": []}
        if flight is None or flight.ammo_start is None:
            return empty

        start_ammo = flight.ammo_start
        end_ammo = flight.ammo_end
        complete = end_ammo is not None
        used = ([max(0, int(a) - int(b)) for a, b in zip(start_ammo, end_ammo)]
                if complete else [None, None, None, None])
        gun_loaded = int(start_ammo[0]) + int(start_ammo[1])
        gun_returned = (int(end_ammo[0]) + int(end_ammo[1])
                        if complete else None)
        gun_fired = (int(used[0]) + int(used[1]) if complete else None)

        gun_hits = [h for h in flight.weapon_hits
                    if self._weapon_kind(h.weapon) == "guns"]
        rocket_hits = [h for h in flight.weapon_hits
                       if self._weapon_kind(h.weapon) == "rockets"]

        # Group recorded gun impacts into attacks.  This is deliberately an
        # impact timeline, not a burst counter: misses leave no timed record,
        # so the report never pretends to know when every trigger pull began.
        passes: List[Dict[str, Any]] = []
        for hit in sorted(gun_hits, key=lambda h: h.at_s):
            if not passes or hit.at_s - passes[-1]["at_s"] > 15.0:
                passes.append({"at_s": hit.at_s, "hits": 0, "targets": []})
            row = passes[-1]
            row["at_s"] = hit.at_s
            row["hits"] += 1
            if hit.target:
                info = self.objects.describe(hit.target)
                if info["named"] and info["name"] not in row["targets"]:
                    row["targets"].append(info["name"])
        for row in passes:
            row["time"] = _clock(start, row.pop("at_s")) if start else ""

        target_counts: Counter = Counter()
        for hit in gun_hits + rocket_hits:
            if not hit.target:
                continue
            info = self.objects.describe(hit.target)
            if info["named"]:
                target_counts[info["name"]] += 1

        return {
            "available": True,
            "complete": complete,
            "gun_loaded": gun_loaded,
            "gun_returned": gun_returned,
            "gun_fired": gun_fired,
            "gun_hits": len(gun_hits),
            "gun_rate": (round(100.0 * len(gun_hits) / gun_fired, 1)
                         if gun_fired else None),
            "bombs_loaded": int(start_ammo[2]),
            "bombs_returned": int(end_ammo[2]) if complete else None,
            "bombs_expended": int(used[2]) if complete else None,
            "rockets_loaded": int(start_ammo[3]),
            "rockets_returned": int(end_ammo[3]) if complete else None,
            "rockets_expended": int(used[3]) if complete else None,
            "rocket_impacts": len(rocket_hits),
            "passes": passes,
            "targets": [{"name": name, "hits": count}
                        for name, count in target_counts.most_common(8)],
        }

    def list_careers(self) -> List[Dict[str, Any]]:
        out = []
        for career_id, meta in self._career_files().items():
            try:
                with self._open(meta) as db:
                    career, squad, player = db.career(), db.squadron(), db.player()
                    if career is None or player is None:
                        continue
                    kills = KillStats(player["killStats"])
                    held = db.awards(player["id"])
                    out.append({
                        "id": career_id,
                        "pilot": f"{player['name']} {player['lastName']}".strip(),
                        "squadron": meta.squadron_name,
                        "rank": self.locale.rank_name(player["country"],
                                                      player["rankId"]),
                        "flag": COUNTRY_FLAGS.get(player["country"], ""),
                        "country_name": COUNTRY_NAMES.get(player["country"], ""),
                        "start_date": career["startDate"],
                        "current_date": career["currentDate"],
                        "sorties": player["sorties"],
                        "flight_hours": _hours(player["flightTime"]),
                        "airborne": kills.airborne,
                        "ground_targets": kills.ground_targets,
                        "awards": sum(1 for a in held
                                      if a["category"] != 1 and not a["isPending"]),
                        "roster_size": len(db.pilots()),
                        "award_points": squad["awardPoints"] if squad else 0,
                    })
            except Exception:
                logger.exception("Failed to summarise %s", meta.path)
        out.sort(key=lambda c: c["current_date"], reverse=True)
        return out

    # -- detail blocks -----------------------------------------------------

    def _combat_results(self, kills: KillStats) -> Dict[str, Any]:
        cats = kills.category_totals()
        cats["air"] = kills.airborne
        headline = [{"key": key, "label": label,
                     "value": sum(cats.get(s, 0) for s in sources)}
                    for key, (label, sources) in COMBAT_CATEGORIES.items()]
        # Leaf categories only. The rollups the game writes beside them
        # (Aircraft, Materiel, Building, Railroad) are subtotals, which is
        # also why the game names them in no language: they were never meant
        # to be rows. _humanise is the last resort for a category the game
        # has no name for.
        breakdown = [{"label": self.locale.stat_name(k) or _humanise(k), "value": v}
                     for k, v in sorted(kills.counts.items(), key=lambda x: -x[1])
                     if k not in ROLLUP_KEYS and v]
        return {
            "headline": headline,
            "breakdown": breakdown,
            "airborne": kills.airborne,
            "parked": kills.static_air,
            "ground_targets": kills.ground_targets,
        }

    def _air_kills_by_type(self, kill_events) -> List[Dict[str, Any]]:
        """
        Victories by aircraft type, from the per-kill event names.

        A name counts only if it matches one of the game's own plane folders;
        parked aircraft carry a ``Static_plane_`` prefix and are listed apart.
        Guessing from prefixes instead would miss jets and swallow ground
        clutter such as "Windsock".
        """
        airborne, parked = Counter(), Counter()
        for row in kill_events:
            name = (row["tpar1"] or "").strip()
            low = name.lower()
            if low.startswith("static_plane_"):
                stem = low[len("static_plane_"):]
                if stem in PLANE_TYPES:
                    parked[name[len("Static_plane_"):]] += 1
            elif low in PLANE_TYPES:
                airborne[name] += 1
        return {
            "airborne": [{"name": self.locale.plane_name(n) or n, "value": v}
                         for n, v in airborne.most_common()],
            "parked": [{"name": self.locale.plane_name(n) or n, "value": v}
                       for n, v in parked.most_common()],
        }

    def _missions_flown(self, sorties, missions=None) -> List[Dict[str, Any]]:
        total_time = sum(s["flightTime"] or 0 for s in sorties)
        outcomes = Counter(PLANE_OUTCOME.get(s["planeStatus"], "unknown")
                           for s in sorties)
        wounded = sum(1 for s in sorties if s["status"] == 4)
        count = len(sorties) or 1

        # flightTime is what was actually flown, and warping to the target
        # makes that a fraction of the route: the game teleports rather than
        # advancing the clock, so a 55-minute mission is logged as 15. The
        # mission's own start->end stamps count the same way (9h 21m against
        # 9h 10m on this career - ramp time, nothing more). What a logbook
        # would have carried is mission.estDuration, the planned route flown
        # in full: 32.7 h against 9.2 h flown, 32 missions.
        planned = 0
        for s in sorties:
            m = (missions or {}).get(s["missionId"])
            if m and m["estDuration"]:
                planned += max(0, int(m["estDuration"]))

        rows = [
            # Every row carries a key as well as the English. The front end
            # prefers the key; the prose stays as a fallback for anything the
            # locale files have not caught up with.
            {"key": "missions.completed",
             "label": "Missions completed", "value": len(sorties)},
            {"key": "missions.flight_time",
             "label": "Flight time", "value": _hm(total_time)},
            {"key": "missions.average_flight_time",
             "label": "Average flight time", "value": _hm(total_time // count)},
        ]
        if planned:
            rows.append({"key": "missions.planned_time",
                         "label": "Planned flight time (full route)",
                         "value": _hm(planned)})
        rows += [
            {"key": "missions.returned",
             "label": "Aircraft returned", "value": outcomes.get("returned", 0)},
            {"key": "missions.damaged",
             "label": "Aircraft damaged", "value": outcomes.get("damaged", 0)},
            {"key": "missions.lost",
             "label": "Aircraft lost", "value": outcomes.get("lost", 0)},
            {"key": "missions.wounded",
             "label": "Wounded in action", "value": wounded},
            {"key": "missions.assists",
             "label": "Shared victories", "value": sum(s["assistCount"] or 0 for s in sorties)},
        ]
        # Own-side aircraft shot down. A zero on every record would be
        # noise; a one is the kind of thing a file never forgets.
        friendly = sum(s["fkill"] or 0 for s in sorties)
        if friendly:
            rows.append({"key": "missions.friendly_kills",
                         "label": "Friendly aircraft shot down", "value": friendly})
        return rows

    def _superseded(self, award_id: int) -> List[int]:
        """
        The awards this one retires when granted - the ``(ExAw=...)`` ids in
        its AwardRemove expression, in file order. That is the game's own
        definition of "same ladder": a cluster removes the base decoration
        and every earlier cluster. RequiredAward is not used because it also
        names prerequisites from other ladders (the DFC requires an Air
        Medal), which are not rungs of this one.
        """
        defn = self.awards_cfg.get(award_id)
        if not defn or not defn.removes:
            return []
        return [int(x) for x in re.findall(r"ExAw\s*=\s*(\d+)", defn.removes)]

    def _ladder_root(self, award_id: int) -> int:
        """The base decoration of an award's ladder: follow AwardRemove down
        until an award that retires nothing (bounded against a cycle)."""
        seen = [award_id]
        while len(seen) < 12:
            below = self._superseded(seen[-1])
            if not below or below[0] in seen:
                break
            seen.append(min(below))
        return seen[-1]

    def _progress(self, db, subject, career, squad, held: set) -> Dict[str, Any]:
        """
        How close this pilot is to his next decoration, and the squadron to
        its next citation.

        Only the next rung of each ladder is offered. Every unearned award
        would be forty-odd rows and would bury the two the man is actually
        going to reach; the rung above the next one is unreachable anyway,
        since it needs the one below it first.

        A rung carries three different sorts of thing and the page must not
        blur them. A cumulative counter can be drawn as a bar. A per-sortie
        requirement cannot - "six airborne kills in one flight" is a standing
        condition, not something a man is two thirds of the way through. And
        a dice roll is neither: it is a chance per debrief, quoted so that a
        Commendation Ribbon at one in five is not read as the same offer as a
        Soldier's Medal at three in a thousand.
        """
        from .. import progress as prog

        # The value set is a parameter because a citation's rungs are
        # counted on the squadron's numbers while everything else is
        # counted on the pilot's. Reading the closure's `values` gave the
        # Distinguished Unit Citation a headline of 1,551 targets and an
        # alternative route of 575 - the same sum, read off two different
        # sets.
        def rows(rungs, limit, vals):
            out = []
            for rung in rungs[:limit]:
                # Higher rungs are named for their device alone - "Bronze
                # Oak Leaf Cluster in Lieu of 5th Award" - which says nothing
                # about the medal it hangs on. The ladder's root carries the
                # medal, so the row leads with that and keeps the device as
                # the qualifier, the way the rack already reads.
                root = self._ladder_root(rung.award_id)
                device = self.award_name(rung.award_id)
                headline = self.award_name(root)
                # The device string usually ends by repeating the medal -
                # "Bronze Oak Leaf Cluster in Lieu of 2nd Bronze Star Medal"
                # - which wraps the row onto a second line for no gain, since
                # the headline has just said it. Drop the repetition.
                if headline and headline in device:
                    device = device.replace(headline, "").strip(" ,-—")
                out.append({
                    "type": rung.award_id,
                    "name": headline,
                    "device": device if root != rung.award_id else "",
                    "eligible": rung.eligible,
                    "chance": rung.chance,
                    "bars": [{"what": g.variable, "have": round(g.current, 1),
                              "need": g.needed, "unit": prog.unit_for(g.variable),
                              "fraction": round(g.fraction, 3)} for g in rung.bars],
                    "conditions": [{"what": g.variable, "need": g.needed,
                                    "unit": prog.unit_for(g.variable)}
                                   for g in rung.conditions],
                    # A state the man has to be in rather than a number he
                    # has to reach. Named plainly - "Wounded in Action" - and
                    # not dressed up as something to work toward, because
                    # nobody is a percentage of the way to being hit.
                    "prereqs": [self._prereq(g, country)
                                for g in rung.prerequisites],
                    # Where nothing is measurable, a single "nearest" route
                    # is a half-truth: the Medal of Honor is six kills in a
                    # sortie *or* five while wounded, and the Distinguished
                    # Service Cross is exactly four at three in five *or*
                    # exactly five at four in five. Both are worth knowing,
                    # so an award with no bar to draw lists its routes.
                    "routes": self._routes(rung, vals, country),
                })
            return out

        country = int(subject["country"] or 0)
        values = prog.pilot_variables(subject, career, squad)
        # "The next rung of each ladder" is self-limiting - a dozen or so for
        # the USAF - so the cap is only a guard against a modded awards.cfg
        # with far more ladders, not a shortlist. Cutting it tighter dropped
        # the Medal of Honor and the Purple Heart, which are precisely the
        # two a reader looks for.
        awards = rows(prog.next_rungs(self.awards_cfg, held, values, country), 14, values)

        # The unit's citations are counted on the unit's totals, and the
        # squadron holds them, so they are asked for separately.
        unit_held = {r["type"] for r in db.query(
            "SELECT type FROM award WHERE pilotId<0 OR category=2")}
        unit_values = prog.squadron_variables(squad, career, country)
        citations = rows(prog.next_rungs(
            self.awards_cfg, unit_held, unit_values, country,
            squadron=True), 4, unit_values)

        promotion = self._next_promotion(values, country)
        return {"awards": awards, "citations": citations, "promotion": promotion}

    def _next_promotion(self, values: Dict[str, Any], country: int) -> Optional[Dict[str, Any]]:
        """
        The promotion out of the pilot's present rank: the rank it leads to,
        whether he has already met it, and a bar per counter he is still
        short on. None when awards.cfg has no promotion out of his rank.

        Promotions are pseudo-awards with no art and no name of their own,
        so they belong beside the rank rather than in the medal list.
        """
        from .. import progress as prog

        for defn in sorted(self.awards_cfg.definitions.values(),
                           key=lambda d: d.order):
            if not defn.is_promotion or not defn.in_proc:
                continue
            node = prog.parse(defn.in_proc)
            ok, gaps = prog.evaluate(node, values)
            # the rung out of *this* rank, whether or not he is there yet
            rank_gap = [g for g in gaps if g.variable.lower() == "rankid"]
            if rank_gap or (not ok and not gaps):
                continue
            rank = self.locale.rank_name(country, int(values.get("rankid", 0)) + 1)
            if ok:
                return {"rank": rank, "ready": True, "bars": []}
            return {
                "rank": rank,
                "ready": False,
                "bars": [{"what": g.variable, "have": round(g.current, 1),
                          "need": g.needed, "unit": prog.unit_for(g.variable),
                          "fraction": round(g.fraction, 3)}
                         for g in gaps if g.kind == "cumulative"],
            }
        return None

    def career_briefing(self, career_id: str) -> Optional[Dict[str, Any]]:
        """
        The squadron at a glance, for the career's card on the start page:
        promotions due, awards waiting to be presented, the store that runs
        out first, the next aircraft back from repair and the next delivery,
        and the player's own state if he is off flying. Asked for per card,
        after the list has drawn, so the start page never waits on it.
        """
        from .. import progress as prog

        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career, squad, player = db.career(), db.squadron(), db.player()
            if career is None or player is None:
                return None
            pending = db.query("SELECT pilotId, category FROM award WHERE isDeleted=0 AND isPending=1")
            promoted = {r["pilotId"] for r in pending if r["category"] == 1}
            due = set(promoted)
            for pilot in db.pilots():
                if pilot["state"] in (2, 3) or pilot["id"] in due:
                    continue
                values = prog.pilot_variables(pilot, career, squad)
                nxt = self._next_promotion(values, int(pilot["country"] or 0))
                if nxt and nxt["ready"]:
                    due.add(pilot["id"])
            awards_waiting = sum(1 for r in pending if r["category"] != 1)
            # The player's own next rung, by the counter he is furthest from.
            mine = None
            if player["state"] not in (2, 3) and player["id"] not in due:
                nxt = self._next_promotion(prog.pilot_variables(player, career, squad),
                                           int(player["country"] or 0))
                bars = (nxt or {}).get("bars") or []
                if bars:
                    worst = min(bars, key=lambda b: b["fraction"])
                    mine = {"rank": nxt["rank"], "have": worst["have"], "need": worst["need"],
                            "unit": worst["unit"]}

            aircraft = self._aircraft(db, career, squad, Path(meta.path))
            lasts = ((aircraft.get("statistics") or {}).get("lasts") or {})
            shortest = min(((k, v) for k, v in lasts.items() if v is not None),
                           key=lambda kv: kv[1], default=None)
            repairs = [r for r in aircraft["repairs"] if r["days"] is not None]
            soonest = min(repairs, key=lambda r: r["days"], default=None)
            arrivals = [a for a in aircraft["arrivals"] if a.get("kind") == "aircraft"]

            state = ""
            until = ""
            if player["state"] == 4:
                state = "wounded"
                until = "" if player["stateEndDate"].startswith("0000") else player["stateEndDate"][:10]
            elif player["state"] in (2, 3):
                state = {2: "kia", 3: "missing"}[player["state"]]
            return {
                "career_id": career_id,
                "promotions_due": len(due),
                "player_promotion_due": player["id"] in due,
                "awards_pending": awards_waiting,
                "next_rank": mine,
                "aircraft_ready": aircraft["serviceable"], "aircraft_total": aircraft["on_strength"],
                "stores": ({"kind": shortest[0], "days": shortest[1]} if shortest else None),
                "in_repair": aircraft["in_repair"],
                "repair_next": ({"code": soonest["code"], "days": soonest["days"]} if soonest else None),
                "arrival": arrivals[0] if arrivals else None,
                "player_state": state, "player_until": until,
            }

    def squadron_promotions(self, career_id: str) -> Optional[Dict[str, Any]]:
        """
        The next promotion of every pilot still on the squadron's books -
        all but the killed (state 2) and the missing (state 3) - keyed by
        pilot id, for the roster's expandable rank column. Asked for only
        when the reader opens it: one evaluation per pilot.
        """
        from .. import progress as prog

        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career, squad = db.career(), db.squadron()
            out = {}
            for pilot in db.pilots():
                if pilot["state"] in (2, 3):
                    continue
                values = prog.pilot_variables(pilot, career, squad)
                out[str(pilot["id"])] = self._next_promotion(
                    values, int(pilot["country"] or 0))
            return {"career_id": career_id, "pilots": out}

    def _routes(self, rung, values, country: int) -> List[Dict[str, Any]]:
        """
        Every unsatisfied way in, nearest first.

        ``evaluate`` reports only an OR's most promising branch, which is the
        right headline - it is the one the pilot will actually reach. But the
        eastern decorations are built almost entirely of ORs, five routes
        being ordinary rather than exceptional, so one bar is a small part of
        the truth and appears to jump about as the nearest branch changes
        under him. The rest go to the page to be folded away.
        """
        from .. import progress as prog

        if rung.eligible:
            return []
        defn = self.awards_cfg.get(rung.award_id)
        if defn is None or not defn.in_proc:
            return []
        out = []
        seen = set()
        for gaps in prog.routes_for(defn.in_proc, values):
            # A branch that wants another nationality is not a route this
            # man can take. The file shares one award between services by
            # an OR over Country, and enumerating those gave the Republic
            # of Korea citation three routes that read identically.
            if any(g.kind == "context" and g.variable.lower() == "country"
                   for g in gaps):
                continue
            key = tuple(sorted((g.variable.lower(), g.op, g.needed) for g in gaps))
            if key in seen:
                continue
            seen.add(key)
            if len(out) >= 5:
                break
            dice = [g for g in gaps if g.kind == "dice"]
            out.append({
                # A route can be a count in its own right, not only a deed
                # in one sortie: "thirty targets" is as much a way in as
                # "six in a single sortie", and the eastern awards are
                # almost entirely the former.
                "bars": [{"what": g.variable, "have": round(g.current, 1),
                          "need": g.needed, "unit": prog.unit_for(g.variable),
                          "fraction": round(g.fraction, 3)}
                         for g in gaps if g.kind == "cumulative"],
                # WIASortie counts as a per-sortie variable in the engine,
                # but to a reader it is a wound, not a tally - the Medal of
                # Honor's second route is "wounded and five kills", not
                # "one wound and five kills".
                "conditions": [{"what": g.variable, "need": g.needed,
                                "unit": prog.unit_for(g.variable),
                                "exact": g.op == "="}
                               for g in gaps if g.kind == "per_sortie"
                               and g.variable.lower() != "wiasortie"],
                "prereqs": [self._prereq(g, country) for g in gaps
                            if g.kind == "context"
                            or g.variable.lower() == "wiasortie"],
                "chance": min((g.needed for g in dice), default=0) / 1000.0
                if dice else None,
            })
        return out if len(out) > 1 else []

    def _prereq(self, gap, country: int) -> Dict[str, Any]:
        """One context condition, in terms the page can put a name to."""
        name = gap.variable.lower()
        if name in ("wia", "wiasortie"):
            return {"kind": "wia"}
        if name == "rankid":
            return {"kind": "rank",
                    "rank": self.locale.rank_name(country, int(gap.needed))}
        if name == "iscommander":
            return {"kind": "command"}
        if name == "cdate":
            # The engine holds a date as 19510601. Rendered raw it said
            # "CDate" in the middle of a route, which tells a reader
            # nothing about what he is waiting for.
            d = int(gap.needed)
            return {"kind": "date",
                    "date": f"{d // 10000}.{d // 100 % 100:02d}.{d % 100:02d}"}
        return {"kind": "other", "what": gap.variable}

    def _citation_ladders(self, current, retired) -> List[Dict[str, Any]]:
        """
        Decorations to the unit itself, one row per ladder, every rung the
        unit has held in the order it earned them. Unlike a pilot's medals
        these are shown in full rather than folded: a wing's citations are
        its history, and there are only ever a handful.
        """
        ladders: Dict[int, Dict[str, Any]] = {}
        for row in list(current) + list(retired):
            root = self._ladder_root(row["type"])
            ladder = ladders.setdefault(root, {
                "type": root, "name": self.award_name(root), "awards": []})
            ladder["awards"].append({
                "type": row["type"],
                "name": self.award_name(row["type"]),
                "earned": row["earnedDate"],
                "received": row["receivedDate"],
                "current": not row["isDeleted"],
            })
        for ladder in ladders.values():
            ladder["awards"].sort(key=lambda a: (a["earned"], a["type"]))
        # Ladders in awards.cfg order, so the DUC row comes before the ROK PUC.
        def order(root: int) -> int:
            defn = self.awards_cfg.get(root)
            return defn.order if defn else root
        return [ladders[k] for k in sorted(ladders, key=order)]

    def _ribbon_rack(self, medals: List[Dict[str, Any]], citations=(),
                     country: Optional[int] = None,
                     rank_id: Optional[int] = None) -> Dict[str, Any]:
        """
        The ribbons worn on the tunic. Individual decorations on the left
        breast: one per ladder, highest precedence first, rows of three with
        a short top row; pending awards are not worn yet. Unit citations are
        the squadron's, worn by everyone serving with it, and on the right
        breast - so they come back as a separate rack. Names ride along for
        the tooltips.
        """
        def entries(ids):
            return [{"type": t, "name": names.get(t) or self.award_name(t),
                     "framed": ribbons.RIBBONS[t].framed,
                     "geometry": ribbons.geometry(t)} for t in ids]
        wanted = os.environ.get("KOREA_PREVIEW_RACK", "")
        preview = PREVIEW_RACK.get(wanted) or tuple(int(t) for t in wanted.split(",") if t.strip().isdigit())
        if preview:
            # A developer's switch, see PREVIEW_RACK.
            medals = [{"type": t, "name": self.award_name(t), "pending": False} for t in preview]
            if wanted in ("navy", "usmc"):
                country = 602 if wanted == "navy" else 603
                citations = [{"type": t, "category": 2, "isDeleted": 0}
                             for t in (602041, 602047, 601049)]
            elif wanted in ("sov", "dprk"):
                # The switch set a country for the naval racks but not for
                # these two, so a Soviet preview came back on an Air Force
                # coat and could never reach the Soviet case.
                country = 501 if wanted == "sov" else 503
                citations = []
            elif preview[0] == 601041:
                citations = [{"type": t, "category": 2, "isDeleted": 0}
                             for t in (601046, 601049)]
        names = {m["type"]: m["name"] for m in medals}
        worn = ribbons.rack(m["type"] for m in medals if not m["pending"])
        unit = ribbons.rack(row["type"] for row in citations
                            if row["category"] == 2 and not row["isDeleted"])
        # The aviator badge worn above the ribbons, sliced from the game's
        # atlas like any medal. Select the service-specific badge and coat.
        held = {m["type"] for m in medals if not m["pending"]}
        country_code = (str(country) if country is not None else
                        next((str(t)[:3] for t in list(worn) + list(unit) if t), ""))
        badges = ((602001,) if country_code in ("602", "603") else
                  (601040, 601027, 601001))
        badge = next((b for b in badges if b in held), None)
        # Full dress: the awards themselves. USAF medals normally three to a
        # row, overlapping up to five when needed to stay within four rows,
        # with the Medal of Honor at the collar; Soviet-pattern orders
        # and medals on their mounts, five to a row, the screw-back orders
        # pinned to the right breast and the Hero's star above everything.
        held = {m["type"] for m in medals if not m["pending"]}
        kit = medal_art.wear(held)
        if not country_code and badge:
            country_code = str(badge)[:3]
        coat = {"601": "usaf", "602": "usnavy", "603": "usmc",
                "501": "sov", "503": "dprk"}.get(country_code)
        # Where unit citations are worn. Everyone mounts them in the rack in
        # service dress - the Air Force moved them off the right breast into
        # the ribbon group with the 1950s blue uniform, and the naval
        # services wear them in the rack too. In full dress they part
        # company: the Air Force keeps them with the medals on the left,
        # while the naval services wear one - only the senior of the
        # PUC/DUC/NUC group, per the 1951 rule - on the right breast.
        unit_in_service = coat in ("usnavy", "usmc", "usaf")
        # How many unit ribbons are worn in full dress, on the breast
        # opposite the medals: the Navy one, the senior of them (the 1951
        # rule), the Marine Corps all of them, and the Air Force none at
        # all - having moved them into the ribbon group, it wears no
        # separate strip beside large medals. None here means all of them.
        unit_dress_limit = {"usnavy": 1, "usaf": 0}.get(coat)
        service_worn = ribbons.rack(list(worn) + list(unit)) if unit_in_service else worn
        name = lambda t: names.get(t) or (self.award_name(t) if t else "")   # noqa: E731

        def pieces(ids):
            # Atlas-drawn pieces carry their width on the coat, in percent.
            return [{"type": t, "name": name(t),
                     "w": medal_art.width_pct(self.icons, t, coat) if coat else None} for t in ids]
        return {
            "ribbons": entries(service_worn),
            "rows": ribbons.rows(len(service_worn), ribbons.per_row_for(coat, len(service_worn))),
            "ribbon_per_row": ribbons.per_row_for(coat, len(service_worn)),
            "citations": entries(unit),
            "citation_rows": ribbons.rows(len(unit)),
            "medals": pieces(kit["bar"]),
            "medal_rows": medal_art.rows_for(coat, len(kit["bar"])),
            "pinned": pieces(kit["pinned"]),
            "hero": pieces([kit["hero"]])[0] if kit["hero"] else None,
            "wings": pieces([kit["wings"]])[0] if kit["wings"] else None,
            "stripes": pieces(kit["stripes"]),
            "neck": kit["neck"],
            "neck_name": name(kit["neck"]),
            "neck_src": medal_art.neck_url(kit["neck"], coat),
            "medal_rev": medal_art.REVISION,
            # Shared awards - the Korean Service Medal above all - carry
            # point-down stars for a sailor or Marine, point-up for the
            # Air Force, so the pictures are asked for by service.
            "svc": "navy" if coat in ("usnavy", "usmc") else "",
            "badge": badge,
            "badge_name": name(badge),
            "tunic": coat,
            # The air force this kit belongs to, which is not always the
            # pilot's own: the preview switch dresses him in another's.
            "country": int(country_code) if country_code.isdigit() else None,
            "rank_overlay": (NAVY_RANK_OVERLAYS.get(rank_id) if coat == "usnavy" else
                             USMC_RANK_OVERLAYS.get(rank_id) if coat == "usmc" else
                             USAF_ST_RANK_OVERLAYS.get(rank_id) if coat == "usaf" else None),
            "rank_overlay_full": (USMC_BD_RANK_OVERLAYS.get(rank_id) if coat == "usmc" else
                                  USAF_RANK_OVERLAYS.get(rank_id) if coat == "usaf" else None),
            "dress_coat": USMC_DRESS_COAT if coat == "usmc" else None,
            # The coat worn in service dress, where that is not simply
            # tunic_<coat>.jpg. The Navy's is khaki; its white coat is the
            # full-dress one and stays the default.
            "service_coat": (NAVY_SERVICE_COAT if coat == "usnavy" else
                             USAF_SERVICE_COAT if coat == "usaf" else None),
            "lapel": _lapel(NAVY_SERVICE_COAT if coat == "usnavy" else
                            USAF_SERVICE_COAT if coat == "usaf" else
                            f"tunic_{coat}.jpg" if coat else None),
            "lapel_full": _lapel(USMC_DRESS_COAT if coat == "usmc" else
                                 f"tunic_{coat}.jpg" if coat else None),
            # Worn on the shirt collar with the khaki coat, alongside the
            # boards rather than instead of them.
            "collar_overlay": (NAVY_COLLAR_OVERLAYS.get(rank_id)
                               if coat == "usnavy" else None),
            "unit_in_service": unit_in_service,
            "unit_dress_limit": unit_dress_limit,
            "rev": ribbons.REVISION,
        }

    def _promotions_and_awards(self, awards, country: int = 601) -> Dict[str, List]:
        """
        Group a pilot's award rows. Rows retired by a higher cluster
        (isDeleted=1, the engine's AwardRemove bookkeeping) are not listed on
        their own; each is filed under the rung that replaced it as
        ``history``, so the record shows the ribbon the pilot wears now and,
        folded beneath it, the ones it superseded with their dates.
        """
        promotions, medals = [], []
        retired = [row for row in awards if row["isDeleted"]]
        # A rung the engine forgot to retire is superseded all the same.
        # AwardRemove is meant to delete the lower rung the moment a cluster
        # is granted, but the game does not always apply it: a pilot given
        # the Medal of Honor and then its oak leaf cluster was found holding
        # 601026 and 601041 at once, both undeleted, and the page listed the
        # medal twice. So a rung named in the AwardRemove of a higher rung
        # the pilot ALSO holds is filed as history, exactly as a properly
        # retired one would be.
        standing = [row for row in awards
                    if not row["isDeleted"] and row["category"] != 1]
        outranked = set()
        for row in standing:
            outranked.update(self._superseded(row["type"]))
        superseded = retired + [row for row in standing
                                if row["type"] in outranked]
        for row in awards:
            if row["isDeleted"]:
                continue
            if row["category"] != 1 and row["type"] in outranked:
                continue
            if row["category"] == 1:
                rank_id = row["type"] - PROMOTION_BASE + 1
                promotions.append({
                    "rank": self.locale.rank_name(country, rank_id),
                    "rank_id": rank_id,
                    "rank_key": f"{country}{rank_id}",
                    "date": row["receivedDate"] if not row["isPending"]
                            else row["earnedDate"],
                    "pending": bool(row["isPending"]),
                })
            else:
                below = self._superseded(row["type"])
                history = [
                    {"type": old["type"],
                     "name": self.award_name(old["type"]),
                     "earned": old["earnedDate"],
                     "received": old["receivedDate"]}
                    for old in superseded if old["type"] in below
                ]
                # Nearest rung first, so the list reads downwards into the past.
                history.sort(key=lambda h: (h["earned"], h["type"]), reverse=True)
                medals.append({
                    "type": row["type"],
                    "name": self.award_name(row["type"]),
                    "earned": row["earnedDate"],
                    "received": row["receivedDate"],
                    "pending": bool(row["isPending"]),
                    "history": history,
                })
        return {"promotions": promotions, "awards": medals}

    def _incidences(self, events, aircraft_flown: str = "") -> List[Dict[str, Any]]:
        """Everything in the pilot's history that is *not* an award."""
        out = []
        for row in events:
            info = describe(row["type"])
            if info.key == "kill" or is_award_event(row["type"]):
                continue
            if row["type"] in (35, 36):
                # Aircraft report (bailed out / damaged) and evading: named in
                # events.py, but not a pilot's history - left out on purpose.
                continue
            entry = {"date": row["date"][:10], "kind": info.key,
                     "label": info.label, "confidence": info.confidence}
            # A key only where a translation exists: an unmapped event code
            # would otherwise print "incidences.unknown_13" at the reader.
            if not info.key.startswith("unknown"):
                entry["key"] = "incidences." + info.key
            if info.key == "plane_lost":
                # tpar1 is the aircraft type for AI pilots but the player's own
                # account name for the player, which is neither useful nor
                # something to put on screen. Fall back to the aircraft flown.
                described = self.objects.describe(row["tpar1"])
                entry["detail"] = (described["name"] if described["named"]
                                   else aircraft_flown)
            elif info.key == "friendly_destroyed":
                described = self.objects.describe(row["tpar1"])
                entry["detail"] = described["name"] if described["named"] else row["tpar1"]
            elif info.key in ("wounded", "medical"):
                if info.key == "medical" and row["ipar1"] == 1:
                    entry["label"] = "Returned to duty"
                    entry["key"] = "incidences.returned_to_duty"
                    entry["kind"] = "recovered"
                else:
                    entry["detail"] = f"health {row['ipar2']}"
                    entry["detail_key"] = "incidences.health"
                    entry["detail_value"] = row["ipar2"]
            out.append(entry)
        out.reverse()
        return out

    @staticmethod
    def _victory_roll(debriefings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Every air-to-air victory of the career, newest first.

        A fighter pilot's record is built around this list and the page had no
        equivalent: the debriefings answer "what happened on mission 43", never
        "what has this man shot down". Airborne only — a parked aircraft
        strafed on its dispersal is a ground target, and the game scores it
        that way too.
        """
        out = []
        for debrief in debriefings:
            for kill in debrief["log"]:
                if not kill.get("air"):
                    continue
                out.append({
                    "date": debrief["date"],
                    "time": kill["time"],
                    "mission_id": debrief["mission_id"],
                    "mission_num": debrief["mission_num"],
                    "type": kill["target"],
                    "victim": kill["victim"],
                    "altitude": kill["altitude"],
                })
        # The debriefings run newest mission first but each log inside one runs
        # in time order, so the raw concatenation numbers a sortie's kills
        # backwards. Sorting the whole roll by date and clock fixes it.
        out.sort(key=lambda v: (v["date"], v["time"]), reverse=True)
        total = len(out)
        for index, victory in enumerate(out):
            victory["number"] = total - index
        return out

    def _performance(self, db, player, victories: List[Dict[str, Any]]
                     ) -> List[Dict[str, Any]]:
        """
        The counters the career keeps for itself.

        mission.result carries a streak and a points tally per pilot per
        mission that nothing in the game's own UI shows. Six neighbouring
        counters — assists, friendly kills, the three objective tallies and the
        eject flag — are zero in all 31 missions of a real career, so they are
        left out rather than rendered as a column of noughts.

        There is deliberately no accuracy figure. Nothing records rounds
        fired: the flight log's hit records carry no ammunition type (all
        38,091 in one mission read "explosion") and count damage events rather
        than bullets, so any hit rate would be authoritative-looking nonsense.
        """
        # airKillStreak is NOT airborne victories. Proved on mission 31: the
        # counter reads 5 for a sortie with no airborne kill at all and five
        # aircraft strafed on their dispersal, and on mission 34 it reads 7
        # for 4 airborne plus 3 parked. It counts every aircraft destroyed.
        # Reporting it as an air-victory figure overstated the best sortie by
        # nearly double, so the best sortie is taken from killStats instead —
        # the same decoding the rest of the page counts victories with.
        best_air = best_ground = 0
        best_air_mission = best_ground_mission = None
        best_points = career_points = 0
        best_points_mission = None

        missions = {m["id"]: m for m in db.missions()}
        for sortie in db.sorties(player["id"]):
            kills = KillStats(sortie["killStats"])
            if kills.airborne > best_air:
                best_air, best_air_mission = kills.airborne, sortie["missionId"]
            if kills.ground_targets > best_ground:
                best_ground, best_ground_mission = (kills.ground_targets,
                                                    sortie["missionId"])

        for mission in missions.values():
            for row in MissionResult(mission["result"]).players():
                if not row.get("personageNickname"):
                    continue                      # AI rows carry no nickname
                points = int(_number(row.get("pointsSumByMission", "0")))
                career_points += points
                if points > best_points:
                    best_points, best_points_mission = points, mission["id"]

        sorties = player["sorties"] or 0
        hours = (player["flightTime"] or 0) / 3600.0
        airborne = KillStats(player["killStats"]).airborne
        altitudes = [v["altitude"] for v in victories if v["altitude"]]
        average = round(sum(altitudes) / len(altitudes)) if altitudes else None

        def number(mission_id):
            row = missions.get(mission_id)
            return row["missionNum"] if row else None

        # mission_id makes a row clickable: the figure is only interesting
        # alongside the sortie that produced it.
        # value_key marks a value that is itself prose and so has to be
        # assembled in the reader's language rather than here.
        return [
            {"key": "performance.best_air_sortie", "label": "Best sortie, air victories",
             "value": best_air, "value_key": "performance.in_one_sortie",
             "mission_id": best_air_mission, "mission_num": number(best_air_mission),
             "hint_key": "performance.best_air_sortie_hint"},
            {"key": "performance.best_ground_sortie", "label": "Best sortie, ground targets",
             "value": best_ground, "value_key": "performance.in_one_sortie",
             "mission_id": best_ground_mission, "mission_num": number(best_ground_mission),
             "hint_key": "performance.best_ground_sortie_hint"},
            {"key": "performance.per_sortie", "label": "Victories per sortie",
             "value": f"{airborne / sorties:.2f}" if sorties else "—",
             "hint_key": "performance.per_sortie_hint"},
            {"key": "performance.per_hour", "label": "Victories per flight hour",
             "value": f"{airborne / hours:.1f}" if hours else "—",
             "hint_key": "performance.per_hour_hint"},
            {"key": "performance.average_altitude", "label": "Average victory altitude",
             "value": f"{average:,}" if average is not None else "—",
             "value_key": "common.metres" if average is not None else None,
             "hint_key": "performance.average_altitude_hint"},
            {"key": "performance.best_score", "label": "Best mission score",
             "value": f"{best_points:,}",
             "mission_id": best_points_mission, "mission_num": number(best_points_mission),
             "hint_key": "performance.best_score_hint"},
            {"key": "performance.career_score", "label": "Career score",
             "value": f"{career_points:,}",
             "hint_key": "performance.career_score_hint"},
        ]

    def _debriefings(self, db, sorties, kill_events,
                     with_flight_log: bool = True) -> List[Dict[str, Any]]:
        """
        One block per sortie, with a kill log worth reading.

        Only named targets are listed — aircraft, vehicles, guns, ships,
        trains. Scenery (crates, coils, barrels, tents) has no name or category
        in the game's own data and is summarised as a count instead: a napalm
        run on an airfield can register forty of them, which buries the kills
        that actually matter.
        """
        by_mission: Dict[int, List] = {}
        for row in kill_events:
            by_mission.setdefault(row["missionId"], []).append(row)
        missions = {m["id"]: m for m in db.missions()}
        planes = {p["id"]: p for p in db.query("SELECT id, slot, config, tcode FROM plane")}
        # What each pilot carried, from the mission's own manifest; parsed
        # once per mission, since every sortie of it shares the record.
        manifests: Dict[int, Dict[int, Dict[str, Any]]] = {}

        out = []
        for sortie in sorties:
            mission = missions.get(sortie["missionId"])
            if mission is not None and mission["id"] not in manifests:
                manifests[mission["id"]] = {
                    r["pilot_id"]: r for r in parse_pilots_list(mission["pilotsList"])}
            carried = manifests.get(sortie["missionId"], {}).get(sortie["pilotId"])
            airframe = planes.get(sortie["planeId"])
            plane_key = PurePath(airframe["config"]).stem if airframe and airframe["config"] else ""
            events = sorted(by_mission.get(sortie["missionId"], []),
                            key=lambda r: r["date"])
            # mission.result carries the same kills with the victim's pilot
            # name and the altitude, neither of which is in the event table.
            # Only the player's kills can be attributed from it — an AI row's
            # actor is the aircraft type, not a pilot — so the enrichment is
            # matched per target type, in order, and only for the player.
            extra = {}
            if with_flight_log and mission is not None:
                for e in MissionResult(mission["result"]).events():
                    if e["victim"] or e["altitude"]:
                        extra.setdefault(e["target"], []).append(e)

            log, scenery = [], 0
            for row in events:
                info = self.objects.describe(row["tpar1"])
                if not info["named"]:
                    scenery += 1
                    continue
                entry = {
                    "time": row["date"][11:19],
                    "target": info["name"],
                    "category": info["category"],
                    "air": info["aircraft"] and not info["parked"],
                    "parked": info["parked"],
                    "victim": "",
                    "altitude": None,
                }
                queue = extra.get(row["tpar1"])
                if queue:
                    found = queue.pop(0)
                    entry["victim"] = found["victim"]
                    # Absolute altitude, so on anything that was already on the
                    # ground it is just the terrain height under it, repeated
                    # down the whole strafing run.
                    if entry["air"]:
                        entry["altitude"] = found["altitude"]
                log.append(entry)
            k = KillStats(sortie["killStats"])
            # The flight log knows when the wheels left the ground and how the
            # sortie ended; the career DB knows neither.
            # Named `flight` rather than `log`: the kill list in this scope is
            # already called `log`, and shadowing it serialised this NamedTuple
            # into the payload as a list.
            flight = (self.flightlogs.for_sortie(sortie["date"][:10],
                                                 sortie["date"][11:16])
                      if with_flight_log else None)
            flight = self._shifted_log(db, sortie["missionId"], flight)
            # Damage taken, folded into the same timeline as the kills: what a
            # reader wants is the order things happened in, not two lists.
            if flight is not None and flight.damage:
                start = sortie["date"][11:]
                for burst in flight.damage:
                    log.append({
                        "time": _clock(start, burst.at_s),
                        "target": "",
                        "category": "",
                        "air": False,
                        "parked": False,
                        "victim": "",
                        "altitude": None,
                        "hurt": {
                            "hits": burst.hits,
                            "amount": round(burst.amount * 100),
                            "total": round(burst.total * 100),
                            # The log gives an object type; the index turns it
                            # into the game's own name, in the reader's
                            # language. Empty stays empty — 91% of the damage a
                            # career pilot takes records no attacker at all,
                            # and "unknown" beside every hit says nothing.
                            "attacker": self._attacker_name(burst.attacker),
                            "self_inflicted": burst.attacker == SELF_DAMAGE,
                        },
                    })
                log.sort(key=lambda row: row["time"])

            outcome = PLANE_OUTCOME.get(sortie["planeStatus"], "unknown")
            # A key rather than prose: the front end renders it in whichever
            # language this record belongs to.
            landing = landing_key = ""
            # sortie.status is the pilot's fate on that sortie, on the same
            # scale as pilot.state (2 killed, 3 missing, 4 wounded - the
            # career's one fatal sortie is status 2, health 0). A crash that
            # kills the pilot still writes a landing line into the flight
            # log, and the record read "landed, aircraft written off" for the
            # mission the player died on. The fate comes first.
            if sortie["status"] == 2:
                landing, landing_key = "killed in action", "killed"
            elif sortie["status"] == 3:
                landing, landing_key = "did not return", "did_not_return"
            elif flight is not None:
                if flight.ejected:
                    landing, landing_key = "bailed out", "bailed_out"
                elif flight.landing_s is None and outcome == "lost":
                    landing, landing_key = "did not return", "did_not_return"
                elif flight.landing_s is None:
                    # No landing in the log, but the game booked the aircraft
                    # as back: the pilot ended the mission from the menu once
                    # near base, which the game accepts as a return and the
                    # log never sees as a touchdown. Reported on the forum as
                    # "did not return" on every sortie of a 45-mission career
                    # whose own totals read 36 returned, 0 lost. The game's
                    # verdict wins; the log only supplies the time, and here
                    # it has none.
                    landing, landing_key = (
                        ("returned, aircraft damaged", "returned_damaged")
                        if outcome == "damaged" else ("returned", "returned"))
                elif outcome == "lost":
                    # The aircraft was written off but the pilot put it down and
                    # walked away. Reported as a plain landing until now, which
                    # made the two write-offs of this career look routine.
                    landing, landing_key = ("landed, aircraft written off",
                                            "force_landed_long")
                elif outcome == "damaged":
                    landing, landing_key = "landed, aircraft damaged", "landed_damaged"
                else:
                    landing, landing_key = "landed", "landed"
            out.append({
                "takeoff": _clock(sortie["date"][11:], flight.takeoff_s) if flight else "",
                "landing_time": _landing_clock(sortie["date"][11:], flight, sortie["flightTime"]),
                "landing": landing,
                "landing_key": landing_key,
                "aircraft": flight.plane if flight else "",
                "mission_id": sortie["missionId"],
                "mission_num": mission["missionNum"] if mission else None,
                "date": sortie["date"][:10],
                "time": sortie["date"][11:16],
                "type": self.locale.mission_type_name(mission["type"]) if mission
                        else "Unknown",
                "duration": _hm(sortie["flightTime"]),
                "outcome": PLANE_OUTCOME.get(sortie["planeStatus"], "unknown"),
                "wounded": sortie["status"] == 4,
                "airborne": k.airborne,
                "ground_targets": k.ground_targets,
                # Shared kills and own-side losses, from the sortie row. The
                # second is rare and grave enough that a file should carry it.
                "assists": sortie["assistCount"] or 0,
                "friendly_kills": sortie["fkill"] or 0,
                # The airframe flown, by tail number - a line-up number is
                # only where it is parked today - and what it carried: stores
                # from the mission manifest, named as the hangar names them;
                # the fuel fraction capped at full, since a scheme with drop
                # tanks records 2.0 and the tanks are already listed.
                "airframe": _tail_code(airframe["tcode"], plane_key) if airframe else "",
                "plane_id": sortie["planeId"],
                "loadout": (self.ammo.describe(plane_key, carried["payload_id"])
                            if carried and plane_key else ""),
                "fuel_pct": (round(min(carried["fuel"], 1.0) * 100)
                             if carried else None),
                "range_km": (round(mission["mrange"] / 1000)
                             if mission and mission["mrange"] else None),
                "gunnery": self._gunnery(flight, sortie["date"][11:]),
                "log": log,
                "scenery": scenery,
            })
        out.reverse()
        return out

    def pilot_summary(self, career_id: str, pilot_id: int) -> Optional[Dict[str, Any]]:
        """
        Enough for the roster modal: who he is, what he has done, what he wears.

        Deliberately not the whole record — the modal is for a glance while
        scanning the roster, and offers a link to the full page for the rest.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            row = db.pilot(pilot_id)
            if row is None:
                return None
            awards_by_pilot = {pilot_id: db.awards(pilot_id)}
            summary = self._pilot_row(row, awards_by_pilot)
            groups = self._promotions_and_awards(
                db.awards(pilot_id, include_removed=True), row["country"])
            sorties = db.sorties(pilot_id)
            kills = KillStats(row["killStats"])
            summary.update({
                "career_id": career_id,
                "squadron": meta.squadron_name,
                "combat": self._combat_results(kills)["headline"],
                "awards_list": groups["awards"],
                "ribbon_rack": self._ribbon_rack(
                    groups["awards"], db.awards(-1), row["country"], row["rankId"]),
                "promotions_list": groups["promotions"],
                "incidences": self._incidences(db.events(pilot_id)),
                "recent": self._debriefings(
                    db, sorties[-5:], db.events(pilot_id, types=[0]),
                    with_flight_log=bool(row["isPlayer"])),
                "missions_flown": self._missions_flown(sorties, {m["id"]: m for m in db.missions()}),
            })
            return summary

    def biography(self, career_id: str,
                  pilot_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """The selected player's in-game biography in this page's language."""
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            pilot = db.pilot(pilot_id) if pilot_id is not None else db.player()
            if pilot is None:
                return None
            described = _pilot_description(pilot["description"])
            biography_id = described.get("biographyId", "")
            if not biography_id:
                return None

            vpath = ("nsdata/assets/characterbio/"
                     f"bio.id={biography_id}.locale={self.lang}.txt")
            raw = self.resolver.read_text(vpath)
            source_language = self.lang
            if not raw and self.lang != "eng":
                source_language = "eng"
                raw = self.resolver.read_text(
                    "nsdata/assets/characterbio/"
                    f"bio.id={biography_id}.locale=eng.txt")
            paragraphs = _biography_paragraphs(raw or "")
            # A biography the player rewrote in the Career Helper wins.
            own = custombio.load(Path(meta.path), pilot["id"])
            custom = bool(own and own["text"])
            if custom:
                paragraphs = custombio.paragraphs(own["text"])
                source_language = self.lang
            if not paragraphs:
                return None

            sorties = db.sorties(pilot["id"])
            starting_rank_id = (sorties[0]["rankId"] if sorties
                                else pilot["rankId"])
            return {
                "career_id": career_id,
                "biography_id": biography_id,
                "custom": custom,
                "source_language": source_language,
                "paragraphs": paragraphs,
                "pilot": {
                    "id": pilot["id"],
                    "name": f"{pilot['name']} {pilot['lastName']}".strip(),
                    "first_name": pilot["name"],
                    "last_name": pilot["lastName"],
                    "birth_date": described.get("birthDate", ""),
                    "starting_rank": self.locale.rank_name(
                        pilot["country"], starting_rank_id),
                },
            }

    def diary(self, career_id: str) -> Optional[Dict[str, Any]]:
        """
        The squadron's war diary: every day of the career that has one.

        Its own page rather than another panel on the record - the detail
        page already carries fifteen of them - and its own endpoint, the
        way the logbook and the certificate have theirs.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career = db.career()
            today = (career["currentDate"] or "")[:10] if career else ""
            data = DiaryBuilder(self, db, today).build()
            player = db.player()
            squad = db.squadron()
            country = player["country"] if player else 601
            data.update({
                "career_id": career_id,
                "squadron": meta.squadron_name,
                "pilot": f"{player['name']} {player['lastName']}".strip() if player else "",
                "today": today,
                # The page's furniture: the squadron's own emblem, its
                # service's seal, and the aeroplane it flies, all of which
                # the tracker already holds.
                "squadron_key": str(squad["configId"]) if squad else "",
                "country": country,
                "seal": COUNTRY_SEALS.get(country, ""),
                "plane": self._squadron_plane(db),
                "navy": country in (602, 603),
            })
            return data

    def _ui_stale(self) -> List[str]:
        if not hasattr(self, "_ui_stale_cache"):
            from .. import uioverrides
            self._ui_stale_cache = uioverrides.stale(self.resolver)
        return self._ui_stale_cache

    @staticmethod
    def _sortie_loss(db) -> Dict[str, Any]:
        """
        Missions the game finished but never wrote the sorties for.

        Steam build 25605106 (2026-09-29) ships an INSERT for the sortie
        table that names eighteen columns and supplies seventeen values, so
        SQLite rejects every one. The mission, the awards and the pilots'
        own counters are all written normally - only the per-sortie record
        is thrown away, which makes it look as though this application has
        lost them.

        A mission still in state 0 has simply not been flown yet, so its
        having no sorties means nothing; anything the game has closed and
        left empty is the fault above.
        """
        row = db.query_one(
            "SELECT COUNT(*) AS n, MIN(date) AS first FROM mission m "
            "WHERE m.isDeleted=0 AND m.state<>0 AND NOT EXISTS ("
            "  SELECT 1 FROM sortie s WHERE s.missionId=m.id AND s.isDeleted=0)")
        missions = int(row["n"] or 0) if row else 0
        return {"missions": missions, "since": (row["first"] if row else None) or ""}

    @staticmethod
    def _squadron_plane(db) -> str:
        """
        The squadron's current aircraft, as the game's own plane key.

        plane.config is a path — "luascripts/worldobjects/planes/f51d.txt" —
        and its stem is the same key the world-object index and the artwork
        file names use. The most common type on strength wins, so a handful of
        replacements arriving early during a conversion cannot flip the page.
        """
        rows = db.query("SELECT config FROM plane WHERE isDeleted = 0")
        if not rows:
            return ""
        counts = Counter(PurePath(r["config"]).stem.lower() for r in rows
                         if r["config"])
        return counts.most_common(1)[0][0] if counts else ""

    def _aircraft(self, db, career, squad, career_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        The squadron's aircraft: what is serviceable, what is in the shop and
        for how long, and what is on its way.

        Asked for on the forum - "how many of my aircraft are in repair, how
        long will I wait, and when are new ones arriving". The game keeps all
        three. plane.slot uses the same bands as pilot.slot: 0..19 the
        line-up, 1000..4999 spare and reserve airframes, 5000+ the write-offs.
        plane.state is 0 serviceable, 2 in repair, 3 written off; a repair
        carries its completion in stateEndDate, so the wait is the game's own
        figure, not an estimate (durations in one career ran 0.5 to 10 days,
        and not in proportion to the damage). supply.type 1 is aircraft,
        with objectCfg the type, quantity the number and scheduled the
        arrival; status 3 is delivered, anything else still on its way.
        Type 2 is replacement pilots, 3/4/5 the three stores the game's
        Resources screen calls Fuel, Ordnance and Equipment (the table
        columns say fuelQty, ammoQty, partsQty). Fuel is in litres and the
        other two in "units", as the Resources screen prints them (566279 L,
        11502 units); status 0 is a request on schedule, 3 delivered.
        """
        now = career["currentTime"] or f"{career['currentDate']} 06:00:00"
        planes = db.query("SELECT * FROM plane WHERE isDeleted = 0 ORDER BY slot, id")

        def type_name(config: str) -> str:
            stem = PurePath(config or "").stem
            described = self.objects.describe(stem) if stem else {"named": False}
            return described["name"] if described["named"] else stem

        # A write-off can sit in its line-up slot until the game moves it
        # (the player's crashed aircraft was still at slot 0 five days on).
        # The game's Resources screen still counts it - "In service 22/24,
        # out of service 2" with one in repair and that wreck - so the
        # strength here is by slot, as the game's is, and the wreck is in
        # the written-off figure as well.
        written_off = [p for p in planes if p["slot"] >= 5000 or p["state"] == 3]
        on_strength = [p for p in planes if p["slot"] < 5000]
        serviceable = [p for p in on_strength if p["state"] == 0]
        repairing = [p for p in on_strength if p["state"] == 2]

        repairs = []
        for p in sorted(repairing, key=lambda p: p["stateEndDate"]):
            ready = p["stateEndDate"] if not p["stateEndDate"].startswith("0000") else ""
            repairs.append({
                "slot": p["slot"],
                "code": _tail_code(p["tcode"], PurePath(p["config"]).stem if p["config"] else ""),
                "type": type_name(p["config"]),
                "health": p["health"],
                "since": p["stateDate"][:10],
                "ready": ready[:10],
                # Whole days from the career clock; the game rolls the day
                # at 06:00, so a repair due at 22:20 tonight reads as today.
                "days": max(0, _days_between(now, ready)) if ready else None,
            })

        supplies = db.query(
            "SELECT * FROM supply WHERE isDeleted = 0 ORDER BY scheduled, id")
        arrivals = []
        for s in supplies:
            kind = SUPPLY_KINDS.get(s["type"])
            if kind is None or s["status"] == 3:
                continue
            arrivals.append({
                "kind": kind,
                "quantity": s["quantity"],
                "type": type_name(s["objectCfg"]) if s["type"] == 1 else "",
                "date": s["scheduled"][:10],
                "days": max(0, _days_between(now, s["scheduled"])),
            })
        delivered = [s for s in supplies if s["type"] == 1 and s["status"] == 3]
        last = delivered[-1] if delivered else None

        # Every airframe's history: sortie.planeId ties each sortie to the
        # machine, the repair events (type 18, ipar1 = 0 start) count its
        # visits to the shop, and the sortie that lost it names the pilot.
        # Identity is plane.id - line-up numbers move as the game reshuffles
        # slots - and the tail number is the face of it.
        by_plane: Dict[int, List] = {}
        for s in db.query(
                """SELECT s.id, s.planeId, s.pilotId, s.killStats, s.planeStatus, s.date,
                          p.name, p.lastName, p.country, p.rankId
                   FROM sortie s JOIN pilot p ON p.id = s.pilotId
                   WHERE s.isDeleted = 0 ORDER BY s.id"""):
            by_plane.setdefault(s["planeId"], []).append(s)
        repairs_by_plane = Counter(
            e["planeId"] for e in db.query(
                "SELECT planeId FROM event WHERE type = 18 AND ipar1 = 0 AND isDeleted = 0"))
        arrived = {}
        for e in db.query(
                "SELECT planeId, date FROM event WHERE type = 15 AND isDeleted = 0 ORDER BY id"):
            arrived.setdefault(e["planeId"], e["date"][:10])

        def band(p) -> int:
            # 0 line-up (the "not ready" bench at 1000+ still belongs to it,
            # it is only parked there while in repair), 1 reserve, 2 gone.
            if p["state"] == 3 or p["slot"] >= 5000:
                return 2
            return 1 if p["slot"] >= 2000 else 0

        airframes = []
        for p in sorted(planes, key=lambda p: (band(p), p["slot"], p["id"])):
            flights = by_plane.get(p["id"], [])
            air = ground = 0
            pilots = Counter()
            for s in flights:
                ks = KillStats(db.kill_stats(s["id"], s["killStats"]))
                air += ks.airborne
                ground += ks.ground_targets
                pilots[s["pilotId"]] += 1
            usual = None
            if pilots:
                pid = pilots.most_common(1)[0][0]
                row = next(s for s in flights if s["pilotId"] == pid)
                usual = {"id": pid,
                         "name": f"{row['name']} {row['lastName']}".strip(),
                         "rank": self.locale.rank_name(row["country"], row["rankId"]),
                         "sorties": pilots[pid]}
            lost = None
            if band(p) == 2:
                fatal = next((s for s in reversed(flights)
                              if PLANE_OUTCOME.get(s["planeStatus"]) == "lost"), None)
                lost = {"date": (fatal["date"] if fatal else p["stateDate"])[:10],
                        "pilot": (f"{fatal['name']} {fatal['lastName']}".strip()
                                  if fatal else ""),
                        "pilot_id": fatal["pilotId"] if fatal else None}
            plane_key = PurePath(p["config"]).stem if p["config"] else ""
            airframes.append({
                "id": p["id"],
                "code": _tail_code(p["tcode"], plane_key),
                "number": (p["slot"] + 1) if p["slot"] < 1000 else None,
                "type": type_name(p["config"]),
                "status": ("written_off" if band(p) == 2
                           else "repair" if p["state"] == 2
                           else "reserve" if band(p) == 1 else "serviceable"),
                "health": p["health"],
                "since": arrived.get(p["id"], p["stateDate"][:10] if p["slot"] < 1000 else ""),
                "ready": (p["stateEndDate"][:10]
                          if p["state"] == 2 and not p["stateEndDate"].startswith("0000") else ""),
                "sorties": len(flights),
                "pilots": len(pilots),
                "usual": usual,
                "airborne": air,
                "ground_targets": ground,
                "repairs": repairs_by_plane.get(p["id"], 0),
                "lost": lost,
            })

        return {
            "airframes": airframes,
            "type": type_name(on_strength[0]["config"]) if on_strength else "",
            "on_strength": len(on_strength),
            "line_up": sum(1 for p in on_strength if p["slot"] < 1000),
            "serviceable": len(serviceable),
            "in_repair": len(repairing),
            # Slots 1000..1999 are the "not ready" bench, an aircraft in
            # repair with its pilot; those are counted in the repair figure.
            "reserve": sum(1 for p in on_strength if 2000 <= p["slot"] < 5000),
            "written_off": len(written_off),
            "repairs": repairs,
            "arrivals": arrivals,
            "last_delivery": ({"quantity": last["quantity"],
                               "type": type_name(last["objectCfg"]),
                               "date": last["statusDate"][:10]} if last else None),
            "received": sum(s["quantity"] for s in delivered),
            "stores": {
                "fuel": squad["fuelQty"] if squad else 0,
                "ordnance": squad["ammoQty"] if squad else 0,
                "equipment": squad["partsQty"] if squad else 0,
                "requests": squad["requestPoints"] if squad else 0,
            },
            "statistics": self._logistics(db, career, squad, len(written_off), career_path),
        }

    # The forecast horizons, in career days.
    LOGISTICS_HORIZONS = (7, 14, 30)
    # Flying days the stock history must cover before measured consumption
    # replaces the booked and estimated figures.
    MEASURED_MIN_DAYS = 3

    def _logistics(self, db, career, squad, written_off: int,
                   career_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """
        The squadron's consumption, its spread and a forecast - for the
        collapsible statistics under the materiel panel.

        What the game books, proven against the stock between career backups
        (2026-10-07): a completed mission takes exactly its ``assignedAmmo``;
        it takes fuel too, a little under ``assignedFuel`` (the aircraft burn
        some 7-15 % less). Assigned fuel is used here: it is what the game
        checks before a mission may fly, and it keeps the forecast on the
        safe side. Request points: each completed mission earns ``ipar1`` of
        its type-26 event, each delivery costs its ``cost``.

        Everything is counted per *flying day*, because a squadron flies in
        bursts - the 12th FBS flew on 30 of 100 days - and a per-calendar-day
        mean would smear three busy days across a week. The horizons are
        career days, so the flying rate carries them across.

        Equipment is booked nowhere per mission. It goes on repairs, so it is
        *estimated* from the repair starts (event type 18, ipar1 0, ipar2 the
        aircraft's health): about one unit per 20 % of damage, which matched
        the stock between two backups (5 % -> 1 unit, 56 % -> 3 units).

        Measured beats both: every read records the stocks (stockhistory),
        and once the readings cover MEASURED_MIN_DAYS flying days the real
        consumption replaces the booked and estimated means. The spread keeps
        the per-day shape of the booked figures, scaled to the measured mean.
        """
        import datetime as _dt
        import math
        import statistics

        def day(text):
            try:
                y, m, d = (int(x) for x in str(text)[:10].split("."))
                return _dt.date(y, m, d)
            except (TypeError, ValueError):
                return None

        flown = db.query("SELECT id, date, assignedFuel, assignedAmmo FROM mission "
                         "WHERE isDeleted=0 AND state<>0")
        today = day(career["currentDate"]) if career else None
        days = sorted({day(m["date"]) for m in flown if day(m["date"])})
        if not days or today is None:
            return None
        span = max(1, (today - days[0]).days + 1)
        earned = {}
        for e in db.query("SELECT date, ipar1 FROM event WHERE type=26 AND isDeleted=0"):
            d = day(e["date"])
            if d and (e["ipar1"] or 0) > 0:
                earned[d] = earned.get(d, 0) + e["ipar1"]
        repairs = {}
        for e in db.query("SELECT date, ipar2 FROM event WHERE type=18 AND ipar1=0 AND isDeleted=0"):
            d = day(e["date"])
            health = e["ipar2"] if e["ipar2"] is not None else 100
            if d:
                repairs[d] = repairs.get(d, 0) + max(1, math.ceil((100 - health) / 20))
        per_day = {d: {"fuel": 0, "ordnance": 0, "missions": 0, "requests": earned.get(d, 0),
                       "equipment": repairs.get(d, 0)}
                   for d in days}
        for m in flown:
            d = day(m["date"])
            if d in per_day:
                per_day[d]["fuel"] += m["assignedFuel"] or 0
                per_day[d]["ordnance"] += m["assignedAmmo"] or 0
                per_day[d]["missions"] += 1

        def spread(key):
            values = [v[key] for v in per_day.values()]
            return {"mean": round(statistics.mean(values), 1),
                    "sd": round(statistics.stdev(values), 1) if len(values) > 1 else 0.0}

        stats = {k: spread(k) for k in ("fuel", "ordnance", "equipment", "missions", "requests")}
        rate = len(days) / span
        stock = {"fuel": squad["fuelQty"] if squad else 0,
                 "ordnance": squad["ammoQty"] if squad else 0,
                 "equipment": squad["partsQty"] if squad else 0}

        delivered_total = {"fuel": 0, "ordnance": 0, "equipment": 0}
        for s in db.query("SELECT type, quantity FROM supply WHERE isDeleted=0 AND status=3"):
            kind = SUPPLY_KINDS.get(s["type"])
            if kind in delivered_total:
                delivered_total[kind] += s["quantity"] or 0
        source = {"fuel": "booked", "ordnance": "booked", "equipment": "estimated"}
        measured = None
        if career_path is not None:
            from .. import stockhistory
            readings = stockhistory.record(career_path, {
                "date": career["currentDate"], "stock": stock, "delivered": delivered_total,
                "last_mission": max((m["id"] for m in flown), default=0)})
            measured = stockhistory.measured(readings, flown)
        measured_days = measured["flying_days"] if measured else 0
        if measured and measured_days >= self.MEASURED_MIN_DAYS:
            for key in ("fuel", "ordnance", "equipment"):
                mean = measured["used"][key] / measured_days
                booked = stats[key]["mean"]
                sd = stats[key]["sd"] * (mean / booked) if booked else 0.0
                stats[key] = {"mean": round(mean, 1), "sd": round(sd, 1)}
                source[key] = "measured"

        horizons = []
        for h in self.LOGISTICS_HORIZONS:
            n = rate * h                      # expected flying days in the horizon
            row = {"days": h, "flying_days": round(n, 1)}
            for key in ("fuel", "ordnance", "equipment", "requests"):
                mean, sd = stats[key]["mean"], stats[key]["sd"]
                # the sum of n flying days: mean n*mu, spread sqrt(n)*sigma
                row[key] = round(n * mean)
                row[key + "_low"] = max(0, round(n * mean - math.sqrt(n) * sd))
                row[key + "_high"] = round(n * mean + math.sqrt(n) * sd)
            for key in ("fuel", "ordnance", "equipment"):
                row[key + "_left"] = stock[key] - row[key]
            horizons.append(row)
        lasts = {key: (round(stock[key] / (stats[key]["mean"] * rate))
                       if stats[key]["mean"] else None)
                 for key in ("fuel", "ordnance", "equipment")}

        delivered = {}
        for s in db.query("SELECT type, quantity, cost FROM supply "
                          "WHERE isDeleted=0 AND status=3"):
            kind = SUPPLY_KINDS.get(s["type"])
            if kind is None:
                continue
            row = delivered.setdefault(kind, {"count": 0, "quantity": 0, "cost": 0})
            row["count"] += 1
            row["quantity"] += s["quantity"] or 0
            row["cost"] += s["cost"] or 0
        for row in delivered.values():
            row["per_point"] = round(row["quantity"] / row["cost"], 1) if row["cost"] else None

        lost_pilots = db.query("SELECT COUNT(*) AS n FROM pilot WHERE isDeleted=0 AND state IN (2, 3)")
        month = 30 / span
        return {
            "span_days": span,
            "flying_days": len(days),
            "flying_rate": round(rate, 3),
            "per_flying_day": stats,
            "source": source,
            "measured_days": measured_days,
            "measured_needed": self.MEASURED_MIN_DAYS,
            "horizons": horizons,
            "lasts": lasts,
            "delivered": delivered,
            "losses_per_month": {
                "aircraft": round(written_off * month, 1),
                "pilots": round((lost_pilots[0]["n"] if lost_pilots else 0) * month, 1),
            },
        }

    @staticmethod
    def _crew(result: "MissionResult", flown: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Map each actor id in ``events`` to the pilot's name.

        The human is easy: their ``players`` row carries a real account guid,
        which is the ``actorUserId`` on their kills.

        The AI looked impossible — their rows have no nickname, and the career's
        ``pilot`` table leaves ``personageId`` empty — but the synthetic ids are
        formation slots, and the slot order is the order the ``sortie`` rows are
        written in. Two independent checks across both careers and all 372
        AI sorties: ``totalFlightTime`` agrees to the second every time, and so
        does the air-kill count summed from unrelated columns. The pairing is
        positional, so it is only used when the two lists are the same length,
        and the flight-time check is repeated per mission before trusting it.
        """
        ai_pilots = [f for f in flown if not f["is_player"]]
        slots = result.flight_slots()
        crew: Dict[str, str] = {}

        for row in result.players():
            uid = row.get("userId", "")
            if row.get("personageNickname") and uid:
                player = next((f["name"] for f in flown if f["is_player"]), "")
                if player:
                    crew[uid] = player

        if len(slots) == len(ai_pilots):
            pairs = list(zip(slots, ai_pilots))
            if all(_number(slot.get("totalFlightTime", "-1")) == pilot.get("_flight_raw", pilot["flight_s"])
                   for slot, pilot in pairs):
                for slot, pilot in pairs:
                    crew[slot["personageId"]] = pilot["name"]
            else:
                logger.warning("Flight times do not line up; "
                               "AI kills left unattributed")
        elif slots:
            logger.warning("%d AI slots for %d AI sorties; "
                           "AI kills left unattributed", len(slots), len(ai_pilots))
        return crew

    def mission_detail(self, career_id: str, mission_id: int) -> Optional[Dict[str, Any]]:
        """
        The full debrief for one mission: briefing, objectives, who flew, and
        every kill anyone scored, with altitudes and named opponents.

        Kept off the career payload not for cost — parsing all fifty missions
        takes 13 ms — but because it is only ever read one mission at a time.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            mission = db.query_one("SELECT * FROM mission WHERE id=?", (mission_id,))
            if mission is not None:
                mission = db._corrected([mission], "mission")[0]
            # Blob ticks are the game's compressed clock; corrected, they move
            # with the warps exactly as the DB events do.
            correction = db.correction_for(mission_id)
            warps = corrections.warps_of(correction) if correction else []
            if mission is None:
                return None
            result = MissionResult(mission["result"])

            # mission.result records how much of each aircraft and each pilot
            # was lost, as fractions. The career database keeps the same two
            # numbers for the player alone (planeHealth, health) and they
            # agree — mission 46: plane 0.540 against planeHealth 46, pilot
            # 0.098 against health 90 — so the blob is trusted for the rest of
            # the flight, who have no row of their own anywhere.
            harm = result.damages()

            # The flight log carries the same totals but with timings, and for
            # every pilot rather than only the human — AType 12 names them all.
            # The blob still supplies the figure, because it is always there;
            # the log supplies when the aircraft was hit.
            player_sortie = db.query_one(
                """SELECT date FROM sortie
                   WHERE missionId = ? AND isPlayer = 1 AND isDeleted = 0""",
                (mission_id,))
            flight_log = None
            if player_sortie:
                flight_log = self._shifted_log(db, mission_id, self.flightlogs.for_sortie(
                    player_sortie["date"][:10], player_sortie["date"][11:16]))

            manifest = {r["pilot_id"]: r for r in parse_pilots_list(mission["pilotsList"])}
            planes = {p["id"]: p for p in db.query("SELECT id, slot, config, tcode FROM plane")}
            flown = []
            for row in db._corrected(db.query(
                    """SELECT s.*, p.name, p.lastName, p.isPlayer, p.avatarPath,
                              p.country, p.rankId
                       FROM sortie s JOIN pilot p ON p.id = s.pilotId
                       WHERE s.missionId = ? AND s.isDeleted = 0
                       ORDER BY s.id""", (mission_id,)), "sortie"):
                kills = KillStats(row["killStats"])
                carried = manifest.get(row["pilotId"])
                airframe = planes.get(row["planeId"])
                plane_key = (PurePath(airframe["config"]).stem
                             if airframe and airframe["config"] else "")
                flown.append({
                    "airframe": _tail_code(airframe["tcode"], plane_key) if airframe else "",
                    "loadout": (self.ammo.describe(plane_key, carried["payload_id"])
                                if carried and plane_key else ""),
                    "fuel_pct": round(min(carried["fuel"], 1.0) * 100) if carried else None,
                    "assists": row["assistCount"] or 0,
                    "friendly_kills": row["fkill"] or 0,
                    "pilot_id": row["pilotId"],
                    "name": f"{row['name']} {row['lastName']}".strip(),
                    "is_player": bool(row["isPlayer"]),
                    "avatar": row["avatarPath"] or "",
                    "rank": self.locale.rank_name(row["country"], row["rankId"]),
                    "rank_id": row["rankId"],
                    "rank_key": f"{row['country']}{row['rankId']}",
                    "airborne": kills.airborne,
                    "ground_targets": kills.ground_targets,
                    "flight_time": _hm(row["flightTime"]),
                    "flight_s": row["flightTime"],
                    # The blob's totalFlightTime is the game's own clock; the
                    # positional AI check must compare against that, not the
                    # corrected value. Stripped again before the payload.
                    "_flight_raw": row.get("_flightTime_raw", row["flightTime"]) if isinstance(row, dict) else row["flightTime"],
                    "outcome": PLANE_OUTCOME.get(row["planeStatus"], "unknown"),
                    "wounded": row["status"] == 4,
                    # Filled in below, once the slots are paired to pilots.
                    "plane_damage": None,
                    "pilot_damage": None,
                })

            # Events name the actor by IL-2 account ("Arrow_1974") for the
            # human and by aircraft type ("F51D") for the AI, so every wingman's
            # kills used to read the same. Both are resolved to the pilot who
            # actually scored them.
            # _crew pairs the blob's formation slots against these rows in the
            # order the game wrote them, so the sort for display happens after.
            crew = self._crew(result, flown)

            # crew maps an actor id to a name; damages is keyed by the same
            # ids, so the two join without another pairing pass.
            by_name = {}
            for actor_id, name in crew.items():
                hurt = harm.get(actor_id)
                if hurt:
                    by_name[name] = hurt
            # The human is the exception. crew keys him by userId, because that
            # is what his kill events carry, but damages keys every row by
            # personageId — the same id for the AI, a different one for him.
            player_name = next((f["name"] for f in flown if f["is_player"]), "")
            for row in result.players():
                if row.get("personageNickname") and player_name:
                    hurt = harm.get(row.get("personageId", ""))
                    if hurt:
                        by_name[player_name] = hurt
            for pilot in flown:
                hurt = by_name.get(pilot["name"])
                if hurt:
                    pilot["plane_damage"] = round(hurt["plane"] * 100)
                    pilot["pilot_damage"] = round(hurt["pilot"] * 100)
                bursts = ((flight_log.damage_by_pilot or {}).get(pilot["name"], [])
                          if flight_log else [])
                start = player_sortie["date"][11:] if player_sortie else ""
                pilot["damage_log"] = [
                    {"time": _clock(start, b.at_s), "hits": b.hits,
                     "total": round(b.total * 100),
                     "attacker": self._attacker_name(b.attacker),
                     "self_inflicted": b.attacker == SELF_DAMAGE}
                    for b in bursts]

            flown.sort(key=lambda f: (not f["is_player"], -f["rank_id"]))
            player_user = next((uid for uid, name in crew.items()
                                if name == next((f["name"] for f in flown
                                                 if f["is_player"]), None)), "")

            start = mission["startTime"][11:] if mission["startTime"] else ""

            # A mission the player sits out is resolved by the game as a
            # fast-forward summary, and its result blob carries no actor the
            # crew map can match — every kill would read as "F-51D". The
            # `event` table has the pilot for each one, and the two agree on
            # target and order in all 66 missions here that record kills at
            # all, so the nth kill in the blob is the nth kill in the table.
            credited = [
                (normalise_object(row["target"] or ""), row["name"])
                for row in db.query(
                    """SELECT p.name || ' ' || p.lastName AS name, e.tpar1 AS target
                       FROM event e LEFT JOIN pilot p ON p.id = e.pilotId
                       WHERE e.type = 0 AND e.missionId = ? AND e.isDeleted = 0
                       ORDER BY e.id""", (mission_id,))]

            log = []
            for index, e in enumerate(result.events()):
                info = self.objects.describe(e["target"])
                actor = crew.get(e["actor_user"], "")
                if not actor and index < len(credited):
                    # Positional, but only where the two lists still agree on
                    # what was killed. If they ever drift, this yields nothing
                    # and the aircraft type is shown as before — a name that
                    # says little beats a name that is wrong.
                    target, name = credited[index]
                    if target == normalise_object(e["target"] or ""):
                        actor = name or ""
                if not actor:
                    by = self.objects.describe(e["actor"])
                    actor = by["name"] if by["named"] else e["actor"]
                air = bool(info["aircraft"] and not info["parked"])
                log.append({
                    "time": _clock(start, corrections.offset(warps, e["tick"]) if warps else e["tick"]),
                    "target": info["name"],
                    "named": info["named"],
                    "air": air,
                    "victim": e["victim"],
                    "altitude": e["altitude"] if air else None,
                    "actor": actor,
                    "by_player": e["actor_user"] == player_user,
                    # Where it happened, in world metres, for the map.
                    "x": e["x"], "z": e["z"],
                })

            # A strafing run flattens a row of crates in the same second and
            # writes one event each. Identical neighbours collapse to a count,
            # which took mission 46 from 110 lines to 90 without losing a kill.
            merged = []
            for entry in log:
                previous = merged[-1] if merged else None
                if (previous is not None
                        and previous["time"] == entry["time"]
                        and previous["target"] == entry["target"]
                        and previous["actor"] == entry["actor"]
                        and not previous["victim"] and not entry["victim"]):
                    previous["count"] += 1
                    continue
                entry["count"] = 1
                merged.append(entry)
            log = merged

            # The stored briefing is frozen in the language the mission was
            # generated in. The generator's own objective text is not, so it is
            # preferred wherever the game ships one, and the stored prose is
            # the fallback.
            briefing = (self.descriptions.objective(mission["type"])
                        or urllib.parse.unquote(mission["briefing"] or ""))
            return {
                "id": mission_id,
                "number": mission["missionNum"],
                "date": mission["date"],
                "start": mission["startTime"],
                "end": mission["endTime"],
                "type": self.locale.mission_type_name(mission["type"]),
                "briefing": briefing,
                "duration": _hm(correction["planned_s"] if correction else (result.duration_s or 0)),
                "objectives": result.objectives(),
                "coalitions": result.coalitions(),
                "obj_success": mission["objSuccess"],
                "obj_failure": mission["objFailure"],
                "flown": [{k: v for k, v in f.items() if not k.startswith("_")} for f in flown],
                "log": log,
                # The briefed route, take-off to landing, and the target the
                # mission was drawn against - both in world metres.
                "route": parse_route(mission["route"]),
                "target": self._target_point(db, mission["targetId"]),
            }

    @staticmethod
    def _target_point(db, target_id) -> Optional[Dict[str, Any]]:
        row = db.query_one("SELECT type, point, mTemplate FROM target WHERE id = ?",
                           (target_id,)) if target_id else None
        point = parse_point(row["point"]) if row else None
        if point is None:
            return None
        point["type"] = row["type"]
        return point

    def place_of(self, db, mission, features) -> str:
        """
        The nearest named place to a mission's target, for prose.

        A town is preferred to an airfield: "Sinuiju" reads as a place a
        squadron was sent to, "K-13 Suwon" reads as an address. The airfield
        is the fallback, stripped of its K-number for the same reason. A
        town within 15 km wins outright even when a field is nearer, because
        the field is usually the target *at* the town.

        Written for the citation and reused by the war diary, which is why
        it takes its features list rather than fetching one per mission -
        the overlay is a few thousand points and a diary asks 28 times.
        """
        pt = self._target_point(db, mission["targetId"]) if mission else None
        if pt is None:
            pts = parse_route(mission["route"]) if mission else []
            pt = next((p for p in pts if p["type"] == WAYPOINT_TARGET), None)
        if pt is None or not features:
            return ""
        towns = [f for f in features if f["kind"] in ("city", "town") and f["name"]]
        fields = [f for f in features if f["kind"] == "airfield" and f["name"]]

        def dist(f):
            return ((f["x"] - pt["x"]) ** 2 + (f["z"] - pt["z"]) ** 2) ** 0.5
        near_town = min(towns, key=dist) if towns else None
        near_field = min(fields, key=dist) if fields else None
        if near_town and (near_field is None or dist(near_town) <= 15000
                          or dist(near_town) <= dist(near_field)):
            return near_town["name"]
        if near_field:
            return re.sub(r"^K-\d+\s+", "", near_field["name"])
        return near_town["name"] if near_town else ""

    def career_map(self, career_id: str,
                   pilot_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Everything the operations map draws: each sortie's briefed route,
        every air victory with its position, and the bases flown from.

        For the whole squadron by default; with a pilot, only his sorties and
        his kills. Kills are attributed the way the mission detail does it
        (result blob actor, else the event table in order), reduced to the
        one question the map asks - whose dot is this.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career = db.career()
            if career is None:
                return None
            missions = {m["id"]: m for m in db.missions()}
            sorties = db.sorties(pilot_id)
            names = {p["id"]: f"{p['name']} {p['lastName']}".strip() for p in db.pilots(True)}
            flown_ids = {s["missionId"] for s in sorties}
            # What each mission destroyed - the squadron's total, or the one
            # pilot's when the map is his - so the target ring can carry it.
            air_by_mission: Counter = Counter()
            ground_by_mission: Counter = Counter()
            for s in sorties:
                ks = KillStats(s["killStats"])
                air_by_mission[s["missionId"]] += ks.airborne
                ground_by_mission[s["missionId"]] += ks.ground_targets

            routes = []
            bases: Dict[str, Dict[str, Any]] = {}
            for mid in sorted(flown_ids):
                m = missions.get(mid)
                if m is None:
                    continue
                pts = parse_route(m["route"])
                if not pts:
                    continue
                routes.append({
                    "mission_id": mid, "number": m["missionNum"], "date": m["date"],
                    "type": self.locale.mission_type_name(m["type"]),
                    "points": [[round(p["x"]), round(p["z"]), p["type"]] for p in pts],
                    "target": self._target_point(db, m["targetId"]),
                    "air": air_by_mission.get(mid, 0),
                    "ground": ground_by_mission.get(mid, 0),
                })
                for p in pts:
                    if p["type"] in (WAYPOINT_TAKEOFF, WAYPOINT_LANDING):
                        key = f"{round(p['x'] / 500)}:{round(p['z'] / 500)}"
                        base = bases.setdefault(key, {"x": p["x"], "z": p["z"],
                                                      "first": m["date"], "last": m["date"],
                                                      "sorties": 0})
                        base["last"] = max(base["last"], m["date"])
                        base["sorties"] += 1

            # Air victories with positions. The event table names the pilot
            # for every kill in order; the result blob has the position for
            # the same kills in the same order (66 of 66 missions agree).
            victories = []
            for mid in sorted(flown_ids):
                m = missions.get(mid)
                if m is None:
                    continue
                credited = db.query(
                    """SELECT pilotId, tpar1 AS target FROM event
                       WHERE type = 0 AND missionId = ? AND isDeleted = 0 ORDER BY id""",
                    (mid,))
                events = MissionResult(m["result"]).events()
                for index, e in enumerate(events):
                    info = self.objects.describe(e["target"])
                    if not (info["aircraft"] and not info["parked"]):
                        continue
                    pid = None
                    if index < len(credited) and (normalise_object(credited[index]["target"] or "")
                                                  == normalise_object(e["target"] or "")):
                        pid = credited[index]["pilotId"]
                    if pilot_id is not None and pid != pilot_id:
                        continue
                    victories.append({
                        "mission_id": mid, "number": m["missionNum"], "date": m["date"],
                        "x": e["x"], "z": e["z"], "alt": e["altitude"],
                        "target": info["name"], "victim": e["victim"],
                        "pilot": names.get(pid, "") if pid is not None else "",
                        "pilot_id": pid,
                    })

            # Our own losses, where they fell.
            by_name = {v: k for k, v in names.items()}
            losses = []
            for mid in sorted(flown_ids):
                m = missions.get(mid)
                if m is None:
                    continue
                seen_loss = set()
                for e in MissionResult(m["result"]).losses():
                    pid = by_name.get(e["pilot"])
                    # Only the squadron's own men (the blob also lists other
                    # friendly aircraft in the area), once each per mission.
                    if pid is None or pid in seen_loss or (pilot_id is not None and pid != pilot_id):
                        continue
                    seen_loss.add(pid)
                    losses.append({
                        "mission_id": mid, "number": m["missionNum"], "date": m["date"],
                        "x": e["x"], "z": e["z"], "alt": e["altitude"],
                        "pilot": e["pilot"], "pilot_id": pid,
                        "plane": self.objects.describe(e["plane"])["name"],
                    })

            return {
                "routes": routes,
                "victories": victories,
                "losses": losses,
                "bases": sorted(bases.values(), key=lambda b: b["first"]),
                "pilot_id": pilot_id,
            }

    def _day_sortie(self, db, pilot_id: int, earned: str, sorties, missions):
        """
        The sortie an award of that day was for - the one with the most in
        it - with its mission and its airborne kills by aircraft name, or
        None when he did not fly that day.
        """
        day = [s for s in sorties if missions[s["missionId"]]["date"] == earned]
        if not day:
            return None
        best = max(day, key=lambda s: (KillStats(s["killStats"]).airborne, KillStats(s["killStats"]).ground_targets))
        m = missions[best["missionId"]]
        kills: Dict[str, int] = {}
        for e in db.query("SELECT tpar1 AS target FROM event WHERE type=0 AND isDeleted=0 AND pilotId=? AND missionId=? ORDER BY id",
                          (pilot_id, m["id"])):
            info = self.objects.describe(e["target"])
            if info["aircraft"] and not info["parked"]:
                kills[info["name"]] = kills.get(info["name"], 0) + 1
        return best, m, kills

    def pilot_basics(self, career_id: str, pilot_id: int) -> Optional[Dict[str, Any]]:
        """
        What a personnel file needs that the service record does not carry:
        the name in its parts, the unit code, the biography and birth date
        (the player's only), and every award row he has been presented
        with, repeat awardings of one id included, oldest first.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            pilot = db.pilot(pilot_id)
            if pilot is None:
                return None
            squadron = db.query_one("SELECT configId FROM squadron WHERE id=?", (pilot["squadronId"],))
            desc = dict(urllib.parse.parse_qsl(urllib.parse.unquote(pilot["description"] or "")))
            awards = [{"type": r["type"], "earned": r["earnedDate"] or "",
                       "received": r["receivedDate"] or r["earnedDate"] or "",
                       "rank_id": r["pilotRank"] if r["pilotRank"] is not None else pilot["rankId"],
                       "name": self.award_name(r["type"])}
                      for r in db.awards(pilot_id) if r["category"] != 1 and not r["isPending"]]
            awards.sort(key=lambda a: (a["earned"], a["type"]))
            return {"first_name": pilot["name"] or "", "last_name": pilot["lastName"] or "",
                    "country": int(pilot["country"]), "rank_id": pilot["rankId"],
                    "lead_level": pilot["leadLevel"],
                    "unit_code": squadron["configId"] if squadron else 0,
                    "bio_id": desc.get("biographyId", ""), "birth_date": desc.get("birthDate", ""),
                    "awards": awards}

    def prc_merits(self, career_id: str, pilot_id: int) -> Optional[Dict[str, Any]]:
        """
        The facts behind a Chinese pilot's merit booklet: every merit and
        Combat Hero Medal he holds, each with the sortie of its day (kills
        by aircraft name and the nearest place, both in this aggregator's
        language), and the post he held then. prc_file turns them into the
        documents; the zh aggregator supplies the Chinese words, the
        reader's one the tooltips.
        """
        from .. import prc_file
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            pilot = db.pilot(pilot_id)
            if pilot is None or int(pilot["country"]) != 502:
                return None
            missions = {m["id"]: m for m in db.missions()}
            sorties = [s for s in db.sorties(pilot_id) if s["missionId"] in missions]
            features = self.overlay.features()
            squadron = db.query_one("SELECT configId FROM squadron WHERE id=?", (pilot["squadronId"],))
            desc = dict(urllib.parse.parse_qsl(urllib.parse.unquote(pilot["description"] or "")))
            entries = []
            for row in db.awards(pilot_id):
                kind = prc_file.kind_of(row["type"])
                if kind is None or row["isPending"]:
                    continue
                earned = row["earnedDate"] or ""
                entry = {"type": row["type"], "kind": kind, "earned": earned,
                         "received": row["receivedDate"] or earned,
                         "rank_id": row["pilotRank"] if row["pilotRank"] is not None else pilot["rankId"],
                         "name": self.award_name(row["type"]),
                         "rank_name": self.locale.rank_name(502, row["pilotRank"] if row["pilotRank"] is not None
                                                            else pilot["rankId"]),
                         "kills": {}, "place": "", "hits": 0, "outcome": "ok", "flown": False}
                day = self._day_sortie(db, pilot_id, earned, sorties, missions)
                if day:
                    best, m, kills = day
                    flight = self.flightlogs.for_sortie(best["date"][:10], best["date"][11:16]) if pilot["isPlayer"] else None
                    entry.update({
                        "flown": True, "kills": kills, "place": self.place_of(db, m, features),
                        "hits": sum(b.hits for b in flight.damage) if flight and flight.damage else 0,
                        "outcome": "bailed" if flight and flight.ejected else ("ok" if best["status"] == 0 else "missing"),
                    })
                entries.append(entry)
            entries.sort(key=lambda e: (e["earned"], e["type"]))
            return {
                "name": f"{pilot['name']} {pilot['lastName']}".strip(),
                "first_name": pilot["name"] or "", "last_name": pilot["lastName"] or "",
                "rank_id": pilot["rankId"], "unit_code": squadron["configId"] if squadron else 0,
                "bio_id": desc.get("biographyId", ""), "birth_date": desc.get("birthDate", ""),
                "entries": entries,
            }

    def citation(self, career_id: str, pilot_id: int, award_id: int,
                 earned: str) -> Optional[Dict[str, Any]]:
        """
        The citation for one of a pilot's decorations: the facts of the day
        it was earned (the sortie with the best result that day - kills by
        name, ground targets, hits taken, the outcome, the flight's size,
        the nearest town) or of the period up to it, composed in the
        language's own citation words. None when the award has no citation.
        """
        if award_id not in citations.FAMILY:
            return None
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            pilot = db.pilot(pilot_id)
            if pilot is None:
                return None
            texts = citations.strings(self.lang)
            country = int(pilot["country"])
            preview = os.environ.get("KOREA_PREVIEW_RACK", "")
            if preview in ("navy", "usmc"):
                country = 602 if preview == "navy" else 603
            row = db.query_one("SELECT pilotRank, receivedDate FROM award WHERE pilotId=? AND type=? AND earnedDate=? ORDER BY id DESC",
                               (pilot_id, award_id, earned))
            rank_id = row["pilotRank"] if row and row["pilotRank"] is not None else pilot["rankId"]
            received = (row["receivedDate"] if row and row["receivedDate"] else earned) or earned
            missions = {m["id"]: m for m in db.missions()}
            names = {p["id"]: f"{p['name']} {p['lastName']}".strip() for p in db.pilots(True)}
            planes = {p["id"]: p for p in db.query("SELECT id, config FROM plane")}
            sorties = [s for s in db.sorties(pilot_id) if s["missionId"] in missions and missions[s["missionId"]]["date"] <= earned]
            unit_sorties = [s for s in db.sorties() if s["missionId"] in missions and missions[s["missionId"]]["date"] <= earned]

            def plane_name(s) -> str:
                p = planes.get(s["planeId"]) if s else None
                key = PurePath(p["config"]).stem if p and p["config"] else ""
                return self.objects.describe(key)["name"] if key else ""

            features = self.overlay.features()
            def place_of(m) -> str:
                return self.place_of(db, m, features)

            # For the Soviet form: what he held before this award, whether
            # he was wounded up to then, and who commands the squadron.
            held_before = [r["type"] for r in db.awards(pilot_id, include_removed=True)
                           if r["category"] != 1 and (r["earnedDate"] or "") < earned and r["type"] != award_id]
            wound = db.query_one("SELECT date FROM event WHERE type=5 AND pilotId=? AND isDeleted=0 AND date<=? ORDER BY date DESC",
                                 (pilot_id, earned + " 23:59:59"))
            commander = db.query_one("SELECT name, lastName FROM pilot WHERE isPlayer=1 AND isDeleted=0")
            # The player's description carries his biography and birth date
            # ("biographyId=601006&birthDate=1920.02.23"); the AI have none.
            desc = dict(urllib.parse.parse_qsl(urllib.parse.unquote(pilot["description"] or "")))
            facts: Dict[str, Any] = {
                "country": country,
                "rank": self.locale.rank_name(country, rank_id),
                "name": f"{pilot['name']} {pilot['lastName']}".strip(),
                "unit": meta.squadron_name,
                "bio_id": desc.get("biographyId", ""), "birth_date": desc.get("birthDate", ""),
                "award_name_tr": self.award_name(award_id),
                "rank_tr": self.locale.rank_name(country, rank_id),
                "held_names": {a: self.award_name(a) for a in held_before},
                "held_before": held_before,
                "wound_date": (wound["date"] or "")[:10] if wound else "",
                "commander": f"{commander['name']} {commander['lastName']}".strip() if commander else "",
                "date": citations.format_date(texts, earned), "earned_raw": earned,
                "aircraft": plane_name(sorties[-1]) if sorties else "",
                "has_sortie": False, "kills": {}, "ground_n": 0, "hits": 0, "outcome": "ok",
            }
            if self.lang == "rus":
                # The наградной лист is a Russian form: names in Cyrillic, from
                # the game's own name table, and for a Soviet pilot "Фамилия,
                # имя и отчество" as the form asks. The tooltips romanise them.
                from ..native_names import native
                from ..ussr_file import patronymic
                first, last = native(pilot["name"], self.resolver, "rus"), native(pilot["lastName"], self.resolver, "rus")
                if first and last:
                    father = patronymic(facts["bio_id"], pilot["name"] + pilot["lastName"]) if country == 501 else ""
                    facts["name"] = f"{first} {last}"
                    facts["name_ru"] = " ".join(x for x in (last, first, father) if x)
                if country == 501:
                    # his post and regiment as a Soviet form types them
                    from ..ussr_file import post, unit
                    squadron = db.query_one("SELECT configId FROM squadron WHERE id=?", (pilot["squadronId"],))
                    regiment = unit(squadron["configId"] if squadron else 0)["short"]
                    facts["post_ru"] = f"{post(rank_id)[0]}, {regiment}"
                if commander:
                    c_first = native(commander["name"], self.resolver, "rus")
                    c_last = native(commander["lastName"], self.resolver, "rus")
                    if c_first and c_last:
                        facts["commander"] = f"{c_first} {c_last}"
            day = self._day_sortie(db, pilot_id, earned, sorties, missions)
            if day:
                best, m, kills = day
                flight = None
                if pilot["isPlayer"]:
                    flight = self.flightlogs.for_sortie(best["date"][:10], best["date"][11:16])
                # A flight-mate lost on the same mission, by name.
                lost_mates = [e["pilot"] for e in MissionResult(m["result"]).losses()
                              if e["pilot"] != facts["name"] and e["pilot"] in names.values()]
                facts.update({
                    "seed": m["id"], "wingman": lost_mates[0] if lost_mates else "",
                    "has_sortie": True, "leader": bool(pilot["isPlayer"]),
                    "flight": sum(1 for s in unit_sorties if s["missionId"] == m["id"]),
                    "aircraft": plane_name(best), "target": self.locale.mission_type_name(m["type"]),
                    "place": place_of(m), "kills": kills,
                    "ground_n": KillStats(best["killStats"]).ground_targets,
                    "hits": sum(b.hits for b in flight.damage) if flight and flight.damage else 0,
                    "outcome": "bailed" if flight and flight.ejected else ("ok" if best["status"] == 0 else "missing"),
                })
            elif sorties:
                facts["place"] = place_of(missions[sorties[-1]["missionId"]])
            # The period up to the day.
            if sorties:
                ks = [KillStats(s["killStats"]) for s in sorties]
                facts.setdefault("seed", sorties[-1]["missionId"])
                facts.update({
                    "period_from": citations.format_date(texts, missions[sorties[0]["missionId"]]["date"]),
                    "period_from_raw": missions[sorties[0]["missionId"]]["date"],
                    "period_to": facts["date"], "missions": len(sorties),
                    "hours": f"{sum(float(s['flightTime'] or 0) for s in sorties) / 3600:.1f}".replace(".", texts.get("decimal", ".")),
                    "air_total": sum(k.airborne for k in ks), "ground_total": sum(k.ground_targets for k in ks),
                })
            if unit_sorties:
                uk = [KillStats(s["killStats"]) for s in unit_sorties]
                facts.update({
                    "sorties_unit": len(unit_sorties),
                    "period_from": facts.get("period_from") or citations.format_date(texts, missions[unit_sorties[0]["missionId"]]["date"]),
                    "period_from_raw": facts.get("period_from_raw") or missions[unit_sorties[0]["missionId"]]["date"],
                    "period_to": facts["date"],
                })
                if citations.FAMILY[award_id][2] == "unit":
                    facts["air_total"] = sum(k.airborne for k in uk)
                    facts["ground_total"] = sum(k.ground_targets for k in uk)
            out = citations.compose(self.lang, award_id, facts)
            if out is not None:
                out["certificate"] = citations.certificate(self.lang, award_id, facts, received, out["paragraphs"])
                out["icon"] = f"/api/icon/award/{award_id}"
                out["award_name"] = self.award_name(award_id)
            return out

    def logbook(self, career_id: str, pilot_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        The pilot's individual flight record, month by month: every sortie
        with its date, aircraft and tail number, mission, take-off and
        landing (the player's, from the flight log; the AI have none), the
        hours - the corrected ones when the career is - split day/night by
        the clock, landings, and a remarks line built from what the sortie
        did to him and he to the enemy. Totals per month and to date.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career = db.career()
            pilot = db.pilot(pilot_id) if pilot_id is not None else db.player()
            if career is None or pilot is None:
                return None
            missions = {m["id"]: m for m in db.missions()}
            planes = {p["id"]: p for p in db.query("SELECT id, slot, config, tcode FROM plane")}
            fields = [f for f in self.overlay.features() if f["kind"] == "airfield" and f["name"]]

            def station(m) -> str:
                pts = parse_route(m["route"])
                if not pts or not fields:
                    return ""
                p = pts[0]
                near = min(fields, key=lambda f: (f["x"] - p["x"]) ** 2 + (f["z"] - p["z"]) ** 2)
                return near["name"]

            kills_by_sortie: Dict[int, List[str]] = {}
            for e in db.query("""SELECT s.id AS sid, e.tpar1 AS target FROM event e
                                 JOIN sortie s ON s.missionId = e.missionId AND s.pilotId = e.pilotId
                                 WHERE e.type = 0 AND e.isDeleted = 0 AND e.pilotId = ? ORDER BY e.id""",
                              (pilot["id"],)):
                info = self.objects.describe(e["target"])
                if info["aircraft"] and not info["parked"]:
                    kills_by_sortie.setdefault(e["sid"], []).append(info["name"])

            months: Dict[str, Dict[str, Any]] = {}
            to_date = {"hours": 0.0, "day": 0.0, "night": 0.0, "sorties": 0, "landings": 0, "air": 0, "ground": 0}
            for s in db.sorties(pilot["id"]):
                m = missions.get(s["missionId"])
                if m is None:
                    continue
                key = m["date"][:7]
                month = months.setdefault(key, {"month": key, "station": station(m), "rows": [],
                                                "totals": {"hours": 0.0, "day": 0.0, "night": 0.0, "sorties": 0,
                                                           "landings": 0, "air": 0, "ground": 0}})
                plane = planes.get(s["planeId"])
                plane_key = PurePath(plane["config"]).stem if plane and plane["config"] else ""
                flight = None
                if pilot["isPlayer"]:
                    flight = self._shifted_log(db, m["id"], self.flightlogs.for_sortie(
                        s["date"][:10], s["date"][11:16]))
                start = s["date"][11:]
                secs = float(s["flightTime"] or 0)
                hours = secs / 3600.0
                # Day and night by the clock: the hours outside 05:30-19:30.
                t0 = _seconds(start) + (flight.takeoff_s if flight and flight.takeoff_s is not None else 0)
                t1 = t0 + secs
                night = max(0.0, min(t1, 5.5 * 3600) - t0) + max(0.0, t1 - max(t0, 19.5 * 3600))
                night_h = min(hours, night / 3600.0)
                ks = KillStats(s["killStats"])
                air, ground = ks.airborne, ks.ground_targets
                returned = s["status"] == 0
                # The remarks are composed on the page in the form's language:
                # the kills by name, the ground count, hits taken, the outcome.
                row = {
                    "date": m["date"], "day": int(m["date"][8:10]),
                    "aircraft": self.objects.describe(plane_key)["name"] if plane_key else "",
                    "code": _tail_code(plane["tcode"], plane_key) if plane else "",
                    "mission": self.locale.mission_type_name(m["type"]), "number": m["missionNum"],
                    "symbol": MISSION_SYMBOL.get(m["type"], ""),
                    "takeoff": _clock(start, flight.takeoff_s)[:5] if flight and flight.takeoff_s is not None else "",
                    "landing": _landing_clock(start, flight, secs)[:5],
                    "hours": round(hours, 1), "night_h": round(night_h, 1), "day_h": round(hours - night_h, 1),
                    "landings": 1 if returned else 0, "air": air, "ground": ground,
                    "remarks": kills_by_sortie.get(s["id"], []),
                    "hits": sum(b.hits for b in flight.damage) if flight and flight.damage else 0,
                    "outcome": "bailed" if flight and flight.ejected else ("ok" if returned else "missing"),
                    "rank": self.locale.rank_name(pilot["country"], s["rankId"]),
                }
                if int(pilot["country"]) in (602, 603):
                    row["char"] = navy_flight_code(m["type"], night_h / hours if hours else 0)
                    row["bureau"] = bureau_number(plane["id"], plane_key, career_id) if plane else ""
                month["rows"].append(row)
                for tot in (month["totals"], to_date):
                    tot["hours"] += hours; tot["day"] += hours - night_h; tot["night"] += night_h
                    tot["sorties"] += 1; tot["landings"] += row["landings"]; tot["air"] += air; tot["ground"] += ground
                month["to_date"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in to_date.items()}
            for month in months.values():
                month["totals"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in month["totals"].items()}

            country = int(pilot["country"])
            return {
                "career_id": career_id,
                "pilot": {"id": pilot["id"], "name": f"{pilot['name']} {pilot['lastName']}".strip(),
                          "last": pilot["lastName"], "first": pilot["name"],
                          "rank": self.locale.rank_name(country, pilot["rankId"]), "country": country,
                          "is_player": bool(pilot["isPlayer"])},
                "organization": meta.squadron_name,
                "aircraft": self.objects.describe(PurePath(planes[next(iter(planes))]["config"]).stem)["name"] if planes else "",
                # A Chinese pilot flew Soviet aeroplanes under Soviet
                # advisers and keeps the Soviet book, as his award papers
                # already use the Soviet sheet. Without 502 here he was
                # handed an AF Form 5.
                "form": {601: "usaf", 602: "navy", 603: "navy", 501: "sov", 502: "sov",
                         503: "dprk"}.get(country, "usaf"),
                "months": [months[k] for k in sorted(months)],
                "as_of": career["currentDate"],
                "corrected": getattr(db, "_corr", None) is not None,
            }

    def combat_report(self, career_id: str) -> Optional[Dict[str, Any]]:
        """Career gunnery totals and one factual report per player sortie."""
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            career, player = db.career(), db.player()
            if career is None or player is None:
                return None
            sorties = db.sorties(player["id"])
            reports = self._debriefings(db, sorties,
                                        db.events(player["id"], types=[0]),
                                        with_flight_log=True)
            detailed = [r for r in reports if r["gunnery"]["available"]]
            complete = [r for r in detailed if r["gunnery"]["complete"]]

            def total(key: str) -> int:
                return sum(int(r["gunnery"].get(key) or 0) for r in complete)

            fired = total("gun_fired")
            # The rate needs the same set in numerator and denominator.  A
            # truncated log can retain impacts but no mission-end ammunition;
            # those impacts remain on its report but not in the career rate.
            impacts = sum(int(r["gunnery"].get("gun_hits") or 0)
                          for r in complete)
            by_aircraft: Dict[str, Dict[str, Any]] = {}
            for report in complete:
                name = report.get("aircraft") or report.get("airframe") or "—"
                row = by_aircraft.setdefault(name, {
                    "aircraft": name, "missions": 0, "gun_fired": 0,
                    "gun_hits": 0, "gun_rate": None})
                row["missions"] += 1
                row["gun_fired"] += int(report["gunnery"].get("gun_fired") or 0)
                row["gun_hits"] += int(report["gunnery"].get("gun_hits") or 0)
            for row in by_aircraft.values():
                if row["gun_fired"]:
                    row["gun_rate"] = round(
                        100.0 * row["gun_hits"] / row["gun_fired"], 1)

            return {
                "career_id": career_id,
                "pilot": {
                    "id": player["id"],
                    "name": f"{player['name']} {player['lastName']}".strip(),
                    "first_name": player["name"] or "",
                    "last_name": player["lastName"] or "",
                    "rank": self.locale.rank_name(player["country"],
                                                   player["rankId"]),
                    "country": player["country"],
                },
                "squadron": meta.squadron_name,
                "as_of": (career["currentDate"] or "")[:10],
                "seal": COUNTRY_SEALS.get(player["country"], ""),
                "summary": {
                    "missions": len(reports),
                    "covered": len(detailed),
                    "complete": len(complete),
                    "gun_fired": fired,
                    "gun_hits": impacts,
                    "gun_rate": round(100.0 * impacts / fired, 1) if fired else None,
                    "bombs_expended": total("bombs_expended"),
                    "rockets_expended": total("rockets_expended"),
                    "rocket_impacts": sum(
                        int(r["gunnery"].get("rocket_impacts") or 0)
                        for r in detailed),
                    "airborne": sum(int(r.get("airborne") or 0) for r in reports),
                    "ground_targets": sum(
                        int(r.get("ground_targets") or 0) for r in reports),
                    "by_aircraft": sorted(by_aircraft.values(),
                                          key=lambda r: (-r["missions"], r["aircraft"])),
                },
                "reports": reports,
            }

    def mission_track(self, career_id: str, mission_id: int) -> Optional[Dict[str, Any]]:
        """
        The player's flown track for one mission, from the flight log: the
        fixes as flown segments, the warps as jumps between them, and the
        moments worth a mark on it - take-off, landing, every burst of damage
        taken, the bail-out - placed where the aircraft was at the time. The
        clock is the mission's, re-timed with the warps when the career is
        corrected, as the debrief's own times are. Our losses ride along, so
        the mission map can show them without a log.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None
        with self._open(meta) as db:
            mission = db.query_one("SELECT id, date, startTime, route, result FROM mission WHERE id=?",
                                   (mission_id,))
            player = db.player()
            if mission is None or player is None:
                return None
            names = {f"{p['name']} {p['lastName']}".strip() for p in db.pilots(True)}
            losses, seen_loss = [], set()
            for e in MissionResult(mission["result"]).losses():
                if e["pilot"] not in names or e["pilot"] in seen_loss:
                    continue
                seen_loss.add(e["pilot"])
                losses.append({"x": e["x"], "z": e["z"], "alt": e["altitude"], "pilot": e["pilot"],
                               "plane": self.objects.describe(e["plane"])["name"]})
            out: Dict[str, Any] = {"mission_id": mission_id, "segments": [], "marks": [], "losses": losses,
                                   "front": self.frontlines.for_date(mission["date"] or "")}
            sortie = db.query_one("SELECT date FROM sortie WHERE missionId=? AND pilotId=? AND isDeleted=0",
                                  (mission_id, player["id"]))
            log = self.flightlogs.for_sortie(sortie["date"][:10], sortie["date"][11:16]) if sortie else None
            if log is None:
                return out
            fixes = corrections.player_track(log.path)
            if len(fixes) < 2:
                return out
            correction = db.correction_for(mission_id)
            warps = corrections.warps_of(correction) if correction else []
            start = (mission["startTime"] or "")[11:]
            clock = lambda t: _clock(start, corrections.offset(warps, t) if warps else t)   # noqa: E731

            jumps = {j[0] for j in corrections.find_warps([(t, x, z) for t, x, z, _ in fixes],
                                                          parse_route(mission["route"]))}
            point = lambda f: [round(f[1]), round(f[2]), clock(f[0]), round(f[3])]           # noqa: E731
            segments: List[Dict[str, Any]] = []
            current: List[Tuple[float, float, float, float]] = [fixes[0]]
            for a, b in zip(fixes, fixes[1:]):
                if a[0] in jumps:
                    segments.append({"warp": False, "points": _thin(current, point)})
                    segments.append({"warp": True, "points": [point(a), point(b)],
                                     "km": round(math.hypot(b[1] - a[1], b[2] - a[2]) / 1000, 1)})
                    current = [b]
                else:
                    current.append(b)
            segments.append({"warp": False, "points": _thin(current, point)})
            out["segments"] = [s for s in segments if len(s["points"]) >= 2]

            marks: List[Dict[str, Any]] = []
            def mark(kind: str, t: Optional[float], **extra) -> None:
                if t is None:
                    return
                x, z, alt = _pos_at(fixes, t)
                marks.append(dict(kind=kind, x=round(x), z=round(z), alt=round(alt), clock=clock(t), **extra))
            mark("takeoff", log.takeoff_s)
            mark("landing", log.landing_s)
            for burst in log.damage:
                mark("hit", burst.at_s, hits=burst.hits,
                     attacker=("" if burst.attacker in ("", "*self*") else self.objects.describe(burst.attacker)["name"]),
                     own=burst.attacker == "*self*", amount=round(burst.amount * 100))
            if log.ejected:
                mark("bailout", log.ejected_s if log.ejected_s is not None else fixes[-1][0])
            out["marks"] = marks
            return out

    # -- detail page -------------------------------------------------------

    def career_detail(self, career_id: str,
                      pilot_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        The service record for one pilot, defaulting to the player.

        The player is not a special case — he is simply the pilot the page
        opens on — so every panel is built from the same code whoever is
        being shown. The one thing an AI pilot cannot have is the take-off
        and landing line: the flight log only marks the human's aircraft
        (ISPL:1), so those fields come back empty rather than invented.
        """
        meta = self._career_files().get(career_id)
        if meta is None:
            return None

        with self._open(meta) as db:
            career, squad = db.career(), db.squadron()
            subject = db.pilot(pilot_id) if pilot_id is not None else db.player()
            if career is None or subject is None:
                return None
            player = subject
            pid = player["id"]
            is_player = bool(player["isPlayer"])

            awards_by_pilot: Dict[int, List] = {}
            retired_citations: List = []
            for row in db.awards(include_removed=True):
                if row["isDeleted"]:
                    if row["category"] == 2:
                        retired_citations.append(row)
                    continue
                awards_by_pilot.setdefault(row["pilotId"], []).append(row)

            current_id = career["playerId"]
            roster = [self._pilot_row(p, awards_by_pilot, current_id)
                      for p in db.pilots()]
            roster.sort(key=lambda p: (not p["is_player"], -p["rank_id"],
                                       -p["sorties"]))

            sorties = db.sorties(pid)
            kill_events = db.events(pid, types=[0])
            player_awards = db.awards(pid, include_removed=True)
            groups = self._promotions_and_awards(player_awards, player['country'])
            described = _pilot_description(player["description"])
            # The selectable biography is the only surviving evidence of the
            # pilot's service before Korea.  These medals belong on what he
            # wears, but are not Korean-career award events and therefore do
            # not enter the dated awards list above.  A player who wrote his
            # own biography in the Career Helper chose them himself.
            own = custombio.load(Path(meta.path), pid)
            if own and own["wwii_awards"] is not None:
                prior_ids = wwii_awards.chosen(own["wwii_awards"], player["country"])
            else:
                prior_ids = wwii_awards.for_career_description(
                    player["description"], player["country"])
            prior_awards = [
                {"type": award_id, "name": self.award_name(award_id),
                 "pending": False, "history": []}
                for award_id in prior_ids
            ]

            # The rank on the earliest sortie is where the career began.
            starting_rank_id = sorties[0]["rankId"] if sorties else player["rankId"]

            # The type the player actually flies, for incidences where the
            # event text is unusable.
            plane_row = db.query_one(
                "SELECT config FROM plane WHERE squadronId=? LIMIT 1",
                (player["squadronId"],))
            aircraft_flown = ""
            if plane_row and plane_row["config"]:
                stem = Path(plane_row["config"]).stem
                described = self.objects.describe(stem)
                aircraft_flown = described["name"] if described["named"] else stem

            # Built once: the victory roll is derived from the same enriched
            # logs the debriefings render, rather than re-reading the results.
            debriefings = self._debriefings(db, sorties, kill_events,
                                            with_flight_log=is_player)
            victories = self._victory_roll(debriefings)

            return {
                "id": career_id,
                "player_id": player["id"],
                "squadron": meta.squadron_name,
                "start_date": career["startDate"],
                "current_date": career["currentDate"],
                "award_points": squad["awardPoints"] if squad else 0,
                "efficiency": squad["efficiency"] if squad else None,
                # Operations the squadron saw through, and how many it won.
                # A running one is not recorded until it ends, and an
                # operation it never flew still counts - see operations.py.
                "operations": Operations(
                    squad["operations"] if squad else None).as_dict(),
                # Sorties the game finished but failed to save. Reported so
                # the reader blames the right thing - see _sortie_loss.
                "sortie_loss": self._sortie_loss(db),
                # Career screens the mod replaces that a game update has
                # changed since (uioverrides.py). Checked once per run.
                "ui_stale": self._ui_stale(),
                # squadrons.xaml keys emblems by the squadron's configId
                "squadron_key": str(squad["configId"]) if squad else "",
                # What the squadron actually flies, for the header artwork.
                # squadrons.cfg also has this, but per *period* — twelve
                # squadrons re-equip mid-war — so the aircraft on strength now
                # is the honest answer and it follows a conversion for free.
                "plane": self._squadron_plane(db),
                "classification": COUNTRY_STAMPS.get(player["country"], "eng"),
                "seal": COUNTRY_SEALS.get(player["country"], "usa"),
                "player": self._pilot_row(player, awards_by_pilot),
                "combat": self._combat_results(KillStats(player["killStats"])),
                "air_kills_by_type": self._air_kills_by_type(kill_events),
                "missions_flown": self._missions_flown(sorties, {m["id"]: m for m in db.missions()}),
                "promotions": groups["promotions"],
                "awards": groups["awards"],
                "ribbon_rack": self._ribbon_rack(
                    groups["awards"] + prior_awards, awards_by_pilot.get(-1, []),
                    player["country"], player["rankId"]),
                "corrections_applied": corrections.is_applied(corrections.load(Path(meta.path).stem)),
                "incidences": self._incidences(db.events(pid), aircraft_flown),
                "debriefings": debriefings,
                "victories": victories,
                "performance": self._performance(db, player, victories),
                "subject_id": pid,
                "is_player": is_player,
                "progression": {
                    "starting_rank": self.locale.rank_name(player["country"],
                                                           starting_rank_id),
                    "current_rank": self.locale.rank_name(player["country"],
                                                          player["rankId"]),
                    "promotions": len(groups["promotions"]),
                    "awards": len(groups["awards"]),
                },
                "roster": roster,
                "squadron_totals": self._combat_results(
                    KillStats(squad["killStats"]))["headline"] if squad else [],
                "pending_total": sum(p["awards_pending"] for p in roster),
                # Decorations to the unit itself, from awards flagged
                # IsSquadron=1: the engine files them under pilotId -1 with
                # category 2, so they fall out of the same grouping the roster
                # uses. Never pending — the engine grants them outright.
                "progress": self._progress(
                    db, player, career, squad,
                    {r["type"] for r in player_awards}),
                "citations": self._citation_ladders(
                    [r for r in awards_by_pilot.get(-1, []) if r["category"] == 2],
                    retired_citations),
                "aircraft": self._aircraft(db, career, squad, Path(meta.path)),
            }
