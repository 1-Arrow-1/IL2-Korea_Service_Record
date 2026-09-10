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

import logging
import re
import urllib.parse
from collections import Counter, OrderedDict
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

from ..assets import AssetResolver
from ..flightlog import FlightLogIndex
from ..gamedata import COUNTRY_FLAGS, COUNTRY_NAMES, COUNTRY_STAMPS, AwardsConfig, LocaleStrings, DEFAULT_TVD, PLANE_TYPES
from ..icons import IconLibrary
from ..worldobjects import WorldObjectIndex
from .attributes import PilotAttributes
from .database import CareerFile, KoreaCareerDatabase, find_careers
from .events import describe, is_award_event
from .killstats import KillStats
from .missionresult import MissionResult, _number

logger = logging.getLogger(__name__)

# pilot.state. Only 0, 2 and 4 occur in a real career, and all three are
# confirmed: every state-2 pilot has a KIA event, and the two state-4 pilots are
# in hospital with a stateEndDate to return on — NOT prisoners, which is what an
# earlier guess had them as. The rest are left unmapped rather than invented.
PILOT_STATE = {0: "active", 2: "kia", 4: "wounded"}

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


def _top_combat_award(country: int, award_ids) -> Optional[int]:
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


class CareerAggregator:
    """Builds the API payloads for one game installation."""

    def __init__(self, game_dir: Path, lang: str = "eng"):
        self.game_dir = Path(game_dir)
        self.lang = lang
        self.resolver = AssetResolver(self.game_dir)
        self.locale = LocaleStrings(self.game_dir, lang, resolver=self.resolver)
        self.objects = WorldObjectIndex(self.resolver, lang)
        self.icons = IconLibrary(self.resolver)
        self.flightlogs = FlightLogIndex(self.game_dir)
        self.awards_cfg = AwardsConfig(
            self.game_dir / "data" / "scg" / str(DEFAULT_TVD) / "awards.cfg")

    # -- helpers -----------------------------------------------------------

    def _career_files(self) -> Dict[str, CareerFile]:
        return {c.path.stem: c for c in find_careers(self.game_dir)}

    def award_name(self, award_id: int) -> str:
        defn = self.awards_cfg.get(award_id)
        return self.locale.award_name(award_id, defn.name if defn else "")

    def _pilot_row(self, row, awards_by_pilot: Dict[int, List]) -> Dict[str, Any]:
        kills = KillStats(row["killStats"])
        attrs = PilotAttributes(row["persLevel"], row["leadLevel"])
        held = awards_by_pilot.get(row["id"], [])
        described = _pilot_description(row["description"])
        medals = [a for a in held if a["category"] != 1 and not a["isPending"]]
        top = _top_combat_award(row["country"], (a["type"] for a in medals))
        return {
            "id": row["id"],
            "name": f"{row['name']} {row['lastName']}".strip(),
            "is_player": bool(row["isPlayer"]),
            "country": row["country"],
            "rank_id": row["rankId"],
            # pilot.rankId is authoritative. The game's own Award and Promotion
            # panel shifts ranks up by the number of promotions a pilot has had.
            "rank": self.locale.rank_name(row["country"], row["rankId"]),
            "state": PILOT_STATE.get(row["state"], f"state {row['state']}"),
            "state_until": (row["stateEndDate"][:10]
                            if row["state"] == 4
                            and not row["stateEndDate"].startswith("0000") else ""),
            # For the dead, stateDate is the day they were lost.
            "state_since": (row["stateDate"][:10]
                            if row["state"] == 2
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

    def emblem_detail(self, kind: str, ident: str) -> Optional[Dict[str, Any]]:
        """
        Name, description and full-size art for one medal, rank or emblem.

        Descriptions live beside the artwork in the archives:

            awards      nsdata/assets/awards/<6xx>/<id>.locale=<lang>.txt
            squadrons   nsdata/assets/squadrons/<601>/<id>.locale=<lang>.txt

        Ranks have artwork but no description, so they return a name only.
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
        return {
            "kind": kind,
            "id": ident,
            "name": name,
            "description": (text or "").strip(),
            "inherited_from": inherited,
            "image": f"/api/icon/{kind}/{ident}",
        }

    # -- landing page ------------------------------------------------------

    def list_careers(self) -> List[Dict[str, Any]]:
        out = []
        for career_id, meta in self._career_files().items():
            try:
                with KoreaCareerDatabase(meta.path) as db:
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
        # The game names these itself in every language it ships; _humanise is
        # only the fallback for the rollups it has no category for.
        breakdown = [{"label": self.locale.stat_name(k) or _humanise(k), "value": v}
                     for k, v in sorted(kills.counts.items(), key=lambda x: -x[1])
                     if k != "Aircraft" and v]
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
            "airborne": [{"name": n, "value": v} for n, v in airborne.most_common()],
            "parked": [{"name": n, "value": v} for n, v in parked.most_common()],
        }

    def _missions_flown(self, sorties) -> List[Dict[str, Any]]:
        total_time = sum(s["flightTime"] or 0 for s in sorties)
        outcomes = Counter(PLANE_OUTCOME.get(s["planeStatus"], "unknown")
                           for s in sorties)
        wounded = sum(1 for s in sorties if s["status"] == 4)
        count = len(sorties) or 1
        return [
            # Every row carries a key as well as the English. The front end
            # prefers the key; the prose stays as a fallback for anything the
            # locale files have not caught up with.
            {"key": "missions.completed",
             "label": "Missions completed", "value": len(sorties)},
            {"key": "missions.flight_time",
             "label": "Flight time", "value": _hm(total_time)},
            {"key": "missions.average_flight_time",
             "label": "Average flight time", "value": _hm(total_time // count)},
            {"key": "missions.returned",
             "label": "Aircraft returned", "value": outcomes.get("returned", 0)},
            {"key": "missions.damaged",
             "label": "Aircraft damaged", "value": outcomes.get("damaged", 0)},
            {"key": "missions.lost",
             "label": "Aircraft lost", "value": outcomes.get("lost", 0)},
            {"key": "missions.wounded",
             "label": "Wounded in action", "value": wounded},
        ]

    def _promotions_and_awards(self, awards, country: int = 601) -> Dict[str, List]:
        promotions, medals = [], []
        for row in awards:
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
                medals.append({
                    "type": row["type"],
                    "name": self.award_name(row["type"]),
                    "earned": row["earnedDate"],
                    "received": row["receivedDate"],
                    "pending": bool(row["isPending"]),
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
        best_air = best_ground = best_points = career_points = 0
        for mission in db.missions():
            for row in MissionResult(mission["result"]).players():
                if not row.get("personageNickname"):
                    continue                      # AI rows carry no nickname
                best_air = max(best_air, int(_number(row.get("airKillStreak", "0"))))
                best_ground = max(best_ground,
                                  int(_number(row.get("groundKillStreak", "0"))))
                points = int(_number(row.get("pointsSumByMission", "0")))
                best_points = max(best_points, points)
                career_points += points

        sorties = player["sorties"] or 0
        hours = (player["flightTime"] or 0) / 3600.0
        airborne = KillStats(player["killStats"]).airborne
        altitudes = [v["altitude"] for v in victories if v["altitude"]]

        average = round(sum(altitudes) / len(altitudes)) if altitudes else None
        # value_key marks a value that is itself prose — "7 in one sortie" —
        # and so has to be assembled in the reader's language, not here.
        return [
            {"key": "performance.best_air_streak", "label": "Best air victory streak",
             "value": best_air, "value_key": "performance.in_one_sortie"},
            {"key": "performance.best_ground_streak", "label": "Best ground streak",
             "value": best_ground, "value_key": "performance.in_one_sortie"},
            {"key": "performance.per_sortie", "label": "Victories per sortie",
             "value": f"{airborne / sorties:.2f}" if sorties else "—"},
            {"key": "performance.per_hour", "label": "Victories per flight hour",
             "value": f"{airborne / hours:.1f}" if hours else "—"},
            {"key": "performance.average_altitude", "label": "Average victory altitude",
             "value": f"{average:,}" if average is not None else "—",
             "value_key": "common.metres" if average is not None else None},
            {"key": "performance.best_score", "label": "Best mission score",
             "value": f"{best_points:,}"},
            {"key": "performance.career_score", "label": "Career score",
             "value": f"{career_points:,}"},
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

        out = []
        for sortie in sorties:
            mission = missions.get(sortie["missionId"])
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
            outcome = PLANE_OUTCOME.get(sortie["planeStatus"], "unknown")
            landing = ""
            if flight is not None:
                if flight.ejected:
                    landing = "bailed out"
                elif flight.landing_s is None:
                    landing = "did not return"
                elif outcome == "damaged":
                    landing = "landed, aircraft damaged"
                else:
                    landing = "landed"
            out.append({
                "takeoff": _clock(sortie["date"][11:], flight.takeoff_s) if flight else "",
                "landing_time": _clock(sortie["date"][11:], flight.landing_s) if flight else "",
                "landing": landing,
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
        with KoreaCareerDatabase(meta.path) as db:
            row = db.pilot(pilot_id)
            if row is None:
                return None
            awards_by_pilot = {pilot_id: db.awards(pilot_id)}
            summary = self._pilot_row(row, awards_by_pilot)
            groups = self._promotions_and_awards(db.awards(pilot_id), row["country"])
            sorties = db.sorties(pilot_id)
            kills = KillStats(row["killStats"])
            summary.update({
                "career_id": career_id,
                "squadron": meta.squadron_name,
                "combat": self._combat_results(kills)["headline"],
                "awards_list": groups["awards"],
                "promotions_list": groups["promotions"],
                "incidences": self._incidences(db.events(pilot_id)),
                "recent": self._debriefings(
                    db, sorties[-5:], db.events(pilot_id, types=[0]),
                    with_flight_log=bool(row["isPlayer"])),
                "missions_flown": self._missions_flown(sorties),
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
            if all(_number(slot.get("totalFlightTime", "-1")) == pilot["flight_s"]
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
        with KoreaCareerDatabase(meta.path) as db:
            mission = db.query_one("SELECT * FROM mission WHERE id=?", (mission_id,))
            if mission is None:
                return None
            result = MissionResult(mission["result"])

            flown = []
            for row in db.query(
                    """SELECT s.*, p.name, p.lastName, p.isPlayer, p.avatarPath,
                              p.country, p.rankId
                       FROM sortie s JOIN pilot p ON p.id = s.pilotId
                       WHERE s.missionId = ? AND s.isDeleted = 0
                       ORDER BY s.id""", (mission_id,)):
                kills = KillStats(row["killStats"])
                flown.append({
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
                    "outcome": PLANE_OUTCOME.get(row["planeStatus"], "unknown"),
                    "wounded": row["status"] == 4,
                })

            # Events name the actor by IL-2 account ("Arrow_1974") for the
            # human and by aircraft type ("F51D") for the AI, so every wingman's
            # kills used to read the same. Both are resolved to the pilot who
            # actually scored them.
            # _crew pairs the blob's formation slots against these rows in the
            # order the game wrote them, so the sort for display happens after.
            crew = self._crew(result, flown)
            flown.sort(key=lambda f: (not f["is_player"], -f["rank_id"]))
            player_user = next((uid for uid, name in crew.items()
                                if name == next((f["name"] for f in flown
                                                 if f["is_player"]), None)), "")

            start = mission["startTime"][11:] if mission["startTime"] else ""
            log = []
            for e in result.events():
                info = self.objects.describe(e["target"])
                actor = crew.get(e["actor_user"], "")
                if not actor:
                    by = self.objects.describe(e["actor"])
                    actor = by["name"] if by["named"] else e["actor"]
                air = bool(info["aircraft"] and not info["parked"])
                log.append({
                    "time": _clock(start, e["tick"]),
                    "target": info["name"],
                    "named": info["named"],
                    "air": air,
                    "victim": e["victim"],
                    "altitude": e["altitude"] if air else None,
                    "actor": actor,
                    "by_player": e["actor_user"] == player_user,
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

            briefing = urllib.parse.unquote(mission["briefing"] or "")
            return {
                "id": mission_id,
                "number": mission["missionNum"],
                "date": mission["date"],
                "start": mission["startTime"],
                "end": mission["endTime"],
                "type": self.locale.mission_type_name(mission["type"]),
                "briefing": briefing,
                "duration": _hm(result.duration_s or 0),
                "objectives": result.objectives(),
                "coalitions": result.coalitions(),
                "obj_success": mission["objSuccess"],
                "obj_failure": mission["objFailure"],
                "flown": flown,
                "log": log,
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

        with KoreaCareerDatabase(meta.path) as db:
            career, squad = db.career(), db.squadron()
            subject = db.pilot(pilot_id) if pilot_id is not None else db.player()
            if career is None or subject is None:
                return None
            player = subject
            pid = player["id"]
            is_player = bool(player["isPlayer"])

            awards_by_pilot: Dict[int, List] = {}
            for row in db.awards():
                awards_by_pilot.setdefault(row["pilotId"], []).append(row)

            roster = [self._pilot_row(p, awards_by_pilot) for p in db.pilots()]
            roster.sort(key=lambda p: (not p["is_player"], -p["rank_id"],
                                       -p["sorties"]))

            sorties = db.sorties(pid)
            kill_events = db.events(pid, types=[0])
            player_awards = db.awards(pid)
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
                "player": self._pilot_row(player, awards_by_pilot),
                "combat": self._combat_results(KillStats(player["killStats"])),
                "air_kills_by_type": self._air_kills_by_type(kill_events),
                "missions_flown": self._missions_flown(sorties),
                "promotions": groups["promotions"],
                "awards": groups["awards"],
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
            }
