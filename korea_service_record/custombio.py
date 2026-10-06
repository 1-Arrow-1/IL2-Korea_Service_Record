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
# biographies, at most 3 on one attribute); every promotion adds one more,
# on the attribute the player picks in the game. leadLevel packs them low
# nibble first as skill, courage, discipline (see career/attributes.py).
# Unlike the text, these DO matter to the game: the mission commander's
# boosters raise every participant's weights in missions resolved without
# the player (Ranks-effectiveness.cfg).
#
# The player may share out ALL his points again - the promotion points too,
# since he chose where they went - keeping the total, and with no attribute
# above what the game itself could have produced: 3 from the biography plus
# every promotion point. Nothing needs remembering between changes, so a
# lost or unseen record cannot add points (an earlier design kept the
# biography's share in the record and did exactly that).
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


def booster_cap(biography_total: int, current: Dict[str, int]) -> int:
    """
    The most one attribute may hold: the biography's 3 plus every point the
    promotions added - and never less than the pilot already has there.
    """
    promotions = max(0, sum(current.values()) - int(biography_total))
    # 15 is all a leadLevel nibble holds
    return min(0xF, max(BOOSTER_MAX + promotions, max(current.values())))


def check_allocation(chosen: Dict[str, int], total: int, cap: int) -> None:
    """Raise ValueError unless ``chosen`` shares out exactly ``total`` points."""
    values = [int(chosen.get(key, -1)) for key in BOOSTER_KEYS]
    if any(v < 0 or v > cap for v in values):
        raise ValueError(f"each booster must be 0 to {cap}")
    if sum(values) != total:
        raise ValueError(f"the boosters must add up to {total}, not {sum(values)}")


def repack(lead_level: int, chosen: Dict[str, int]) -> int:
    """``leadLevel`` holding ``chosen``; bits above the three boosters are kept."""
    lead = int(lead_level or 0)
    packed = 0
    for i, key in enumerate(BOOSTER_KEYS):
        value = int(chosen[key])
        if not 0 <= value <= 0xF:
            raise ValueError(f"{key} booster out of range: {value}")
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
        "updated": data.get("updated"),
    }


def save(career_path: Path, pilot_id: int, country: int,
         text: Optional[str], awards: Optional[List[int]]) -> Path:
    """
    Write the text and medals. ``text`` None keeps the game's biography;
    ``awards`` None keeps the medals inferred from it. Raises ValueError on a
    text longer than :data:`MAX_LENGTH`.
    """
    if text is not None:
        text = text.replace("\r\n", "\n").strip()
        if len(text) > MAX_LENGTH:
            raise ValueError(f"biography longer than {MAX_LENGTH} characters")
        text = text or None
    data = {
        "version": 1,
        "career": str(career_path),
        "pilot_id": int(pilot_id),
        "country": int(country),
        "text": text,
        "wwii_awards": (None if awards is None
                        else list(wwii_awards.chosen(awards, int(country)))),
    }
    return _write(career_path, data)


def clear(career_path: Path, pilot_id: Optional[int] = None) -> None:
    """Back to the game's text and medals. ``pilot_id`` is accepted for callers."""
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
