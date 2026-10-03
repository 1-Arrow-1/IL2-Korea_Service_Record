"""
Restores the sortie rows the 29 September 2026 build threw away.

Build 25605106 lists a column ``escapedJail`` in its sortie INSERT that no
career file has, so every sortie of a mission flown on it failed to save. The
mission row survived, and with it ``mission.result`` - the full debrief - and
``pilotsList``; the kill rows in ``event`` survived too. Pilot and squadron
totals were updated as usual, so only the sortie rows are missing.

Every field of a sortie row can be rebuilt from what survived. Verified on
2026-10-02 against all 701 sorties of the 97 missions in six careers that
have both a debrief and real rows: every field matched on every sortie.

    pilotId, planeId   pilotsList, in slot order; the human's debrief row
                       (a real account guid) is slot 0, the AI rows
                       ...200000000000 to ...800000000000 the rest in order
    isPlayer           the human's row
    score              pointsSumByMission
    killStats          the debrief's kill* counters, keys as the game writes
                       them (alphabetical; the Raildoad typo kept)
    assistCount, fkill assistCount, friendlyKillCount
    flightTime         totalFlightTime
    date               mission.startTime
    rankId             the pilot's rank now, less every promotion presented
                       (type 19, ipar3=1) after that date
    eventFlags         ipar1 of the mission's type-35 event for the pilot
    status, health     type 3 killed (2, 0) / type 4 missing (3, 100) /
                       type 5 wounded (4, ipar2); status 1 from a type-36
                       event after the update, from ejectStatus before it
    planeStatus,       type-2 loss, or killed with group-state plane health
    planeHealth        0 (3, 0); group-state plane health below 99 where the
                       debrief's planeStatus is 1; a repair (type 18,
                       ipar1=0) starting within 2 min of the mission end
                       (2, ipar2); debrief damage of 1% or more (2, rounded);
                       else (0, 100)

Four of those rules were fitted on the same data (the repair window, the 1%
threshold, the status-1 era rule, the group-state condition), so a 100% match
there is weaker evidence than a prediction would be.

Runs by itself when the tracker reads a career, before the napalm correction,
and writes only when a mission has lost its sorties. If the career carries a
napalm record (napalmfix.py), the pilot and squadron offsets there already
hold these sorties' kills - they were part of the stored totals but of no
sortie row - so they are lowered by the restored kills in the same
transaction; the napalm run that follows then corrects the restored rows like
any other. ``restore()`` deletes the restored rows and puts the offsets back.
"""

import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import corrections

logger = logging.getLogger(__name__)

FORMAT = 1
AI_ID_PREFIX = "00000000-0000-0000-0000-"
TIME = "%Y.%m.%d %H:%M:%S"


# -- the record -------------------------------------------------------------

def path_for(career_name: str) -> Path:
    return corrections.FOLDER / f"{career_name}.recovered.json"


def load(career_name: str) -> Optional[Dict[str, Any]]:
    p = path_for(career_name)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Unreadable recovery record %s: %s", p, exc)
        return None


def save(career_name: str, data: Dict[str, Any]) -> Path:
    corrections.FOLDER.mkdir(parents=True, exist_ok=True)
    p = path_for(career_name)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


# -- rebuilding -------------------------------------------------------------

def _num(value: Optional[str], default: float = 0.0) -> float:
    from .career.missionresult import _unquote
    try:
        return float(_unquote(value)) if value not in (None, "") else default
    except ValueError:
        return default


def _kills(player: Dict[str, str]) -> str:
    counts = {}
    for key, value in player.items():
        if key.startswith("kill"):
            n = int(_num(value))
            if n:
                counts[key[4:]] = n
    return "&".join(f"{k}={counts[k]}" for k in sorted(counts))


def lost_missions(con: sqlite3.Connection) -> List[sqlite3.Row]:
    """Missions with a debrief that lists pilots and not one sortie row."""
    out = []
    for m in con.execute("""SELECT * FROM mission WHERE isDeleted = 0
                            AND result LIKE '%players=%' AND pilotsList <> ''
                            ORDER BY id"""):
        if con.execute("SELECT 1 FROM sortie WHERE missionId = ? LIMIT 1", (m["id"],)).fetchone() is None:
            out.append(m)
    return out


def _rank_on(con: sqlite3.Connection, pilot_id: int, date: str) -> int:
    row = con.execute("SELECT rankId FROM pilot WHERE id = ?", (pilot_id,)).fetchone()
    if row is None:
        return 0
    later = con.execute("""SELECT COUNT(*) FROM event WHERE type = 19 AND ipar3 = 1
                           AND pilotId = ? AND date > ? AND isDeleted = 0""", (pilot_id, date)).fetchone()[0]
    return int(row[0]) - int(later)


def _fate(con, m, pilot_id, plane_id, player, group, result) -> Dict[str, int]:
    events = {}
    for typ, ipar2 in con.execute("""SELECT type, ipar2 FROM event WHERE missionId = ? AND pilotId = ?
                                     AND type IN (2, 3, 4, 5, 36) AND isDeleted = 0""",
                                  (m["id"], pilot_id)):
        events[typ] = ipar2
    end = m["endTime"] or m["startTime"]
    try:
        until = (dt.datetime.strptime(end, TIME) + dt.timedelta(seconds=120)).strftime(TIME)
    except (TypeError, ValueError):
        until = end
    repair = con.execute("""SELECT ipar2 FROM event WHERE type = 18 AND ipar1 = 0 AND planeId = ?
                            AND date >= ? AND date <= ? AND isDeleted = 0 ORDER BY id LIMIT 1""",
                         (plane_id, end, until)).fetchone()
    post_update = con.execute("""SELECT 1 FROM event WHERE type IN (35, 36) AND missionId <= ?
                                 AND isDeleted = 0 LIMIT 1""", (m["id"],)).fetchone() is not None
    ejected = (player.get("ejectStatus") or "0") not in ("0", "")

    if 3 in events:
        status, health = 2, 0
    elif 4 in events:
        status, health = 3, 100
    elif 5 in events:
        status, health = 4, int(events[5])
    elif (36 in events) if post_update else ejected:
        status, health = 1, 100
    else:
        status, health = 0, 100

    damage = result.damages().get(player.get("personageId", ""), {}).get("plane", 0)
    group_plane = int(_num(group.get("planeHealth"), 100)) if group else 100
    if 2 in events or (3 in events and group and group_plane == 0):
        plane_status, plane_health = 3, 0
    elif 0 < group_plane < 99 and (player.get("planeStatus") or "0") == "1":
        plane_status, plane_health = 2, group_plane
    elif repair is not None:
        plane_status, plane_health = 2, int(repair[0])
    elif damage >= 0.01:
        plane_status, plane_health = 2, round(100 * (1 - damage))
    else:
        plane_status, plane_health = 0, 100
    return {"status": status, "health": health, "planeStatus": plane_status, "planeHealth": plane_health}


def rebuild(con: sqlite3.Connection, m: sqlite3.Row) -> List[Dict[str, Any]]:
    """The sortie rows of one mission, in slot order, as the game would write them."""
    from .career.missionresult import MissionResult, _rows, _unquote
    from .loadouts import parse_pilots_list

    result = MissionResult(m["result"])
    slots = parse_pilots_list(m["pilotsList"])
    players = result.players()
    groups = {_unquote(g.get("personageId", "")): g
              for g in _rows(result.sections.get("playerGroupState", ""))}
    human = [p for p in players if not p.get("personageId", "").startswith(AI_ID_PREFIX)]
    ai = sorted((p for p in players if p.get("personageId", "").startswith(AI_ID_PREFIX)),
                key=lambda p: p["personageId"])
    pairs = [(slots[0], human[0], 1)] if human and slots else []
    pairs += [(s, p, 0) for s, p in zip(slots[1:] if human else slots, ai)]
    flags = {pid: ipar1 for pid, ipar1 in con.execute(
        "SELECT pilotId, ipar1 FROM event WHERE type = 35 AND missionId = ? AND isDeleted = 0", (m["id"],))}
    rows = []
    for slot, player, is_player in pairs:
        pid, plane = slot["pilot_id"], slot.get("plane_id")
        row = {
            "missionId": m["id"], "pilotId": pid, "planeId": plane,
            "rankId": _rank_on(con, pid, m["startTime"]), "isPlayer": is_player,
            "score": int(_num(player.get("pointsSumByMission"))),
            "killStats": _kills(player),
            "assistCount": int(_num(player.get("assistCount"))),
            "fkill": int(_num(player.get("friendlyKillCount"))),
            "flightTime": int(_num(player.get("totalFlightTime"))),
            "date": m["startTime"], "eventFlags": int(flags.get(pid, 0)), "returnTime": 0,
        }
        row.update(_fate(con, m, pid, plane, player, groups.get(player.get("personageId", "")), result))
        rows.append(row)
    return rows


def plan(db_path: Path) -> Dict[int, List[Dict[str, Any]]]:
    """
    Mission id -> the rows to restore. Reads only. A mission that rebuilds to
    nothing - a debrief without rows the slots can pair with - is left out, or
    it would stay "lost" and be retried, and backed up, on every read.
    """
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        out = {}
        for m in lost_missions(con):
            rows = rebuild(con, m)
            if rows:
                out[m["id"]] = rows
        return out
    finally:
        con.close()


# -- writing ----------------------------------------------------------------

_COLUMNS = ("missionId", "pilotId", "planeId", "rankId", "isPlayer", "score", "status", "health",
            "planeStatus", "planeHealth", "killStats", "assistCount", "fkill", "flightTime",
            "date", "insDate", "isDeleted", "eventFlags", "returnTime")


def _shift_napalm(napalm: Optional[Dict[str, Any]], entry: Dict[str, Any], sign: int) -> None:
    """Move one restored mission's kills into (-1) or out of (+1) the napalm offsets."""
    from .napalmfix import _parse
    if not napalm:
        return
    for pid, kills in entry["kills"].items():
        for key, n in _parse(kills).items():
            if pid in napalm.get("pilots", {}):
                napalm["pilots"][pid][key] = napalm["pilots"][pid].get(key, 0) + sign * n
            if napalm.get("squadron") is not None:
                napalm["squadron"][key] = napalm["squadron"].get(key, 0) + sign * n
    if sign > 0:
        for sid in entry["sorties"]:
            napalm.get("sorties", {}).pop(str(sid), None)


def _save_both(name: str, data: Dict[str, Any], napalm: Optional[Dict[str, Any]]) -> None:
    from .napalmfix import save as napalm_save
    if napalm:
        napalm_save(name, napalm)
    save(name, data)


def apply(db_path: Path, backup: bool = False) -> Dict[str, Any]:
    """
    Insert every lost mission's rows in one transaction. The write lock is
    taken first and the plan made inside it; with ``backup`` the file is
    copied under that lock, and only when there is something to insert. Both
    records are saved before the commit and put back if the commit fails, so
    the napalm offsets never move without the rows they account for.
    """
    from .napalmfix import load as napalm_load

    name = Path(db_path).stem
    data = load(name) or {"format": FORMAT, "career": name, "missions": {}}
    napalm = napalm_load(name)
    before = (json.dumps(data), json.dumps(napalm) if napalm else None)
    restored = missions = 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")   # the game writes insDate in UTC
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        todo = plan(db_path)
        if not todo:
            con.rollback()
            return {"missions": 0, "sorties": 0}
        if backup:
            corrections.backup(Path(db_path))
        for mission_id, rows in todo.items():
            if con.execute("SELECT 1 FROM sortie WHERE missionId = ? LIMIT 1", (mission_id,)).fetchone():
                continue                     # restored by someone else in the meantime
            entry = {"sorties": [], "kills": {}}
            for row in rows:
                row = dict(row, insDate=stamp, isDeleted=0)
                cur = con.execute(f"INSERT INTO sortie ({', '.join(_COLUMNS)}) VALUES "
                                  f"({', '.join('?' * len(_COLUMNS))})", [row[c] for c in _COLUMNS])
                entry["sorties"].append(cur.lastrowid)
                entry["kills"][str(row["pilotId"])] = row["killStats"]
                restored += 1
            data["missions"][str(mission_id)] = entry
            missions += 1
            # The napalm offsets were taken when these kills were in the totals
            # but in no sortie row; now that they are in one, take them out.
            _shift_napalm(napalm, entry, -1)
        data["auto"] = True
        data["applied_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_both(name, data, napalm)
        try:
            con.commit()
        except sqlite3.Error:
            _save_both(name, json.loads(before[0]), json.loads(before[1]) if before[1] else None)
            raise
    finally:
        con.close()
    return {"missions": missions, "sorties": restored}


def restore(db_path: Path) -> int:
    """Delete every restored row, put the napalm offsets back, stop the automatic run."""
    from .napalmfix import load as napalm_load

    name = Path(db_path).stem
    data = load(name)
    if not data:
        return 0
    napalm = napalm_load(name)
    before = (json.dumps(data), json.dumps(napalm) if napalm else None)
    removed = 0
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        for entry in data.get("missions", {}).values():
            for sid in entry["sorties"]:
                removed += con.execute("DELETE FROM sortie WHERE id = ?", (sid,)).rowcount
            _shift_napalm(napalm, entry, +1)
        data["missions"] = {}
        data["auto"] = False
        _save_both(name, data, napalm)
        try:
            con.commit()
        except sqlite3.Error:
            _save_both(name, json.loads(before[0]), json.loads(before[1]) if before[1] else None)
            raise
    finally:
        con.close()
    return removed


def _rolled_back(db_path: Path, data: Dict[str, Any]) -> bool:
    """
    Rows this module inserted are gone again. The game never deletes sortie
    rows, so a backup has been put back over the file: the player undoing
    the recovery, which must not be redone.
    """
    ids = [sid for entry in data.get("missions", {}).values() for sid in entry["sorties"]]
    if not ids:
        return False
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        found = con.execute(f"SELECT COUNT(*) FROM sortie WHERE id IN ({','.join('?' * len(ids))})",
                            ids).fetchone()[0]
    finally:
        con.close()
    return found < len(ids)


def auto_sync(db_path: Path) -> Optional[Dict[str, Any]]:
    """
    Called whenever the tracker reads a career, before the napalm correction.
    Plans read-only and takes the write lock only when a mission really has
    rows to restore. A career put back from a backup is left alone for good,
    and the napalm offsets lose the restored kills the file no longer has.
    """
    from .napalmfix import load as napalm_load

    name = Path(db_path).stem
    data = load(name) or {}
    if data.get("auto") is False:
        return None
    try:
        if _rolled_back(db_path, data):
            napalm = napalm_load(name)
            for entry in data["missions"].values():
                _shift_napalm(napalm, entry, +1)
            data["missions"] = {}
            data["auto"] = False
            _save_both(name, data, napalm)
            logger.info("Sortie recovery: %s was put back from a backup - switched off", name)
            return None
        pending = plan(db_path)
    except sqlite3.Error as exc:
        logger.info("Sortie recovery: %s not readable now (%s)", name, exc)
        return None
    if not pending:
        return None
    try:
        result = apply(db_path, backup=True)
    except sqlite3.OperationalError as exc:
        logger.info("Sortie recovery: %s is in use, will retry (%s)", name, exc)
        return None
    if result["sorties"]:
        logger.info("Sortie recovery on %s: %s", name, result)
    return result if result["sorties"] else None
