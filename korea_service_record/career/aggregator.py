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

import json
import logging
import re
import urllib.parse
from collections import Counter, OrderedDict
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

from ..assets import AssetResolver
from ..flightlog import SELF as SELF_DAMAGE, FlightLogIndex
from ..gamedata import (COUNTRY_FLAGS, COUNTRY_NAMES, COUNTRY_SEALS, COUNTRY_STAMPS, AwardsConfig,
                        LocaleStrings, MissionDescriptions, DEFAULT_TVD, PLANE_TYPES)
from ..geo import (MapTiles, Overlay, WAYPOINT_TAKEOFF, WAYPOINT_LANDING,
                   parse_point, parse_route)
from ..icons import IconLibrary
from .. import corrections, ribbons
from ..loadouts import AmmoSchemes, parse_pilots_list
from ..worldobjects import WorldObjectIndex, normalise as normalise_object
from .attributes import PilotAttributes
from .database import CareerFile, KoreaCareerDatabase, find_careers
from .events import describe, is_award_event
from .killstats import ROLLUP_KEYS, KillStats
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
    # The player's own aircraft can carry a code typed in the hangar; its
    # letters arrive as plain letters and its digits one glyph block up
    # (chr(43)..chr(52)), so the base is whichever block the digits sit in.
    codes = [ord(ch) for ch in digits]
    base = 33 if all(33 <= o <= 42 for o in codes) else 43 if all(43 <= o <= 52 for o in codes) else None
    number = "".join(str(o - base) for o in codes) if base else digits
    if letters.isalpha():
        prefix = letters
    else:
        prefix = BUZZ_PREFIX.get(plane_key.lower(), "")
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


def _humanise(key: str) -> str:
    """IndustrialBuilding -> Industrial Building; Raildoad -> Raildoad (sic)."""
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key)


def _hours(seconds: Optional[int]) -> float:
    return round((seconds or 0) / 3600.0, 1)


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
        self.ribbons = ribbons.RibbonRenderer(self.resolver.cache_dir)
        self.flightlogs = FlightLogIndex(self.game_dir)
        self.descriptions = MissionDescriptions(self.resolver, lang, DEFAULT_TVD)
        # Through the resolver: a stock installation keeps awards.cfg inside
        # Missions.gtp and has no loose copy to read.
        self.awards_cfg = AwardsConfig(
            self.game_dir / "data" / "scg" / str(DEFAULT_TVD) / "awards.cfg",
            resolver=self.resolver)

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
                             for k, v in flight.damage_by_pilot.items()})

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

    def _ribbon_rack(self, medals: List[Dict[str, Any]],
                     citations=()) -> Dict[str, Any]:
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
        names = {m["type"]: m["name"] for m in medals}
        worn = ribbons.rack(m["type"] for m in medals if not m["pending"])
        unit = ribbons.rack(row["type"] for row in citations
                            if row["category"] == 2 and not row["isDeleted"])
        # The aviator badge worn above the ribbons: the highest of the three,
        # sliced from the game's atlas like any medal. The tunic is only drawn
        # for the USAF - it is their coat.
        held = {m["type"] for m in medals if not m["pending"]}
        badge = next((b for b in (601040, 601027, 601001) if b in held), None)
        return {
            "ribbons": entries(worn),
            "rows": ribbons.rows(len(worn)),
            "citations": entries(unit),
            "citation_rows": ribbons.rows(len(unit)),
            "badge": badge,
            "badge_name": names.get(badge) or (self.award_name(badge) if badge else ""),
            "tunic": "usaf" if any(str(t).startswith("601") for t in list(worn) + list(unit)) or badge else None,
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
        for row in awards:
            if row["isDeleted"]:
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
                    for old in retired if old["type"] in below
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
        for sortie in db.query(
                """SELECT missionId, killStats FROM sortie
                   WHERE pilotId = ? AND isDeleted = 0""", (player["id"],)):
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
                "landing_time": _clock(sortie["date"][11:], flight.landing_s) if flight else "",
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
                "ribbon_rack": self._ribbon_rack(groups["awards"], db.awards(-1)),
                "promotions_list": groups["promotions"],
                "incidences": self._incidences(db.events(pilot_id)),
                "recent": self._debriefings(
                    db, sorties[-5:], db.events(pilot_id, types=[0]),
                    with_flight_log=bool(row["isPlayer"])),
                "missions_flown": self._missions_flown(sorties, {m["id"]: m for m in db.missions()}),
            })
            return summary

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

    def _aircraft(self, db, career, squad) -> Dict[str, Any]:
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
                """SELECT s.planeId, s.pilotId, s.killStats, s.planeStatus, s.date,
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
                ks = KillStats(s["killStats"])
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

            return {
                "routes": routes,
                "victories": victories,
                "bases": sorted(bases.values(), key=lambda b: b["first"]),
                "pilot_id": pilot_id,
            }

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
                "ribbon_rack": self._ribbon_rack(groups["awards"], awards_by_pilot.get(-1, [])),
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
                "citations": self._citation_ladders(
                    [r for r in awards_by_pilot.get(-1, []) if r["category"] == 2],
                    retired_citations),
                "aircraft": self._aircraft(db, career, squad),
            }
