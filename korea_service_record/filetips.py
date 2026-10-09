"""
Tooltip helpers shared by the Chinese and Soviet personnel files: dates in
the reader's words and the biography paragraph by paragraph in his language.
"""

import re
from typing import Any, Dict, List


def long_date(lang: str, ymd: str) -> str:
    """'1951.04.02' in the reader's words (citations are keyed by game code)."""
    from . import citations
    from .i18n import game_code
    return citations.format_date(citations.strings(game_code(lang)), ymd)


def biography_tips(bio: Dict[str, Any], count: int, lang: str) -> List[str]:
    """
    The biography in the reader's language, one tooltip per paragraph of
    the document's own language. The game's translations keep the
    paragraphs in step; where they do not, each paragraph gets the one at
    the same place in the text.
    """
    paragraphs = bio.get("paragraphs") or []
    if not paragraphs or not count:
        return []
    who = bio.get("pilot") or {}
    fields = {"name": who.get("name", ""), "firstName": who.get("first_name", ""),
              "lastName": who.get("last_name", ""), "startRank": who.get("starting_rank", ""),
              "birthDate": long_date(lang, who.get("birth_date", "")) if who.get("birth_date") else ""}

    def fill(text: str) -> str:
        text = re.sub(r"^#+\s*", "", text)
        return re.sub(r"\$\[([^\]]+)\]", lambda m: fields.get(m.group(1), m.group(0)), text)

    filled = [fill(p) for p in paragraphs]
    if len(filled) == count:
        return filled
    return [filled[min(len(filled) - 1, i * len(filled) // count)] for i in range(count)]
