"""
Flight-time corrections: re-timing the missions the player warped through.

The game's own two rules for a sortie's clock disagree. A mission the squadron
flies without the player is not simulated: every pilot is credited the planned
duration and the kills are placed where the briefed route would have put them.
A mission the player flies runs on the player's clock, and when he warps to the
target the whole formation warps with him - a 78-minute plan lands as a
17-minute sortie with every kill in its first ten minutes, and the wingmen
credited half an hour for a return leg nobody flew.

This module applies the AI rule to the player's days. For each mission he flew
it works out, from his own flight log, where the warps were (a fix 215 km from
the previous one, 256 seconds later, is not flying) and how long each skipped
stretch would have taken at the speed the briefing gave that leg. Everything
after a warp shifts by that much; the duration becomes the plan's; pilots who
did not come back keep the time they had. Where the log is gone, the plan
alone is used: the outbound leg's planned time against the first event.

Nothing here writes to the game. The result is a *sidecar* - one JSON per
career under the tracker's own folder - that records, for every corrected
mission, the shifts and both the original and the credited durations. The
tracker applies it on the fly when the user switches corrected times on, and
the Career Helper can push the credited hours into the game file (and take
them back), using the same record. See ``career_helper.py``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

from .assets import default_cache_dir
from .flightlog import FlightLogIndex, _Reader, HEADER
from .geo import parse_route

logger = logging.getLogger(__name__)

FOLDER = default_cache_dir().parent / "corrections"
FORMAT = 1
TIME = "%Y.%m.%d %H:%M:%S"

# A jump between two fixes that no aircraft of 1951 could fly: at least this
# far, at least this fast (an F-86 in a dive stays under 330 m/s).
WARP_MIN_M = 5_000.0
WARP_MIN_MPS = 350.0
# Record types whose payload starts with the aircraft id and a position.
FIX_TYPES = {5, 6, 24, 25, 26, 27, 28, 30, 31}
# A mission counts as warped when it was flown in less than this share of the plan.
THRESHOLD = 0.5


class Warp(NamedTuple):
    at_s: float          # seconds after the sortie start; events at or after shift
    delta_s: float       # by this much


def offset(warps: Iterable[Warp], t_s: float) -> float:
    """A log offset, corrected: plus every warp that happened before it."""
    return t_s + sum(w.delta_s for w in warps if w.at_s <= t_s)


def shift_stamp(warps: Iterable[Warp], start: str, stamp: str) -> str:
    """A 'YYYY.MM.DD HH:MM:SS' event time on the mission clock, corrected."""
    try:
        t0 = dt.datetime.strptime(start, TIME)
        t = dt.datetime.strptime(stamp, TIME)
    except ValueError:
        return stamp
    rel = (t - t0).total_seconds()
    return (t0 + dt.timedelta(seconds=offset(warps, rel))).strftime(TIME)


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------

def path_for(career_name: str) -> Path:
    return FOLDER / f"{career_name}.json"


def load(career_name: str) -> Optional[Dict[str, Any]]:
    p = path_for(career_name)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Corrections for %s unreadable: %s", career_name, exc)
        return None
    if data.get("format") != FORMAT:
        return None
    return data


def save(career_name: str, data: Dict[str, Any]) -> Path:
    FOLDER.mkdir(parents=True, exist_ok=True)
    p = path_for(career_name)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def warps_of(entry: Dict[str, Any]) -> List[Warp]:
    return [Warp(float(w[0]), float(w[1])) for w in entry.get("warps", [])]


# ---------------------------------------------------------------------------
# Reading the player's track out of a log
# ---------------------------------------------------------------------------

def player_fixes(log_path: Path) -> List[Tuple[float, float, float]]:
    """(t_s, x, z) of the human's aircraft, in order, from every record that
    carries its id and a position."""
    player: Optional[int] = None
    fixes: List[Tuple[float, float, float]] = []
    pending: List[Tuple[int, bytes]] = []
    try:
        with open(log_path, "rb") as fh:
            while True:
                head = fh.read(7)
                if len(head) < 7:
                    break
                tick, atype, size = HEADER.unpack(head)
                payload = fh.read(size)
                fh.seek(1, 1)
                if atype == 10 and player is None:
                    try:
                        r = _Reader(payload)
                        plid, _pid = r.int32(), r.int32()
                        r.skip(28)
                        r.string(); r.string(); r.string(); r.string(); r.string()
                        r.skip(12)
                        r.int32()
                        if r.int32() == 1:
                            player = plid
                    except Exception:            # noqa: BLE001 - malformed record
                        pass
                elif atype in FIX_TYPES and len(payload) >= 16:
                    pending.append((tick, payload))
    except OSError as exc:
        logger.warning("Cannot read %s: %s", log_path, exc)
        return []
    if player is None:
        return []
    for tick, payload in pending:
        if struct.unpack_from("<i", payload, 0)[0] != player:
            continue
        x, _y, z = struct.unpack_from("<3f", payload, 4)
        if 0.0 < x < 500_000.0 and 0.0 < z < 500_000.0:
            fixes.append((tick / 50.0, x, z))
    fixes.sort()
    return fixes


def find_warps(fixes: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float, float, float, float]]:
    """(t_before, t_after, x0, z0, x1, z1) for every impossible jump."""
    out = []
    for (t0, x0, z0), (t1, x1, z1) in zip(fixes, fixes[1:]):
        d = math.hypot(x1 - x0, z1 - z0)
        dt_s = t1 - t0
        if d >= WARP_MIN_M and dt_s > 0 and d / dt_s >= WARP_MIN_MPS:
            out.append((t0, t1, x0, z0, x1, z1))
    return out


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def _leg_speed(route: List[Dict[str, Any]], x: float, z: float) -> float:
    """Briefed speed (m/s) of the route leg nearest to a point."""
    best, best_d = None, float("inf")
    for a, b in zip(route, route[1:]):
        ax, az, bx, bz = a["x"], a["z"], b["x"], b["z"]
        vx, vz = bx - ax, bz - az
        L2 = vx * vx + vz * vz
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (z - az) * vz) / L2))
        d = math.hypot(ax + t * vx - x, az + t * vz - z)
        if d < best_d:
            best_d, best = d, b
    speed_kmh = (best or (route[-1] if route else {"speed": 400}))["speed"] or 400.0
    return float(speed_kmh) / 3.6


def _planned_outbound_s(route: List[Dict[str, Any]]) -> float:
    total = 0.0
    for a, b in zip(route, route[1:]):
        v = (b["speed"] or 400.0) / 3.6
        total += math.hypot(b["x"] - a["x"], b["z"] - a["z"]) / v
        if b["type"] == 2:          # the target
            break
    return total


# ---------------------------------------------------------------------------
# Computing the corrections for a career
# ---------------------------------------------------------------------------

def compute(db_path: Path, game_dir: Path, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Corrections for every mission the player flew short of the plan. Entries
    already present in ``existing`` are kept as they are (an applied entry
    must not be recomputed under the game's feet); new missions are added.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    career = con.execute("SELECT * FROM career").fetchone()
    player = career["playerId"]
    logs = FlightLogIndex(game_dir)
    data = existing or {"format": FORMAT, "career": db_path.stem, "missions": {}}
    data["format"] = FORMAT
    data["career"] = db_path.stem
    data["generated"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    missions = data.setdefault("missions", {})

    rows = con.execute(
        "SELECT m.*, s.id AS sortie_id, s.flightTime AS flown, s.date AS sdate "
        "FROM mission m JOIN sortie s ON s.missionId=m.id AND s.pilotId=? "
        "WHERE m.isDeleted=0 AND s.isDeleted=0 ORDER BY m.id", (player,)).fetchall()
    for m in rows:
        key = str(m["id"])
        if key in missions:
            continue
        est = float(m["estDuration"] or 0)
        flown = float(m["flown"] or 0)
        if est <= 0 or flown <= 0 or flown >= est * THRESHOLD:
            continue
        route = parse_route(m["route"])
        start = m["startTime"]
        gap = est - flown
        warps: List[Warp] = []
        source = "plan"

        log = logs.for_sortie(m["sdate"][:10], m["sdate"][11:])
        jumps = find_warps(player_fixes(log.path)) if log else []
        if jumps:
            source = "log"
            for (t0, t1, x0, z0, x1, z1) in jumps:
                d = math.hypot(x1 - x0, z1 - z0)
                v = _leg_speed(route, (x0 + x1) / 2, (z0 + z1) / 2) if route else 400 / 3.6
                warps.append(Warp(round(t1 - 0.5, 1), round(d / v - (t1 - t0), 1)))
            warps = [w for w in warps if w.delta_s > 0]
        if not warps:
            # No usable log: the outbound leg at briefed speed, against the
            # first thing that happened, and the rest on the way home.
            first = con.execute(
                "SELECT MIN(date) FROM event WHERE missionId=? AND isDeleted=0 AND type=0",
                (m["id"],)).fetchone()[0]
            try:
                first_s = (dt.datetime.strptime(first, TIME) - dt.datetime.strptime(start, TIME)).total_seconds()
            except (TypeError, ValueError):
                first_s = flown / 2
            out_s = _planned_outbound_s(route) if route else est / 2
            d1 = max(0.0, min(gap, out_s - first_s))
            warps = [Warp(0.0, round(d1, 1)), Warp(round(flown, 1), round(gap - d1, 1))]
        # The plan is the credited duration, so the last warp absorbs the
        # difference between the skipped legs at briefed speed and the game's
        # own allowance for start-up, climb, pattern and landing.
        total = sum(w.delta_s for w in warps)
        if total <= 0:
            continue
        adjust = gap - total
        last = warps[-1]
        warps[-1] = Warp(last.at_s, round(max(0.0, last.delta_s + adjust), 1))
        if adjust < 0 and warps[-1].delta_s == 0.0:
            scale = gap / total
            warps = [Warp(w.at_s, round(w.delta_s * scale, 1)) for w in warps]

        durations: Dict[str, Dict[str, float]] = {}
        for s in con.execute("SELECT id, pilotId, status, flightTime FROM sortie "
                             "WHERE missionId=? AND isDeleted=0", (m["id"],)):
            orig = float(s["flightTime"] or 0)
            if s["status"] in (2, 3):
                credited = offset(warps, orig)          # lost: his own time, shifted
            else:
                credited = est
            if credited > orig:
                durations[str(s["id"])] = {"pilot": s["pilotId"], "orig": orig,
                                           "credited": round(credited, 1)}
        try:
            end_credited = (dt.datetime.strptime(start, TIME)
                            + dt.timedelta(seconds=est)).strftime(TIME)
        except ValueError:
            end_credited = m["endTime"]
        missions[key] = {
            "start": start,
            "date": m["date"],
            "planned_s": est,
            "flown_s": flown,
            "source": source,
            "warps": [[w.at_s, w.delta_s] for w in warps],
            "durations": durations,
            "end_time": {"orig": m["endTime"], "credited": end_credited},
            "applied": False,
        }
    con.close()
    return data


# ---------------------------------------------------------------------------
# Pushing the hours into the game file, and taking them back
# ---------------------------------------------------------------------------

def apply_hours(db_path: Path, data: Dict[str, Any], mission_ids: Iterable[str]) -> List[str]:
    """Write the credited durations for the given missions. The caller backs
    up first and holds the sidecar; returns the ids actually applied."""
    import sqlite3
    done: List[str] = []
    con = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        before = [r[0] for r in con.execute("SELECT id FROM award WHERE isDeleted=0")]
        for key in mission_ids:
            entry = data["missions"].get(key)
            if not entry or entry.get("applied"):
                continue
            total = 0.0
            for sid, d in entry["durations"].items():
                current = con.execute("SELECT flightTime FROM sortie WHERE id=?", (int(sid),)).fetchone()
                if current is None or abs(float(current[0] or 0) - d["orig"]) > 0.5:
                    continue                    # changed since it was computed: leave it
                delta = d["credited"] - d["orig"]
                con.execute("UPDATE sortie SET flightTime=? WHERE id=?", (int(round(d["credited"])), int(sid)))
                con.execute("UPDATE pilot SET flightTime = flightTime + ? WHERE id=?", (int(round(delta)), d["pilot"]))
                total += delta
            con.execute("UPDATE squadron SET flightTime = flightTime + ?", (int(round(total)),))
            con.execute("UPDATE mission SET endTime=? WHERE id=? AND endTime=?",
                        (entry["end_time"]["credited"], int(key), entry["end_time"]["orig"]))
            entry["applied"] = True
            entry["applied_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry["awards_before"] = before
            done.append(key)
        con.commit()
    finally:
        con.close()
    return done


def restore_hours(db_path: Path, data: Dict[str, Any], mission_ids: Iterable[str]) -> List[str]:
    """Put the game's own durations back for the given applied missions."""
    import sqlite3
    done: List[str] = []
    con = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        for key in mission_ids:
            entry = data["missions"].get(key)
            if not entry or not entry.get("applied"):
                continue
            total = 0.0
            for sid, d in entry["durations"].items():
                delta = d["credited"] - d["orig"]
                con.execute("UPDATE sortie SET flightTime=? WHERE id=?", (int(round(d["orig"])), int(sid)))
                con.execute("UPDATE pilot SET flightTime = flightTime - ? WHERE id=?", (int(round(delta)), d["pilot"]))
                total += delta
            con.execute("UPDATE squadron SET flightTime = flightTime - ?", (int(round(total)),))
            con.execute("UPDATE mission SET endTime=? WHERE id=?", (entry["end_time"]["orig"], int(key)))
            entry["applied"] = False
            entry.pop("applied_at", None)
            done.append(key)
        con.commit()
    finally:
        con.close()
    return done


def awards_since_apply(db_path: Path, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Award rows granted after the earliest apply still in force."""
    import sqlite3
    before: Optional[set] = None
    for entry in data.get("missions", {}).values():
        if entry.get("applied") and "awards_before" in entry:
            ids = set(entry["awards_before"])
            before = ids if before is None else (before & ids)
    if before is None:
        return []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT id, pilotId, type, earnedDate FROM award WHERE isDeleted=0 ORDER BY id")
        if r["id"] not in before]
    con.close()
    return rows


def withdraw_award(db_path: Path, award_id: int) -> None:
    """
    Take one award back: the row, its events, and - if it retired a lower
    rung of the same ladder when it was granted - that rung comes back. The
    type-20 events with ipar3=2 say exactly which rows were retired.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=1.0)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM award WHERE id=?", (award_id,)).fetchone()
        if row is None:
            return
        pilot = row["pilotId"]
        # Rows retired at the moment this one was granted, for the same pilot.
        granted_at = con.execute(
            "SELECT MIN(date) FROM event WHERE type=20 AND ipar1=? AND pilotId=?",
            (award_id, pilot)).fetchone()[0]
        retired = con.execute(
            "SELECT DISTINCT ipar1 FROM event WHERE type=20 AND ipar3=2 AND pilotId=? AND date=?",
            (pilot, granted_at)).fetchall() if granted_at else []
        for r in retired:
            rid = r[0]
            if rid != award_id:
                con.execute("UPDATE award SET isDeleted=0 WHERE id=?", (rid,))
                con.execute("UPDATE event SET isDeleted=1 WHERE type=20 AND ipar1=? AND ipar3=2", (rid,))
        con.execute("UPDATE event SET isDeleted=1 WHERE type=20 AND ipar1=?", (award_id,))
        con.execute("UPDATE award SET isDeleted=1 WHERE id=?", (award_id,))
        con.commit()
    finally:
        con.close()
