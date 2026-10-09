"""
Custom portrait paths the game can survive.

``pilot.avatarPath`` names a portrait under
``data/NSData/assets/pilotphotos/<avatarPath>.dds``. The career processor copies
it into a 16-byte buffer with ``strcpy_s`` (careerProcessor.dll 1.004b,
FUN_1800379d0 at 0x180037c8e), so a path of 16 characters or more makes the
C runtime abort the game - exception 0xc0000409 in ucrtbase.dll - at the next
day rollover. The stock paths are short (``usa50h/1``); 2.2.2's custom
portraits were ``custom/<16 hex>-<pilot id>``, 26 characters, and every career
that took one crashed on its next new day (12th FBS career, 2026-10-05: three
crash dumps, all in that call).

New portraits use ``cp/<10 hex>`` - 13 characters. ``repair()`` moves a career
that already holds a long ``custom/`` path onto the short one: the DDS is
copied to the new name, the path rewritten, a backup taken first.
"""

import hashlib
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# The game's buffer is 16 bytes including the terminating NUL.
MAX_AVATAR_PATH = 15
PHOTO_ROOT = "data/NSData/assets/pilotphotos"
STATE_FOLDER = "custom-portraits"


def career_key(career_path: Path) -> str:
    try:
        identity = str(Path(career_path).resolve()).casefold()
    except OSError:
        identity = str(career_path).casefold()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def is_custom(avatar_path: str) -> bool:
    """A portrait the Career Helper made, never one the game shipped."""
    return str(avatar_path or "").startswith(("custom/", "cp/"))


def short_avatar_path(career_path: Path, pilot_id: int) -> str:
    """``cp/`` and ten hex digits of career and pilot: 13 characters."""
    digest = hashlib.sha256(f"{career_key(career_path)}-{int(pilot_id)}".encode("utf-8"))
    return "cp/" + digest.hexdigest()[:10]


def photo_file(game_dir: Path, avatar_path: str) -> Path:
    return Path(game_dir) / PHOTO_ROOT / f"{avatar_path}.dds"


def _state_path(career_path: Path) -> Path:
    from .assets import default_cache_dir
    return default_cache_dir().parent / STATE_FOLDER / f"{career_key(career_path)}.json"


def _too_long(db_path: Path) -> List[Dict[str, Any]]:
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        return [{"id": r[0], "path": r[1]} for r in con.execute(
            "SELECT id, avatarPath FROM pilot WHERE length(avatarPath) > ?", (MAX_AVATAR_PATH,))]
    finally:
        con.close()


def repair(db_path: Path, game_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """
    Rewrite every ``custom/`` portrait path longer than the game allows.
    Called whenever the tracker reads a career; writes only when one exists.
    A long path of unknown origin is left alone and logged.
    """
    from . import corrections

    db_path, game_dir = Path(db_path), Path(game_dir)
    try:
        todo = _too_long(db_path)
    except sqlite3.Error as exc:
        logger.info("Portrait repair: %s not readable now (%s)", db_path.stem, exc)
        return None
    if not todo:
        return None
    done = []
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=rw", uri=True, timeout=1.0)
    try:
        con.execute("BEGIN IMMEDIATE")
        corrections.backup(db_path)
        for row in todo:
            old = row["path"] or ""
            if not old.startswith("custom/"):
                logger.warning("Portrait repair: pilot %s has a %d-character avatarPath %r "
                               "of unknown origin - left alone", row["id"], len(old), old)
                continue
            new = short_avatar_path(db_path, row["id"])
            source, target = photo_file(game_dir, old), photo_file(game_dir, new)
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif not target.is_file():
                logger.warning("Portrait repair: %s is missing; the portrait will show blank", source)
            con.execute("UPDATE pilot SET avatarPath = ? WHERE id = ? AND avatarPath = ?",
                        (new, row["id"], old))
            done.append({"pilot": row["id"], "from": old, "to": new})
        con.commit()
    except sqlite3.OperationalError as exc:
        logger.info("Portrait repair: %s is in use, will retry (%s)", db_path.stem, exc)
        return None
    finally:
        con.close()
    # The Career Helper remembers the path it set; keep it pointing at the new one.
    state_file = _state_path(db_path)
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        for d in done:
            for key in ("custom_avatar_path", "original_avatar_path"):
                if state.get(key) == d["from"]:
                    state[key] = d["to"]
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, AttributeError):
        pass
    if done:
        logger.info("Portrait repair on %s: %s", db_path.stem, done)
    return done or None
