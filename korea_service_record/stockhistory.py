"""
The squadron's stocks as the tracker found them, reading after reading.

The career file holds only today's stock. What a mission *really* used is
the difference between two readings, once the deliveries in between are
added back: consumption = delivered - change in stock. That is exact for all
three stores - fuel (the true burn, not the amount the game books before a
mission), ordnance and equipment, which the game books nowhere per mission.

So every time the record is read the tracker notes the stocks, the totals
delivered so far and the newest completed mission, in
``%LOCALAPPDATA%\\IL2KoreaTracker\\stock-history\\<career key>.json``. The
history knows only what happened while the tracker was watching; until it
covers a few flying days, the statistics fall back to the booked figures.

A career that goes backwards - a restored backup, a replayed day - starts a
new history rather than producing negative consumption, and an interval in
which a stock grew without a delivery (an edit) is left out.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .assets import default_cache_dir
from .portraitfix import career_key

logger = logging.getLogger(__name__)

STATE_FOLDER = "stock-history"
KEYS = ("fuel", "ordnance", "equipment")
MAX_READINGS = 400


def history_path(career_path: Path) -> Path:
    return default_cache_dir().parent / STATE_FOLDER / f"{career_key(career_path)}.json"


def load(career_path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(history_path(career_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    readings = data.get("readings") if isinstance(data, dict) else None
    return [r for r in readings or [] if isinstance(r, dict)]


def _same(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in ("date", "stock", "delivered", "last_mission"))


def record(career_path: Path, reading: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Add a reading - ``date`` (career date), ``stock`` and ``delivered`` (by
    key) and ``last_mission`` (the newest completed mission id) - unless it
    says nothing new. Returns the history. Never raises: a history that
    cannot be written costs the measured figures, not the page.
    """
    readings = load(career_path)
    if readings and _same(readings[-1], reading):
        return readings
    if readings and (str(reading["date"]) < str(readings[-1].get("date", "")) or
                     reading["last_mission"] < readings[-1].get("last_mission", 0)):
        logger.info("Career went backwards; stock history restarted")
        readings = []
    readings.append(dict(reading, recorded=datetime.now(timezone.utc).isoformat(timespec="seconds")))
    readings = readings[-MAX_READINGS:]
    try:
        target = history_path(career_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "career": str(career_path),
                                         "readings": readings}, indent=1) + "\n",
                             encoding="utf-8")
        temporary.replace(target)
    except OSError as exc:
        logger.warning("Cannot write stock history: %s", exc)
    return readings


def measured(readings: List[Dict[str, Any]],
             completed: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    What the stores really lost between readings, and over how many flying
    days. ``completed`` are the career's completed missions (``id``,
    ``date``); the flying days of an interval are the dates of the missions
    completed in it. None until two usable readings exist.
    """
    by_id = {m["id"]: str(m["date"])[:10] for m in completed}
    used = {k: 0 for k in KEYS}
    days = set()
    intervals = 0
    for a, b in zip(readings, readings[1:]):
        try:
            delta = {k: (b["delivered"][k] - a["delivered"][k]) - (b["stock"][k] - a["stock"][k])
                     for k in KEYS}
        except (KeyError, TypeError):
            continue
        if any(v < 0 for v in delta.values()):
            continue                      # a stock grew without a delivery: edited, not flown
        new_days = {d for i, d in by_id.items() if a["last_mission"] < i <= b["last_mission"]}
        if not new_days and not any(delta.values()):
            continue
        for k in KEYS:
            used[k] += delta[k]
        days |= new_days
        intervals += 1
    if not intervals or not days:
        return None
    return {"flying_days": len(days), "used": used}
