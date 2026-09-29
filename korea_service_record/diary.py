"""
The squadron's war diary: the career told day by day.

Everything here is assembled out of rows the game wrote. Nothing is
invented and nothing is inferred beyond what ``career/events.py`` has
already proven about each event type - a diary whose whole worth is that
it happened cannot afford a single embellishment.

**Why the events cannot simply be listed.** The career this was built
against holds 2,883 events over 23 days, but the distribution is savage:
the median day carries 3 and 7 April carries 1,186. Two types cause that
almost entirely - ``kill`` (1,036 rows, one per object destroyed) and
``award`` (1,718, one per decoration considered for every pilot on the
roster). Printed one to a line they would bury the four rows that
actually tell you something happened. So those two are counted, and the
count is attached to the mission or the day it belongs to, while the rare
types - a man lost, a man wounded, an operation opening - each get their
own line. A day is then three to ten lines, and a five-week tour reads in
a few minutes.

**An award event is not an award.** Of those 1,718 rows, 244 are grants,
229 presentations and **1,245 removals** - 915 of them on 23 April alone.
A removal is the bookkeeping behind a cluster replacing the decoration it
supersedes (the ``AwardRemove`` mechanism), not something that happened to
anybody, so the diary drops them: counting all three together would have
had the squadron decorated 99 times on a day it was decorated 29. Grants
and presentations are counted separately, because earning a medal and
being handed it are different days, and the player's own are named.

**Every line is emitted as facts plus a key**, never as a finished
sentence, the same way ``_incidences`` does it. The server does not know
how German orders a clause or how Russian declines a name, so it hands
the page ``{key, count, names}`` and the page builds the sentence from
its own locale file. The English ``label`` beside each key is a fallback
for anything a translation has not caught up with, not the primary text.
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from . import ribbons as ribbon_art
from .career.events import describe

# Counted, never listed: see the module docstring.
TALLIED = {"kill"}

# event.ipar3 on an award row
GRANTED, PRESENTED, REMOVED = 0, 1, 2

# The game writes some casualty rows twice. Maurice Dillard's F-51D on
# 1951.04.18 is events 1041 and 1042 - same second, same mission, same
# pilot - and he flew one sortie that mission, ending planeStatus 3. Bryan
# Bickle on 1951.05.01 is the same (2528, 2529). Winton White, killed on
# that sortie, and the player, who walked away from it, each get one row,
# so whatever causes the doubling it is not a second aircraft. Only the
# types where a repeat in the same second cannot mean anything are folded:
# two kill rows at one timestamp really are two objects.
UNREPEATABLE = {"plane_lost", "pilot_kia", "pilot_missing", "wounded",
                "medical", "friendly_destroyed"}

# Types whose ipar1 is 0 = begins, 1 = ends. An aircraft going into the
# shop and coming out again are one event each, and a diary wants the
# going-in; a repair that finishes is worth a line of its own only
# because it puts an aeroplane back on the line.
PHASED = {"medical", "plane_repair", "operation", "transfer"}

# event type 33, ipar2 on the closing row - the game's own
# carEventOperationSuccess / Failure / Missed. career/operations.py reads the
# same three codes out of the squadron's tally.
OPERATION_END = {
    1: "operation_end_success",
    2: "operation_end_failure",
    3: "operation_end",
}


def _who(names: Dict[int, str], pilot_id: Optional[int]) -> str:
    """A pilot's name, or empty for the squadron-wide rows (pilotId -1)."""
    if pilot_id is None or pilot_id < 0:
        return ""
    return names.get(pilot_id, "")


def _entry(key: str, label: str, **fields) -> Dict[str, Any]:
    row = {"key": "diary." + key, "label": label}
    row.update({k: v for k, v in fields.items() if v not in ("", None, [], 0)})
    return row


class DiaryBuilder:
    """
    Builds the day entries for one career.

    Takes the aggregator rather than inheriting from it: the diary needs
    its object names, its mission-type names and its place resolver, and
    borrowing three methods is cheaper than moving them.
    """

    def __init__(self, agg, db, today: str = ""):
        self.agg = agg
        self.db = db
        self.today = today
        self.names = {p["id"]: f"{p['name']} {p['lastName']}".strip()
                      for p in db.pilots(True)}
        self.player = db.player()
        self.player_id = self.player["id"] if self.player else -1

    # -- missions ----------------------------------------------------------

    def _missions(self, features) -> Dict[str, List[Dict[str, Any]]]:
        """Every mission the squadron flew, filed under its date."""
        by_day: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        flown = {s["missionId"] for s in self.db.sorties(self.player_id)}
        # Kills are counted per mission, not per day: a day with three
        # sorties should say which of them did the damage.
        kills = Counter(r["missionId"] for r in self.db.events()
                        if describe(r["type"]).key == "kill")
        for m in self.db.missions():
            # An unscheduled sortie is numbered -1, -2 downwards, which is
            # the game's way of keeping it out of the mission count rather
            # than a number to show anybody. Both rows carrying one in the
            # reference career also have isEmergency set, and their times
            # match the type-31 events exactly.
            row = {
                "id": m["id"],
                "num": m["missionNum"] if m["missionNum"] > 0 else None,
                "time": (m["startTime"] or "")[11:16],
                "type": self.agg.locale.mission_type_name(m["type"]),
                "place": self.agg.place_of(self.db, m, features),
                "targets": kills.get(m["id"], 0),
                "player": m["id"] in flown,
            }
            if m["isEmergency"]:
                row["emergency"] = True
            # state 1 is a mission that was actually flown and resolved;
            # objSuccess/objFailure are the objective counts behind it.
            if m["state"] == 1:
                row["objectives"] = {"met": m["objSuccess"] or 0,
                                     "missed": m["objFailure"] or 0}
            by_day[m["date"]].append(row)
        for day in by_day.values():
            day.sort(key=lambda r: (r["time"], r["num"]))
        return by_day

    # -- the rest of the day -----------------------------------------------

    def _notes(self, rows) -> Tuple[List[Dict[str, Any]], Counter]:
        """
        One day's events, as lines.

        Arrivals are gathered into one line because five men reporting on
        the same morning is one event in the life of a squadron, not five.
        Losses are never gathered: each of those is a name the diary owes
        a line to.
        """
        out: List[Dict[str, Any]] = []
        arrivals: List[str] = []
        mine: Dict[int, set] = {}
        delivered = 0
        repairs_begun = 0
        repairs_done = 0
        tally: Counter = Counter()

        seen = set()
        for r in sorted(rows, key=lambda x: (x["date"], x["id"])):
            info = describe(r["type"])
            key, who = info.key, _who(self.names, r["pilotId"])
            if key in UNREPEATABLE:
                fingerprint = (key, r["pilotId"], r["date"], r["missionId"])
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
            phase = r["ipar1"] if info.key in PHASED else None

            if key in TALLIED:
                tally[key] += 1
                continue
            if key in ("award", "promotion"):
                action = r["ipar3"]
                if action == REMOVED:
                    continue                       # bookkeeping, not an event
                tally["presented" if action == PRESENTED else "granted"] += 1
                if r["pilotId"] == self.player_id:
                    # The reader's own thread through the diary. ipar2 is
                    # the award type; ipar1 is the row in the award table.
                    mine.setdefault(r["ipar2"], set()).add(action)
                continue
            if key == "reported":
                arrivals.append(who)
            elif key == "plane_delivered":
                delivered += 1
            elif key == "plane_repair":
                if phase == 1:
                    repairs_done += 1
                else:
                    repairs_begun += 1
            elif key == "operation":
                name = self._operation(r["tpar1"])
                if phase != 1:
                    out.append(_entry("operation_begin", "Begun: " + name,
                                      name=name))
                else:
                    # ipar2 says how it went, and the game names all three
                    # outcomes itself. Rendering them alike would throw away
                    # the only verdict a squadron gets on a week's work.
                    kind = OPERATION_END.get(r["ipar2"], "operation_end")
                    out.append(_entry(kind, "Ended: " + name, name=name))
            elif key == "pilot_kia":
                out.append(_entry("pilot_kia", f"{who} killed in action", who=who))
            elif key == "pilot_missing":
                out.append(_entry("pilot_missing", f"{who} missing in action", who=who))
            elif key == "wounded":
                out.append(_entry("wounded", f"{who} wounded in action",
                                  who=who, health=r["ipar2"]))
            elif key == "medical":
                out.append(_entry(
                    "returned_to_duty" if phase == 1 else "to_hospital",
                    f"{who} returned to duty" if phase == 1
                    else f"{who} taken to hospital", who=who))
            elif key == "plane_lost":
                out.append(_entry("plane_lost", f"{who} lost his aircraft", who=who))
            elif key == "friendly_destroyed":
                described = self.agg.objects.describe(r["tpar1"])
                what = described["name"] if described["named"] else r["tpar1"]
                out.append(_entry("friendly_destroyed",
                                  f"{who} destroyed a friendly {what}",
                                  who=who, what=what))
            elif key == "commander_assigned":
                out.append(_entry("commander_assigned",
                                  f"{who} took command", who=who))
            elif key == "successor":
                out.append(_entry("successor", f"{who} took over the career",
                                  who=who))
            elif key == "unit_award":
                out.append(_entry("unit_award", "The squadron was cited"))
            elif key == "efficiency":
                # ipar1 is the new rating, ipar2 the direction; the rating
                # alone is what a reader can do anything with.
                out.append(_entry("efficiency", f"Squadron efficiency now {r['ipar1']}",
                                  value=r["ipar1"]))
            elif key == "resources_destroyed":
                out.append(_entry("resources_destroyed",
                                  "The airfield's stores were hit",
                                  fuel=r["ipar1"], ammo=r["ipar2"], parts=r["ipar3"]))
            elif key == "transfer":
                # ipar1 = 0 the move is ordered, 1 the squadron has arrived.
                field = self._airfield(r["tpar1"])
                out.append(_entry(
                    "transfer_done" if phase == 1 else "transfer_ordered",
                    (f"The squadron is now at {field}" if phase == 1
                     else f"Ordered to move to {field}"), field=field))
            elif key == "emergency_mission":
                continue            # the mission row already carries this
            elif key == "request_points":
                continue            # folded into the mission it belongs to

        if arrivals:
            out.insert(0, _entry("reported",
                                 f"{len(arrivals)} reported for duty",
                                 names=arrivals, count=len(arrivals)))
        if delivered:
            out.append(_entry("plane_delivered",
                              f"{delivered} aircraft delivered", count=delivered))
        if repairs_begun:
            out.append(_entry("plane_repair",
                              f"{repairs_begun} aircraft under repair",
                              count=repairs_begun))
        if repairs_done:
            out.append(_entry("plane_repaired",
                              f"{repairs_done} aircraft back on the line",
                              count=repairs_done))
        # His own decorations last, one line each. The game commonly grants
        # and presents the same medal on the same day - there were three
        # such pairs in the reference career - and two lines saying so is
        # one event reported twice.
        for award_id, actions in mine.items():
            both = {GRANTED, PRESENTED} <= actions
            name = self.agg.award_name(award_id)
            key = ("own_both" if both
                   else "own_presented" if PRESENTED in actions else "own_granted")
            label = {"own_both": f"You earned and were presented with the {name}",
                     "own_presented": f"You were presented with the {name}",
                     "own_granted": f"You earned the {name}"}[key]
            # Not every decoration has a ribbon: the Pilot's Badge is worn
            # above them, not among them, and `/api/ribbon/` has nothing
            # for it. The page shows the atlas icon for those instead of
            # asking for a picture that does not exist.
            out.append(_entry(key, label, award=name, award_id=award_id,
                              ribbon=award_id in ribbon_art.RIBBONS))
        return out, tally

    # -- names -------------------------------------------------------------

    @staticmethod
    def _operation(raw: Optional[str]) -> str:
        """
        The operation's name as the game stores it, minus its side prefix.

        "WB" and "EB" are Western Bloc and Eastern Bloc, not a build tag:
        scg/2/operations.cfg defines each historical operation twice, an odd
        id for the west listing countries 601/602/603 and the even id after
        it for the east listing 501/502/503. So "WB Operation Rugged" and
        "EB Countering Operation Rugged" are the same week from either side.

        Only the prefix goes - the east's "Countering ..." is part of the
        name. Anything without a prefix is left alone.
        """
        name = (raw or "").strip()
        for prefix in ("WB ", "EB "):
            if name.startswith(prefix):
                return name[len(prefix):].strip()
        return name

    @staticmethod
    def _airfield(raw: Optional[str]) -> str:
        """"K-16_Seoul" as "K-16 Seoul"."""
        return (raw or "").replace("_", " ").strip()

    # -- the whole thing ---------------------------------------------------

    def build(self) -> Dict[str, Any]:
        features = self.agg.overlay.features()
        missions = self._missions(features)
        by_day: Dict[str, List] = defaultdict(list)
        for r in self.db.events():
            by_day[r["date"][:10]].append(r)

        days = []
        for date in sorted(set(by_day) | set(missions)):
            # A diary is written up to today and no further. The game
            # schedules the far side of a squadron move before it happens -
            # the reference career stands on 7 May with "the squadron is now
            # at K-16 Seoul" already written against the 8th - and a diary
            # that records tomorrow is not a diary.
            if self.today and date > self.today:
                break
            notes, tally = self._notes(by_day.get(date, []))
            day = {"date": date,
                   "missions": missions.get(date, []),
                   "notes": notes}
            # The two tallied types, and only where they are not zero: a
            # line reading "0 decorations granted" is worse than silence.
            if tally.get("granted"):
                day["granted"] = tally["granted"]
            if tally.get("presented"):
                day["presented"] = tally["presented"]
            if tally.get("kill") and not missions.get(date):
                # Kills normally hang off a mission. Any left over belong
                # to the day itself rather than being dropped.
                day["targets"] = tally["kill"]
            days.append(day)
        return {"days": days}
