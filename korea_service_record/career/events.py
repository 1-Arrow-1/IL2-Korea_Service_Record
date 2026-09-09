"""
Event type map for the IL-2 Korea ``event`` table.

Korea's numbering is unrelated to Great Battles' (where 4=aircraft lost,
6=promotion, 8=award, 13=medical leave). Everything below is derived from a
live career, cross-checked against the in-game service record where possible.
Types are marked with the evidence behind them so nothing inherits false
confidence:

    CONFIRMED  cross-checked against the DB *and* the in-game UI
    LIKELY     consistent across many rows, one interpretation fits
    UNKNOWN    seen, not yet identified

Row shape: id, date, type, pilotId, rankId, missionId, squadronId, careerId,
planeId, ipar1..ipar4, tpar1..tpar4, insdate, isDeleted.

``missionId`` is the single most useful discriminator on award events:
a real mission id means the mission-debrief pass (``AwardInProc``), while -1
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
# Verified: 601019 granted at m47 (ipar3=0), 601018 retired in the same pass
# (ipar3=2), 601019 handed over on the next career day (ipar3=1).
ACTION_GRANTED = 0
ACTION_PRESENTED = 1
ACTION_REMOVED = 2

AWARD_ACTIONS: Dict[int, str] = {
    ACTION_GRANTED: "granted",
    ACTION_PRESENTED: "presented",
    ACTION_REMOVED: "removed",
}

# -- operation sub-actions (ipar1 on type 33) ------------------------------
OPERATION_BEGIN = 0
OPERATION_END = 1


EVENT_TYPES: Dict[int, EventType] = {
    0: EventType(0, "kill", "Target destroyed", CONFIRMED,
                 "tpar1 = target object name. Names beginning Static_ are "
                 "ground kills; note that plain names such as 'Windsock' are "
                 "also ground objects, so never infer airborne kills from "
                 "these names — use killStats instead."),
    5: EventType(5, "wounded", "Wounded in action", LIKELY,
                 "Pilot 17 on 1951.04.12 11:30 with ipar2=83, matching the "
                 "service record line 'Wounded in action: Light' on that date."),
    14: EventType(14, "reported", "Reported for duty", LIKELY,
                  "Emitted for replacement pilots on arrival; all ipar are -1."),
    16: EventType(16, "medical", "Hospital / return to duty", LIKELY,
                  "ipar1=0 sent to hospital, ipar1=1 returned to duty. Pilot 17 "
                  "has the pair on 1951.04.12 and 1951.04.14, matching the "
                  "service record exactly. ipar2 carries the same code as the "
                  "type 5 wound event."),
    19: EventType(19, "promotion", "Promotion", CONFIRMED,
                  "ipar1 = award row id, ipar2 = promotion award type "
                  "(601980..601984), ipar3 = action. The rankId column holds "
                  "the rank at the time of the row, so it changes between the "
                  "granted row and the presented row."),
    20: EventType(20, "award", "Award", CONFIRMED,
                  "ipar1 = award row id, ipar2 = award type, ipar3 = action."),
    33: EventType(33, "operation", "Operation", CONFIRMED,
                  "ipar1 = 0 begin / 1 end, tpar1 = operation name."),

    # Seen in live data, not yet identified.
    2: EventType(2, "unknown_2", "Unknown (2)", UNKNOWN),
    3: EventType(3, "unknown_3", "Unknown (3)", UNKNOWN),
    8: EventType(8, "unknown_8", "Unknown (8)", UNKNOWN),
    13: EventType(13, "unknown_13", "Unknown (13)", UNKNOWN),
    15: EventType(15, "unknown_15", "Unknown (15)", UNKNOWN),
    18: EventType(18, "unknown_18", "Unknown (18)", UNKNOWN,
                  "pilotId=-1, planeId set — plane repair or replacement?"),
    25: EventType(25, "unknown_25", "Unknown (25)", UNKNOWN),
    26: EventType(26, "unknown_26", "Unknown (26)", UNKNOWN,
                  "Carries a missionId; ipar1/ipar2 look like counters."),
    31: EventType(31, "unknown_31", "Unknown (31)", UNKNOWN),
    32: EventType(32, "unknown_32", "Unknown (32)", UNKNOWN),
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


def award_action(ipar3: Optional[int]) -> str:
    return AWARD_ACTIONS.get(ipar3, f"unknown({ipar3})")


def award_source(mission_id: Optional[int]) -> str:
    """
    Which evaluation pass produced an award row.

    A real mission id means the debrief pass, which is the only place the
    per-sortie variables (AirObjSortie, WIASortie) are non-zero. -1 means a
    roster sweep, where only career totals are live.
    """
    return "sweep" if mission_id is None or mission_id == -1 else "mission"
