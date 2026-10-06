"""
A player's own biography, written in the Career Helper.

The game shows a biography only while a career is being created; once the
career runs, the Service Record's biography book is the only place it is read
again. So a biography the player rewrites lives with the tracker, not the
game: one small record per career under
``%LOCALAPPDATA%\\IL2KoreaTracker\\custom-biographies``, keyed exactly as the
custom portraits are. Nothing in the game folder or the career database
changes, and ``pilot.description`` keeps the biography the player chose.

A record holds the text (``None``: keep the game's) and the World War II
medals the player says he earned (``None``: infer them from the chosen
biography, as before). It belongs to one pilot; when the game carries the
career on with a successor, the record no longer applies.

The text uses the game's own variables - ``$[name]``, ``$[firstName]``,
``$[lastName]``, ``$[birthDate]``, ``$[startRank]`` - and blank lines between
paragraphs. It is plain text: the book receives text, never markup.
"""

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import wwii_awards
from .assets import default_cache_dir
from .portraitfix import career_key

STATE_FOLDER = "custom-biographies"
VARIABLES = ("name", "firstName", "lastName", "birthDate", "startRank")
# The book pages any length; this only stops a pasted novel. The longest
# stock biography is about 4,800 characters.
MAX_LENGTH = 30000

_VARIABLE = re.compile(r"\$\[([^\]]*)\]")


# Boosters. The biography chosen at career start seeds the player's
# ``pilot.leadLevel`` from ``characterbio/info.json`` (4 points, 5 for two
# biographies, at most 3 on one attribute); the game adds more during the
# career. leadLevel packs them low nibble first as skill, courage, discipline
# (see career/attributes.py). Unlike the text, these DO matter to the game:
# the mission commander's boosters raise every participant's weights in
# missions resolved without the player (Ranks-effectiveness.cfg).
BOOSTER_KEYS = ("skill", "courage", "discipline")       # packed order
BOOSTER_MAX = 3                                          # per attribute, as the stock biographies


def biography_points(info: Dict[str, Any], biography_id: str) -> Optional[Dict[str, int]]:
    """The points a biography gives, following the game's ``copy`` entries."""
    entry = info.get(str(biography_id))
    for _ in range(4):
        if isinstance(entry, dict) and "copy" in entry:
            entry = info.get(str(entry["copy"]))
    if not isinstance(entry, dict):
        return None
    try:
        return {key: int(entry[key]) for key in BOOSTER_KEYS}
    except (KeyError, TypeError, ValueError):
        return None


def boosters(lead_level: int) -> Dict[str, int]:
    """The three boosters packed into ``pilot.leadLevel``."""
    lead = int(lead_level or 0)
    return {key: (lead >> (4 * i)) & 0xF for i, key in enumerate(BOOSTER_KEYS)}


def check_allocation(chosen: Dict[str, int], total: int) -> None:
    """Raise ValueError unless ``chosen`` shares out exactly ``total`` points."""
    values = [int(chosen.get(key, -1)) for key in BOOSTER_KEYS]
    if any(v < 0 or v > BOOSTER_MAX for v in values):
        raise ValueError(f"each booster must be 0 to {BOOSTER_MAX}")
    if sum(values) != total:
        raise ValueError(f"the boosters must add up to {total}, not {sum(values)}")


def reallocate(lead_level: int, allocated: Dict[str, int],
               chosen: Dict[str, int]) -> int:
    """
    ``leadLevel`` with the biography's share moved from ``allocated`` to
    ``chosen``. What the game added on top stays; bits above the three
    boosters are kept as they are.
    """
    lead = int(lead_level or 0)
    current = boosters(lead)
    packed = 0
    for i, key in enumerate(BOOSTER_KEYS):
        earned = max(0, current[key] - int(allocated[key]))
        value = earned + int(chosen[key])
        if value > 0xF:
            raise ValueError(f"{key} booster would exceed 15")
        packed |= value << (4 * i)
    return (lead & ~0xFFF) | packed


def state_path(career_path: Path) -> Path:
    return default_cache_dir().parent / STATE_FOLDER / f"{career_key(career_path)}.json"


def _read(career_path: Path, pilot_id: int) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(state_path(career_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("pilot_id") != int(pilot_id):
        return None
    return data


def _write(career_path: Path, data: Dict[str, Any]) -> Path:
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    target = state_path(career_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(target)
    return target


def _boosters_of(data: Dict[str, Any]) -> Optional[Dict[str, int]]:
    value = data.get("boosters")
    if not isinstance(value, dict):
        return None
    try:
        return {key: int(value[key]) for key in BOOSTER_KEYS}
    except (KeyError, TypeError, ValueError):
        return None


def load(career_path: Path, pilot_id: int) -> Optional[Dict[str, Any]]:
    """This pilot's record, or None when there is none or it is another's."""
    data = _read(career_path, pilot_id)
    if data is None:
        return None
    text = data.get("text")
    awards = data.get("wwii_awards")
    return {
        "pilot_id": int(pilot_id),
        "country": data.get("country"),
        "text": text if isinstance(text, str) and text.strip() else None,
        "wwii_awards": list(awards) if isinstance(awards, list) else None,
        # the biography's points as the player last shared them out
        "boosters": _boosters_of(data),
        "updated": data.get("updated"),
    }


def save(career_path: Path, pilot_id: int, country: int,
         text: Optional[str], awards: Optional[List[int]]) -> Path:
    """
    Write the text and medals. ``text`` None keeps the game's biography;
    ``awards`` None keeps the medals inferred from it. A booster allocation
    already recorded is kept. Raises ValueError on a text longer than
    :data:`MAX_LENGTH`.
    """
    if text is not None:
        text = text.replace("\r\n", "\n").strip()
        if len(text) > MAX_LENGTH:
            raise ValueError(f"biography longer than {MAX_LENGTH} characters")
        text = text or None
    previous = _read(career_path, pilot_id) or {}
    data = {
        "version": 1,
        "career": str(career_path),
        "pilot_id": int(pilot_id),
        "country": int(country),
        "text": text,
        "wwii_awards": (None if awards is None
                        else list(wwii_awards.chosen(awards, int(country)))),
        "boosters": _boosters_of(previous),
    }
    return _write(career_path, data)


def save_boosters(career_path: Path, pilot_id: int, country: int,
                  chosen: Dict[str, int]) -> Path:
    """Record how the biography's points are now shared out; text and medals stay."""
    data = _read(career_path, pilot_id) or {
        "version": 1, "career": str(career_path), "pilot_id": int(pilot_id),
        "country": int(country), "text": None, "wwii_awards": None}
    data["boosters"] = {key: int(chosen[key]) for key in BOOSTER_KEYS}
    return _write(career_path, data)


def clear(career_path: Path, pilot_id: Optional[int] = None) -> None:
    """
    Back to the game's text and medals. A booster allocation stays recorded:
    the career still holds it, and the next change must know it.
    """
    data = _read(career_path, pilot_id) if pilot_id is not None else None
    if data is not None and _boosters_of(data) is not None:
        data["text"] = None
        data["wwii_awards"] = None
        _write(career_path, data)
        return
    try:
        state_path(career_path).unlink()
    except FileNotFoundError:
        pass


def paragraphs(text: str) -> List[str]:
    """Plain text with blank lines between paragraphs, as the book wants it."""
    out = []
    for piece in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")):
        plain = re.sub(r"\s+", " ", piece).strip()
        if plain:
            out.append(plain)
    return out


def html_paragraphs(raw: str) -> List[str]:
    """The game's small HTML biography as safe, plain-text paragraphs."""
    text = (raw or "").strip()
    if not text:
        return []
    found = re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", text,
                       flags=re.IGNORECASE | re.DOTALL)
    pieces = found if found else re.split(r"(?:\r?\n){2,}", text)
    out = []
    for piece in pieces:
        # Stock biographies contain only <p>, but a hand-written loose file
        # may contain simple inline markup. The page receives text, never
        # game-supplied HTML, so it cannot become executable browser content.
        plain = re.sub(r"<br\s*/?>", " ", piece, flags=re.IGNORECASE)
        plain = re.sub(r"<[^>]+>", "", plain)
        plain = re.sub(r"\s+", " ", html.unescape(plain)).strip()
        if plain:
            out.append(plain)
    return out


def editable(raw: str) -> str:
    """A game biography as the editor shows it: paragraphs, blank lines between."""
    return "\n\n".join(html_paragraphs(raw))


def unknown_variables(text: str) -> List[str]:
    """``$[...]`` placeholders the book cannot fill, as written, in order."""
    seen = []
    for match in _VARIABLE.finditer(text or ""):
        if match.group(1) not in VARIABLES and match.group(0) not in seen:
            seen.append(match.group(0))
    return seen
