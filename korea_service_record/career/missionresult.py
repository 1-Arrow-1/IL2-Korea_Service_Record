"""
Parser for ``mission.result`` — the debrief the game stores per mission.

Every mission row carries a ~22 KB url-encoded blob that nothing else in the
schema duplicates. It is a set of ``key=value`` sections joined by ``&``, and
the interesting ones are CSV-ish: a header row of column names, then one row
per record, all joined by ``|``::

    events=type,date,x,y,z,targetType,actorType,targetCountry,actorCountry,
           targetName,actorName,targetUserId,actorUserId|0,386,167370,307,...
    players=airKillStreak,...,personageNickname,...|0,0,0,...
    damages=personageId,plane,pilot|<guid>,0.5398,0.0982
    coalitions=id,missionStatus,pointsCount,sortieCount|0,2,20,0

``events`` gives every kill with its position — including **altitude** and the
victim's pilot name, neither of which is anywhere else. ``players`` gives about
a hundred per-pilot counters for everyone who flew, not just the human.
``damages`` gives how badly each aircraft and pilot were hurt, as fractions.

Parsed lazily: 22 KB per mission across fifty missions is a megabyte of work
for data that is only ever on screen one mission at a time.
"""

import logging
import urllib.parse
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# events.type — 0 is the only value seen in a career, on rows that are plainly
# kills (they carry a target, an actor and a position).
EVENT_KILL = 0

# AI personage ids are not random: "00000000-0000-0000-0000-300000000000" is
# formation slot 3. The human's row carries a real account guid instead.
AI_ID_PREFIX = "00000000-0000-0000-0000-"


def _unquote(text: str) -> str:
    """
    Ids survive the section-level unquote still escaped.

    The blob is url-encoded twice, so a guid arrives as
    ``00000000%2d0000%2d...`` with its hyphens still escaped. Comparing those
    against the singly-encoded ids in ``events`` fails silently, which is what
    kept the AI slots from ever matching a pilot.
    """
    return urllib.parse.unquote(text or "")


def _rows(section: str) -> List[Dict[str, str]]:
    """Split one ``header|row|row`` section into dicts."""
    parts = section.split("|")
    if len(parts) < 2:
        return []
    columns = parts[0].split(",")
    out = []
    for row in parts[1:]:
        values = row.split(",")
        if len(values) < len(columns):
            # A trailing column can be absent; pad rather than drop the row.
            values += [""] * (len(columns) - len(values))
        out.append(dict(zip(columns, values)))
    return out


def _number(text: str, default: float = 0.0) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


class MissionResult:
    """One decoded ``mission.result``."""

    def __init__(self, raw: Optional[str]):
        self.sections: Dict[str, str] = {}
        text = urllib.parse.unquote(raw or "")
        for part in text.split("&"):
            key, _, value = part.partition("=")
            if key:
                self.sections[key] = value

    @property
    def duration_s(self) -> int:
        return int(_number(self.sections.get("missionDuration", "0")))

    def events(self) -> List[Dict[str, Any]]:
        """
        Kills, each with position and the names of both parties.

        ``targetName`` is either a pilot ("Nam-il Chung,503056,0"), a generic
        bucket ("BlocksArray", "NOICON") for scenery, or empty. Only the pilot
        form is worth showing, so it is split out rather than printed raw.
        """
        out = []
        for row in _rows(self.sections.get("events", "")):
            if int(_number(row.get("type", "-1"), -1)) != EVENT_KILL:
                continue
            target_name = urllib.parse.unquote(row.get("targetName", ""))
            victim = ""
            if target_name and target_name not in ("BlocksArray", "NOICON"):
                # "Nam-il Chung,503056,0" -> the name only
                victim = target_name.split(",")[0].strip()
            out.append({
                "tick": int(_number(row.get("date", "0"))),
                "target": row.get("targetType", ""),
                "actor": urllib.parse.unquote(row.get("actorType", "")),
                "victim": victim,
                "altitude": int(_number(row.get("y", "0"))),
                "x": int(_number(row.get("x", "0"))),
                "z": int(_number(row.get("z", "0"))),
                "actor_user": _unquote(row.get("actorUserId", "")),
            })
        return out

    def players(self) -> List[Dict[str, str]]:
        """Every pilot's counters, with the identifying fields decoded."""
        rows = _rows(self.sections.get("players", ""))
        for row in rows:
            for field in ("personageId", "userId", "parentId", "personageNickname"):
                if field in row:
                    row[field] = _unquote(row[field])
        return rows

    def flight_slots(self) -> List[Dict[str, str]]:
        """
        The AI rows in formation-slot order, which is the order the career's
        own ``sortie`` rows are written in.

        Checked across both careers and every mission: 372 of 372 pairings
        agree exactly on ``totalFlightTime``, and again on air kills counted
        from an unrelated set of columns. See ``CareerAggregator._crew``.
        """
        return [r for r in self.players()
                if r.get("personageId", "").startswith(AI_ID_PREFIX)]

    def damages(self) -> Dict[str, Dict[str, float]]:
        """Per personage: how much of the aircraft and the pilot was lost."""
        out = {}
        for row in _rows(self.sections.get("damages", "")):
            out[row.get("personageId", "")] = {
                "plane": _number(row.get("plane", "0")),
                "pilot": _number(row.get("pilot", "0")),
            }
        return out

    def objectives(self) -> List[Dict[str, int]]:
        return [{"id": int(_number(r.get("id", "0"))),
                 "coalition": int(_number(r.get("coalition", "0"))),
                 "type": int(_number(r.get("type", "0"))),
                 "state": int(_number(r.get("state", "0")))}
                for r in _rows(self.sections.get("objectives", ""))]

    def coalitions(self) -> List[Dict[str, int]]:
        return [{"id": int(_number(r.get("id", "0"))),
                 "status": int(_number(r.get("missionStatus", "0"))),
                 "points": int(_number(r.get("pointsCount", "0")))}
                for r in _rows(self.sections.get("coalitions", ""))]
