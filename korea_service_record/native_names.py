"""
A pilot's name in his own script, from the game's own name tables.

The career database keeps every name in the romanisation the English game
shows ("Lixin Song", "Svyatoslav Dunaev"). characternames.locale=eng.json
maps a key to that spelling and characternames.locale=<lang>.json the same
key to the native one, so the pair turns the romanised name back into
宋立新 or Святослав Дунаев.
"""

import functools
from typing import Dict, Optional, Tuple


@functools.lru_cache(maxsize=4)
def _tables(resolver, lang: str) -> Optional[Tuple[Dict[str, str], Dict[str, str]]]:
    from .gamedata import loads_lenient
    try:
        eng = loads_lenient(resolver.read_text("nsdata/assets/locale/characternames.locale=eng.json") or "{}")
        native = loads_lenient(resolver.read_text(f"nsdata/assets/locale/characternames.locale={lang}.json") or "{}")
    except Exception:  # noqa: BLE001 - no names is a blank field, not an error page
        return None
    reverse: Dict[str, str] = {}
    for key, word in eng.items():
        reverse.setdefault(word, key)
    return reverse, native


def native(word: str, resolver, lang: str) -> str:
    """One romanised name part in the game language ``lang`` (chs, rus), or ""."""
    tables = _tables(resolver, lang)
    if tables is None or not word:
        return ""
    reverse, names = tables
    key = reverse.get(word)
    return names.get(key, "") if key else ""
