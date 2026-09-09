"""
Event type map for the IL-2 Korea ``event`` table.

Korea's numbering is unrelated to Great Battles' (where 4=aircraft lost,
6=promotion, 8=award, 13=medical leave). Everything below was derived from a
live career and cross-checked, so each entry carries the evidence behind it and
nothing inherits false confidence:

    CONFIRMED  matched exactly against a second source — the flight logs, a
               count elsewhere in the schema, or the game's own UI
    LIKELY     one interpretation fits every row and a UI string names it,
               but nothing independently pins it
    UNKNOWN    seen, not yet identified

Row shape: id, date, type, pilotId, rankId, missionId, squadronId, careerId,
planeId, ipar1..ipar4, tpar1..tpar4, insdate, isDeleted.

Two fields recur across several types:

``ipar2`` as health
    Types 5, 16 and 18 all carry the health of the pilot or aircraft at the
    moment of the event (observed range 40-98). Plane 3's unpaired
    ``(0, 85)`` row matches its live ``plane.health = 85``.

``missionId`` as the award route
    On types 19 and 20, a real mission id means the mission-debrief pass
    (``AwardInProc``, the only place per-sortie variables are non-zero) and -1
    means a roster sweep.
"""

import logging
from typing import Dict, NamedTuple, Optional

logger = logging.getLogger(__name__)

CONFIRMED = "confirmed"
LIKELY = "likely"
UNKNOWN = "unknown"


class EventType(NamedTuple):
    code: int
    key: str
    label: str
    confidence: str
    note: str = ""


# -- award / promotion sub-actions (ipar3) ---------------------------------
ACTION_GRANTED = 0
ACTION_PRESENTED = 1
ACTION_REMOVED = 2

AWARD_ACTIONS: Dict[int, str] = {
    ACTION_GRANTED: "granted",
    ACTION_PRESENTED: "presented",
    ACTION_REMOVED: "removed",
}

# -- start/finish sub-actions (ipar1 on types 16, 18, 33) ------------------
PHASE_START = 0
PHASE_END = 1


EVENT_TYPES: Dict[int, EventType] = {
    0: EventType(0, "kill", "Target destroyed", CONFIRMED,
                 "tpar1 = target object name. Names beginning Static_ are "
                 "ground kills, but plain names such as 'Windsock' are ground "
                 "objects too, so never infer airborne kills from these — use "
                 "killStats."),

    2: EventType(2, "plane_lost", "Aircraft lost", CONFIRMED,
                 "Fires whether or not the pilot survives. tpar1 = aircraft "
                 "type and tpar2 = pilot name for AI; for the player tpar1 "
                 "holds their callsign instead. Confirmed in the flight log "
                 "for mission 31: both Lucien Stokes and the player have their "
                 "F-51D destroyed (AType:3) and both get a type 2 row."),

    3: EventType(3, "pilot_kia", "Pilot killed in action", CONFIRMED,
                 "The set of pilots with a type 3 row equals the set with "
                 "pilot.state = 2 exactly (9 of 9). In the mission 31 log the "
                 "difference from type 2 is visible: Stokes has his pilot bot "
                 "destroyed as well as his aircraft and gets a type 3; the "
                 "player loses only the aircraft and gets none."),

    5: EventType(5, "wounded", "Wounded in action", CONFIRMED,
                 "ipar2 = the pilot's health afterwards. Emitted alongside a "
                 "type 16 with the same value, and matches the in-game service "
                 "record line 'Wounded in action' for pilot 17 on 1951.04.12."),

    8: EventType(8, "commander_assigned", "Commander assigned", LIKELY,
                 "One row, for the player, at career start. Matches the UI "
                 "string carEventCommander_Assigned, 'New commander - "
                 "$[rank] $[name]'."),

    13: EventType(13, "unknown_13", "Unknown (13)", UNKNOWN,
                  "One row: the player, 1951.05.15 06:00, a day the career "
                  "skips over. No ipar. Candidates from the UI strings are "
                  "leave, discharge or a newspaper; none confirmed."),

    14: EventType(14, "reported", "Reported for duty", LIKELY,
                  "Emitted for replacement pilots on arrival; all ipar are -1. "
                  "Matches the service-record line 'Reported for duty with "
                  "<squadron>'."),

    15: EventType(15, "plane_delivered", "Aircraft delivered", CONFIRMED,
                  "One row per aircraft received. 17 rows against 17 airframes "
                  "delivered (supply.type = 1, status = 3), and the first batch "
                  "of four names planes 21-24, matching supply #1 quantity 4."),

    16: EventType(16, "medical", "Hospital", CONFIRMED,
                  "ipar1 = 0 sent to hospital, 1 returned to duty. ipar2 = "
                  "health. Pilot 17's pair on 1951.04.12 and 1951.04.14 "
                  "matches the service record exactly."),

    18: EventType(18, "plane_repair", "Aircraft repair", CONFIRMED,
                  "ipar1 = 0 sent for repair, 1 repaired. ipar2 = the "
                  "aircraft's health. Rows pair up per plane with the same "
                  "value, and an unpaired 0 row matches a plane still sitting "
                  "at plane.state = 2 with that health."),

    19: EventType(19, "promotion", "Promotion", CONFIRMED,
                  "ipar1 = award row id, ipar2 = promotion award type "
                  "(601980..601984), ipar3 = action. rankId holds the rank at "
                  "the time of the row, so it differs between the granted and "
                  "presented rows."),

    20: EventType(20, "award", "Award", CONFIRMED,
                  "ipar1 = award row id, ipar2 = award type, ipar3 = action."),

    25: EventType(25, "efficiency", "Squadron efficiency changed", LIKELY,
                  "One row, ipar1 = 3, matching squadron.efficiency = 3 and "
                  "the UI string 'Efficiency increased to $[value]'. ipar2 = 1 "
                  "is probably the direction."),

    26: EventType(26, "request_points", "Request points awarded", LIKELY,
                  "ipar2 = mission.missionNum (49 of 49). ipar1 = points, "
                  "matching carEventRequestsUpdate, '$[quantity] request "
                  "points awarded for mission #$[id]'. Totals corroborate: 343 "
                  "awarded against 348 spent in supply.cost, consistent with a "
                  "small starting balance."),

    31: EventType(31, "emergency_mission", "Unscheduled mission", CONFIRMED,
                  "ipar1 = mission.targetId, ipar2 = mission.type. All three "
                  "rows match the three missions with isEmergency = 1 and a "
                  "negative missionNum. UI string carEventEmergencyTarget."),

    32: EventType(32, "resources_destroyed", "Airfield resources destroyed",
                  LIKELY,
                  "One row, ipar1..3 = 14800 / 230 / 77, matching the three "
                  "squadron resource pools (fuel, ammo, parts) and the UI "
                  "string carEventResourcesDestroyed. Fired ten minutes after "
                  "an unscheduled mission was raised against the airfield."),

    33: EventType(33, "operation", "Operation", CONFIRMED,
                  "ipar1 = 0 begin / 1 end, tpar1 = operation name."),
}


def describe(type_code: int) -> EventType:
    """Look up an event type, returning a placeholder for unseen codes."""
    known = EVENT_TYPES.get(type_code)
    if known is not None:
        return known
    logger.info("Unmapped event type encountered: %s", type_code)
    return EventType(type_code, f"unknown_{type_code}",
                     f"Unknown ({type_code})", UNKNOWN)


def is_award_event(type_code: int) -> bool:
    """Award and promotion rows share the ipar layout."""
    return type_code in (19, 20)


def is_loss_event(type_code: int) -> bool:
    """Aircraft lost or pilot killed — what Viking1 asked to see per pilot."""
    return type_code in (2, 3)


def carries_health(type_code: int) -> bool:
    """Types whose ipar2 is a health value rather than an id."""
    return type_code in (5, 16, 18)


def award_action(ipar3: Optional[int]) -> str:
    return AWARD_ACTIONS.get(ipar3, f"unknown({ipar3})")


def award_source(mission_id: Optional[int]) -> str:
    """
    Which evaluation pass produced an award row.

    A real mission id means the debrief pass, the only place the per-sortie
    variables (AirObjSortie, WIASortie) are non-zero. -1 means a roster sweep,
    where only career totals are live.
    """
    return "sweep" if mission_id is None or mission_id == -1 else "mission"
