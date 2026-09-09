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
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..gamedata import AwardsConfig, LocaleStrings, DEFAULT_TVD, PLANE_TYPES
from .attributes import PilotAttributes
from .database import CareerFile, KoreaCareerDatabase, find_careers
from .events import describe, is_award_event
from .killstats import KillStats

logger = logging.getLogger(__name__)

PILOT_STATE = {
    0: "active", 1: "commander", 2: "kia", 3: "wounded",
    4: "pow", 5: "transferred", 7: "gone",
}

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


def _hours(seconds: Optional[int]) -> float:
    return round((seconds or 0) / 3600.0, 1)


def _hm(seconds: Optional[int]) -> str:
    total = int(seconds or 0)
    return f"{total // 3600}h {total % 3600 // 60:02d}m"


class CareerAggregator:
    """Builds the API payloads for one game installation."""

    def __init__(self, game_dir: Path, lang: str = "eng"):
        self.game_dir = Path(game_dir)
        self.lang = lang
        self.locale = LocaleStrings(self.game_dir, lang)
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
            "state": PILOT_STATE.get(row["state"], f"state{row['state']}"),
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
            "promotions": sum(1 for a in held if a["category"] == 1),
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
        breakdown = [{"label": k, "value": v}
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
            {"label": "Missions completed", "value": len(sorties)},
            {"label": "Flight time", "value": _hm(total_time)},
            {"label": "Average flight time", "value": _hm(total_time // count)},
            {"label": "Aircraft returned", "value": outcomes.get("returned", 0)},
            {"label": "Aircraft damaged", "value": outcomes.get("damaged", 0)},
            {"label": "Aircraft lost", "value": outcomes.get("lost", 0)},
            {"label": "Wounded in action", "value": wounded},
        ]

    def _promotions_and_awards(self, awards) -> Dict[str, List]:
        promotions, medals = [], []
        for row in awards:
            if row["category"] == 1:
                rank_id = row["type"] - PROMOTION_BASE + 1
                promotions.append({
                    "rank": self.locale.rank_name(601, rank_id),
                    "rank_id": rank_id,
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

    def _incidences(self, events) -> List[Dict[str, Any]]:
        """Everything in the pilot's history that is *not* an award."""
        out = []
        for row in events:
            info = describe(row["type"])
            if info.key == "kill" or is_award_event(row["type"]):
                continue
            entry = {"date": row["date"][:10], "kind": info.key,
                     "label": info.label, "confidence": info.confidence}
            if info.key == "plane_lost":
                entry["detail"] = row["tpar1"]
            elif info.key in ("wounded", "medical"):
                if info.key == "medical" and row["ipar1"] == 1:
                    entry["label"] = "Returned to duty"
                    entry["kind"] = "recovered"
                else:
                    entry["detail"] = f"health {row['ipar2']}"
            out.append(entry)
        out.reverse()
        return out

    def _debriefings(self, db, sorties, kill_events) -> List[Dict[str, Any]]:
        by_mission: Dict[int, List] = {}
        for row in kill_events:
            by_mission.setdefault(row["missionId"], []).append(row)
        missions = {m["id"]: m for m in db.missions()}

        out = []
        for sortie in sorties:
            mission = missions.get(sortie["missionId"])
            kills = sorted(by_mission.get(sortie["missionId"], []),
                           key=lambda r: r["date"])
            log = [{"time": r["date"][11:19], "target": r["tpar1"],
                    "air": (r["tpar1"] or "").lower() in PLANE_TYPES}
                   for r in kills]
            k = KillStats(sortie["killStats"])
            out.append({
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
            })
        out.reverse()
        return out

    # -- detail page -------------------------------------------------------

    def career_detail(self, career_id: str) -> Optional[Dict[str, Any]]:
        meta = self._career_files().get(career_id)
        if meta is None:
            return None

        with KoreaCareerDatabase(meta.path) as db:
            career, squad, player = db.career(), db.squadron(), db.player()
            if career is None or player is None:
                return None
            pid = player["id"]

            awards_by_pilot: Dict[int, List] = {}
            for row in db.awards():
                awards_by_pilot.setdefault(row["pilotId"], []).append(row)

            roster = [self._pilot_row(p, awards_by_pilot) for p in db.pilots()]
            roster.sort(key=lambda p: (not p["is_player"], -p["rank_id"],
                                       -p["sorties"]))

            sorties = db.sorties(pid)
            kill_events = db.events(pid, types=[0])
            player_awards = db.awards(pid)
            groups = self._promotions_and_awards(player_awards)

            # The rank on the earliest sortie is where the career began.
            starting_rank_id = sorties[0]["rankId"] if sorties else player["rankId"]

            return {
                "id": career_id,
                "squadron": meta.squadron_name,
                "start_date": career["startDate"],
                "current_date": career["currentDate"],
                "award_points": squad["awardPoints"] if squad else 0,
                "efficiency": squad["efficiency"] if squad else None,
                "player": self._pilot_row(player, awards_by_pilot),
                "combat": self._combat_results(KillStats(player["killStats"])),
                "air_kills_by_type": self._air_kills_by_type(kill_events),
                "missions_flown": self._missions_flown(sorties),
                "promotions": groups["promotions"],
                "awards": groups["awards"],
                "incidences": self._incidences(db.events(pid)),
                "debriefings": self._debriefings(db, sorties, kill_events),
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
