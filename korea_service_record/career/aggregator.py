"""
CareerAggregator: turns the raw tables into the shapes the front end renders.

Two views, mirroring the Great Battles tracker:

* ``list_careers()``   — one summary per ``.db`` for the landing page
* ``career_detail(id)`` — roster, player card and service record for one career

Everything here is derived, never stored. All the decoding lives in the sibling
modules (killstats, attributes, events) so this file stays about assembly.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..gamedata import AwardsConfig, LocaleStrings, DEFAULT_TVD
from .attributes import PilotAttributes
from .database import CareerFile, KoreaCareerDatabase, find_careers
from .events import (award_action, award_source, describe, is_award_event,
                     is_loss_event)
from .killstats import KillStats

logger = logging.getLogger(__name__)

# pilot.state, read off the live roster. 0 and 2 are certain (every state-2
# pilot has a KIA event); the rest are inferred from the game's own vocabulary
# and may need widening once a career produces them.
PILOT_STATE = {
    0: "active",
    1: "commander",
    2: "kia",
    3: "wounded",
    4: "pow",
    5: "transferred",
    7: "gone",
}


def _hours(seconds: Optional[int]) -> float:
    return round((seconds or 0) / 3600.0, 1)


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
            "airborne": kills.airborne,
            "ground_targets": kills.ground_targets,
            "attributes": attrs.display_rows(),
            "awards_held": sum(1 for a in held if not a["isPending"]),
            "awards_pending": sum(1 for a in held if a["isPending"]),
            "slot": row["slot"],
            "pcp": row["pcp"],
        }

    # -- landing page ------------------------------------------------------

    def list_careers(self) -> List[Dict[str, Any]]:
        out = []
        for career_id, meta in self._career_files().items():
            try:
                with KoreaCareerDatabase(meta.path) as db:
                    career = db.career()
                    squad = db.squadron()
                    player = db.player()
                    if career is None or player is None:
                        logger.warning("Skipping unreadable career: %s", meta.path)
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
                        "awards": sum(1 for a in held if not a["isPending"]),
                        "roster_size": len(db.pilots()),
                        "award_points": squad["awardPoints"] if squad else 0,
                    })
            except Exception:
                logger.exception("Failed to summarise %s", meta.path)
        out.sort(key=lambda c: c["current_date"], reverse=True)
        return out

    # -- detail page -------------------------------------------------------

    def career_detail(self, career_id: str) -> Optional[Dict[str, Any]]:
        meta = self._career_files().get(career_id)
        if meta is None:
            return None

        with KoreaCareerDatabase(meta.path) as db:
            career = db.career()
            squad = db.squadron()
            player = db.player()
            if career is None or player is None:
                return None

            awards_by_pilot: Dict[int, List] = {}
            for row in db.awards():
                awards_by_pilot.setdefault(row["pilotId"], []).append(row)

            roster = [self._pilot_row(p, awards_by_pilot) for p in db.pilots()]
            roster.sort(key=lambda p: (not p["is_player"], p["rank_id"] * -1,
                                       -p["sorties"]))

            return {
                "id": career_id,
                "squadron": meta.squadron_name,
                "start_date": career["startDate"],
                "current_date": career["currentDate"],
                "award_points": squad["awardPoints"] if squad else 0,
                "efficiency": squad["efficiency"] if squad else None,
                "player": self._pilot_row(player, awards_by_pilot),
                "player_awards": self._awards_for(db, player["id"]),
                "service_record": self._service_record(db, player["id"]),
                "roster": roster,
                "pending_total": sum(p["awards_pending"] for p in roster),
            }

    def _awards_for(self, db: KoreaCareerDatabase, pilot_id: int) -> List[Dict]:
        out = []
        for row in db.awards(pilot_id):
            out.append({
                "type": row["type"],
                "name": self.award_name(row["type"]),
                "earned": row["earnedDate"],
                "received": row["receivedDate"],
                "pending": bool(row["isPending"]),
                "is_promotion": row["category"] == 1,
            })
        return out

    def _service_record(self, db: KoreaCareerDatabase, pilot_id: int) -> List[Dict]:
        """
        The pilot's history, in the spirit of the game's own SERVICE RECORDS
        panel but with the award route shown — which the game never tells you.
        """
        out = []
        for row in db.events(pilot_id):
            info = describe(row["type"])
            if info.key == "kill":
                continue                      # far too many to list individually
            entry = {
                "date": row["date"][:10],
                "kind": info.key,
                "label": info.label,
                "confidence": info.confidence,
            }
            if is_award_event(row["type"]):
                entry["award"] = self.award_name(row["ipar2"])
                entry["action"] = award_action(row["ipar3"])
                entry["route"] = award_source(row["missionId"])
                if entry["action"] == "removed":
                    continue                  # superseded clusters are noise here
            elif is_loss_event(row["type"]):
                entry["aircraft"] = row["tpar1"]
            elif row["type"] in (5, 16):
                entry["health"] = row["ipar2"]
                entry["phase"] = "returned" if row["ipar1"] == 1 else "start"
            out.append(entry)
        out.reverse()
        return out
