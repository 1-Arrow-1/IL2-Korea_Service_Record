"""
Takes the napalm re-kills back out of the career file itself.

Since the game build of 29 September 2026, napalm burning on an airfield's
block group books the same destroyed part again every 2 seconds for the fire's
~178 s life (killfix.py has the evidence). The career processor adds every one
of those kills to ``sortie.killStats``, from there to ``pilot.killStats`` and
``squadron.killStats``, and through the points formula to ``score`` and
``pcp``. The mod's awards read the totals (``GrObj``, ``BldObj``) and its
promotions read ``pcp``, so both were being paid on kills that never happened.

This rewrites, whenever the tracker reads a career and only when something
differs, with a backup first:

* every inflated ``sortie.killStats`` to the count rebuilt from its kill rows
  (killfix.reductions - one row per destroyed object, categorised by the
  game's own statobjects.json);
* ``pilot.killStats`` and ``squadron.killStats`` to ``offset + the sum of the
  corrected sorties``. The offset is the stored total minus the sum of the
  original sorties, taken once before anything is written: it holds what the
  sortie rows do not, such as the two sorties the escapedJail bug never saved
  in the 12th FBS career;
* ``pilot.pcp`` to ``score + gap - excess``. The game adds the same points to
  score and PCP (FUN_18006b690), so ``gap = pcp - score`` is fixed for life
  (46 of 46 pilots); the excess is the points formula replayed over the
  original sorties minus the same replay over the corrected ones. The score
  itself stays the game's.

Every target is recomputed from scratch, never from the value in the file, so
nothing is ever taken off twice and a value the game writes back from memory
is simply corrected again on the next read. The record of original sortie
values, offsets and gaps lives beside the flight-time record; ``restore()``
puts the game's own values back and stops the automatic run for that career.

What it cannot do: the debrief of the napalm sortie itself is evaluated by the
game before the tracker sees it. awards.cfg guards that debrief with
``(BldObjSortie<60)&(GrObjSortie<60)`` on every award that counts ground kills.
"""

import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import corrections

logger = logging.getLogger(__name__)

FORMAT = 1

# PCP is written %.2f.
_EPS = 0.005


# -- the record -------------------------------------------------------------

def path_for(career_name: str) -> Path:
    return corrections.FOLDER / f"{career_name}.napalm.json"


def load(career_name: str) -> Optional[Dict[str, Any]]:
    p = path_for(career_name)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Unreadable napalm record %s: %s", p, exc)
        return None


def save(career_name: str, data: Dict[str, Any]) -> Path:
    corrections.FOLDER.mkdir(parents=True, exist_ok=True)
    p = path_for(career_name)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def _empty(name: str) -> Dict[str, Any]:
    return {"format": FORMAT, "career": name, "sorties": {}, "pilots": {},
            "squadron": None, "gaps": {}}


# -- killStats strings, keys exactly as stored --------------------------------

def _parse(raw: Optional[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for pair in (raw or "").split("&"):
        key, sep, value = pair.partition("=")
        if not sep:
            continue
        try:
            out[key] = out.get(key, 0) + int(value)
        except ValueError:
            pass
    return out


def _add(into: Dict[str, int], raw: Optional[str]) -> None:
    for key, value in _parse(raw).items():
        into[key] = into.get(key, 0) + value


def _render(template: Optional[str], values: Dict[str, int]) -> str:
    """``values`` written in the order the template's keys stand, new keys after."""
    seen, parts = set(), []
    for pair in (template or "").split("&"):
        key, sep, _ = pair.partition("=")
        if not sep or key in seen:
            continue
        seen.add(key)
        parts.append(f"{key}={max(0, int(values.get(key, 0)))}")
    for key in sorted(values):
        if key not in seen and values[key]:
            parts.append(f"{key}={max(0, int(values[key]))}")
    return "&".join(parts)


# -- the points formula (careerProcessor.dll FUN_18006b690) -------------------

def points(kill_strings: List[Optional[str]]) -> int:
    """The kill-driven part of a pilot's score, summed over sorties in order."""
    veh = train = building = total = 0
    for raw in kill_strings:
        k = _parse(raw)
        total += max(0, k.get("Aircraft", 0) - k.get("StaticPlane", 0))
        veh += k.get("Materiel", 0) + k.get("StaticPlane", 0)
        train += k.get("Railroad", 0)          # the game never reads its Raildoad typo
        building += k.get("Building", 0)
        total += veh // 15 + k.get("Ships", 0) + train // 5 + building // 5
        veh, train, building = veh % 15, train % 5, building % 5
    return total


# -- the plan -------------------------------------------------------------------

def plan(db_path: Path, game_dir: Path, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Every value as it should stand, beside the value in the file. Reads only.
    Fills ``data`` with any original or offset seen for the first time; the
    caller saves it only when it writes.
    """
    from .assets import AssetResolver
    from .career.killfix import KillCategories, reductions, subtract

    table = KillCategories.from_resolver(AssetResolver(Path(game_dir)))
    out: Dict[str, Any] = {"sorties": [], "pilots": [], "squadron": None}
    if table is None:
        return out
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        names: Dict[Tuple[int, int], List[str]] = {}
        for row in con.execute(
                "SELECT missionId, pilotId, tpar1 FROM event WHERE type = 0 AND isDeleted = 0"):
            names.setdefault((row["missionId"], row["pilotId"]), []).append(row["tpar1"] or "")
        # In the order the game processed them: restored sorties (recovery.py)
        # carry new ids but old dates, and the points pots depend on order.
        sorties = con.execute(
            "SELECT id, missionId, pilotId, killStats FROM sortie WHERE isDeleted = 0 ORDER BY date, id"
        ).fetchall()
        pilots = {r["id"]: r for r in con.execute(
            "SELECT id, name, lastName, isPlayer, killStats, pcp, score FROM pilot")}
        squadron = con.execute(
            "SELECT id, killStats FROM squadron WHERE isDeleted = 0 LIMIT 1").fetchone()
    finally:
        con.close()

    orig_of: Dict[int, str] = {}
    corr_of: Dict[int, str] = {}
    for s in sorties:
        orig = data["sorties"].get(str(s["id"]), s["killStats"])
        corr = subtract(orig, reductions(orig, names.get((s["missionId"], s["pilotId"]), []), table))
        orig_of[s["id"]], corr_of[s["id"]] = orig, corr
        if corr != s["killStats"]:
            out["sorties"].append({"id": s["id"], "now": s["killStats"], "target": corr,
                                   "orig": orig})

    by_pilot: Dict[int, List[int]] = {}
    for s in sorties:
        by_pilot.setdefault(s["pilotId"], []).append(s["id"])

    def affected(ids: List[int]) -> bool:
        return any(orig_of[i] != corr_of[i] for i in ids)

    for pid, ids in by_pilot.items():
        p = pilots.get(pid)
        if p is None or (str(pid) not in data["pilots"] and not affected(ids)):
            continue
        sum_orig: Dict[str, int] = {}
        sum_corr: Dict[str, int] = {}
        for i in ids:
            _add(sum_orig, orig_of[i])
            _add(sum_corr, corr_of[i])
        if str(pid) not in data["pilots"]:
            # Taken once, while the file still holds the game's own totals.
            stored = _parse(p["killStats"])
            data["pilots"][str(pid)] = {k: stored.get(k, 0) - sum_orig.get(k, 0)
                                        for k in set(stored) | set(sum_orig)}
            data["gaps"].setdefault(str(pid), float(p["pcp"] or 0) - float(p["score"] or 0))
        offset = data["pilots"][str(pid)]
        target_kills = _render(p["killStats"], {k: offset.get(k, 0) + sum_corr.get(k, 0)
                                                for k in set(offset) | set(sum_corr)})
        excess = points([orig_of[i] for i in ids]) - points([corr_of[i] for i in ids])
        target_pcp = round(float(p["score"] or 0) + float(data["gaps"][str(pid)]) - excess, 2)
        out["pilots"].append({
            "id": pid, "name": f"{p['name']} {p['lastName']}".strip(),
            "is_player": bool(p["isPlayer"]),
            "kills_now": p["killStats"], "kills_target": target_kills,
            "pcp_now": float(p["pcp"] or 0), "pcp_target": target_pcp, "points": excess})

    if squadron is not None and (data["squadron"] is not None or affected([s["id"] for s in sorties])):
        sum_orig, sum_corr = {}, {}
        for s in sorties:
            _add(sum_orig, orig_of[s["id"]])
            _add(sum_corr, corr_of[s["id"]])
        if data["squadron"] is None:
            stored = _parse(squadron["killStats"])
            data["squadron"] = {k: stored.get(k, 0) - sum_orig.get(k, 0)
                                for k in set(stored) | set(sum_orig)}
        offset = data["squadron"]
        out["squadron"] = {"id": squadron["id"], "now": squadron["killStats"],
                           "target": _render(squadron["killStats"],
                                             {k: offset.get(k, 0) + sum_corr.get(k, 0)
                                              for k in set(offset) | set(sum_corr)})}
    return out


def _pending(p: Dict[str, Any]) -> bool:
    return bool(p["sorties"]
                or any(x["kills_now"] != x["kills_target"] or abs(x["pcp_now"] - x["pcp_target"]) > _EPS
                       for x in p["pilots"])
                or (p["squadron"] and p["squadron"]["now"] != p["squadron"]["target"]))


# -- writing ----------------------------------------------------------------------

def apply(db_path: Path, game_dir: Path) -> Dict[str, Any]:
    """Write the plan in one transaction. The caller backs up first."""
    name = Path(db_path).stem
    data = load(name) or _empty(name)
    p = plan(db_path, game_dir, data)
    counts = {"sorties": 0, "pilots": 0, "squadron": 0}
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        for s in p["sorties"]:
            data["sorties"].setdefault(str(s["id"]), s["orig"])
            con.execute("UPDATE sortie SET killStats = ? WHERE id = ?", (s["target"], s["id"]))
            counts["sorties"] += 1
        for x in p["pilots"]:
            if x["kills_now"] != x["kills_target"] or abs(x["pcp_now"] - x["pcp_target"]) > _EPS:
                con.execute("UPDATE pilot SET killStats = ?, pcp = ? WHERE id = ?",
                            (x["kills_target"], x["pcp_target"], x["id"]))
                counts["pilots"] += 1
        sq = p["squadron"]
        if sq and sq["now"] != sq["target"]:
            con.execute("UPDATE squadron SET killStats = ? WHERE id = ?", (sq["target"], sq["id"]))
            counts["squadron"] = 1
        con.commit()
    finally:
        con.close()
    data["auto"] = True
    data["applied_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save(name, data)
    return counts


def restore(db_path: Path) -> Dict[str, int]:
    """The game's own values back everywhere; the automatic run stops."""
    name = Path(db_path).stem
    data = load(name)
    counts = {"sorties": 0, "pilots": 0, "squadron": 0}
    if not data:
        return counts
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=rw", uri=True, timeout=1.0)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        for sid, orig in data.get("sorties", {}).items():
            con.execute("UPDATE sortie SET killStats = ? WHERE id = ?", (orig, int(sid)))
            counts["sorties"] += 1
        sorties = con.execute(
            "SELECT id, pilotId, killStats FROM sortie WHERE isDeleted = 0").fetchall()
        for pid, offset in data.get("pilots", {}).items():
            row = con.execute("SELECT killStats, score FROM pilot WHERE id = ?", (int(pid),)).fetchone()
            if row is None:
                continue
            total = dict(offset)
            for s in sorties:
                if s["pilotId"] == int(pid):
                    _add(total, s["killStats"])
            pcp = round(float(row["score"] or 0) + float(data["gaps"].get(pid, 0)), 2)
            con.execute("UPDATE pilot SET killStats = ?, pcp = ? WHERE id = ?",
                        (_render(row["killStats"], total), pcp, int(pid)))
            counts["pilots"] += 1
        if data.get("squadron") is not None:
            row = con.execute("SELECT id, killStats FROM squadron WHERE isDeleted = 0 LIMIT 1").fetchone()
            if row is not None:
                total = dict(data["squadron"])
                for s in sorties:
                    _add(total, s["killStats"])
                con.execute("UPDATE squadron SET killStats = ? WHERE id = ?",
                            (_render(row["killStats"], total), row["id"]))
                counts["squadron"] = 1
        con.commit()
    finally:
        con.close()
    data["auto"] = False
    data.pop("applied_at", None)
    save(name, data)
    return counts


def auto_sync(db_path: Path, game_dir: Path) -> Optional[Dict[str, int]]:
    """
    Called whenever the tracker reads a career. Writes, backup first, only when
    a value differs from its corrected figure; a career without napalm kills is
    never written and gets no record. A file the game holds is left for later.
    """
    name = Path(db_path).stem
    data = load(name) or _empty(name)
    if data.get("auto") is False:
        return None
    try:
        p = plan(db_path, game_dir, data)
    except sqlite3.Error as exc:
        logger.info("Napalm correction: %s not readable now (%s)", name, exc)
        return None
    if not _pending(p):
        return None
    try:
        corrections.backup(Path(db_path))
        counts = apply(db_path, game_dir)
    except sqlite3.OperationalError as exc:
        logger.info("Napalm correction: %s is in use, will retry (%s)", name, exc)
        return None
    logger.info("Napalm correction on %s: %s", name, counts)
    return counts
