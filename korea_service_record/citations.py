"""
Citations: the written reason for a decoration, in the words of the
awarding nation's own citations and built from what the man actually did.

The texts live in locales/citations/<lang>.json, one file per language,
keyed by nation and award family. A family is either a single action
(the Silver Star, the DFC, a Bronze Star with the V: the sortie that earned
it, on the day it was earned) or a period (the Air Medal, the orders of
the Red Banner: the missions flown up to the day). The facts - kills by
name, ground targets, hits taken, the outcome, the flight's size, where -
come from the career and the flight log; the sentences are the locale's.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FOLDER = Path(__file__).resolve().parent / "locales" / "citations"

# Award id -> (nation, family, kind). Kind: "sortie" for a single action,
# "period" for service over time, "unit" for a squadron citation, "service"
# for a service medal, which states only what it is for.
_USAF_SORTIE = {"moh": (601026, 601041), "dsc": (601021, 601022, 601023, 601024, 601025),
                "silver_star": (601018, 601019, 601020, 601050, 601051),
                "bsm_v": (601058, 601059, 601060, 601061, 601062), "purple_heart": (601028, 601029, 601030)}
_USAF_PERIOD = {"bsm": (601008, 601009, 601010), "air_medal": (601002, 601003, 601004, 601005, 601006, 601007),
                "dfc": (601011, 601012, 601013, 601014, 601015, 601016),
                "commendation": (601054, 601055, 601056, 601057), "lom": (601017,), "dsm": (601052,)}
_USAF_SERVICE = {"ndsm": (601053,), "ksm": tuple(range(601031, 601039)), "un": (601039,)}
_USAF_UNIT = {"duc": (601042, 601044, 601045, 601046), "rok_puc": (601043, 601047, 601048, 601049)}
_SOV_SORTIE = {"courage": (501002,)}
_SOV_PERIOD = {"hero": (501022,), "lenin": (501024,), "red_banner": (501016, 501018, 501020), "suvorov": (501014,),
               "nevsky": (501012,), "red_star": (501006,), "battle_merit": (501004,)}
_DPRK_PERIOD = {"hero_k": (503007,), "freedom": (503005, 503006), "soldiers_honour": (503003, 503004),
                "merit_k": (503002,)}
_DPRK_SERVICE = {"flw": (503008,)}
_PRC_PERIOD = {"merit_c": (502002,)}
_PRC_SERVICE = {"liberation_c": (502003,), "oppose_c": (502004,)}

FAMILY: Dict[int, tuple] = {}
for nation, table, kind in (("usaf", _USAF_SORTIE, "sortie"), ("usaf", _USAF_PERIOD, "period"), ("usaf", _USAF_UNIT, "unit"),
                            ("usaf", _USAF_SERVICE, "service"),
                            ("sov", _SOV_SORTIE, "sortie"), ("sov", _SOV_PERIOD, "period"),
                            ("dprk", _DPRK_PERIOD, "period"), ("dprk", _DPRK_SERVICE, "service"),
                            ("prc", _PRC_PERIOD, "period"), ("prc", _PRC_SERVICE, "service")):
    for family, ids in table.items():
        for aid in ids:
            FAMILY[aid] = (nation, family, kind)

# How the day is told: the air fight first (the default), the attack under
# fire first (the Bronze Star with V), or the wound alone (the Purple Heart).
STYLE = {"bsm_v": "valour", "purple_heart": "wound", "courage": "valour"}

# The numeral of a repeat Soviet order, as the citation names it.
ORDER_NUMERAL = {501018: 2, 501020: 3}

_cache: Dict[str, Dict[str, Any]] = {}


def strings(lang: str) -> Dict[str, Any]:
    """The citation texts for a game language code, English when missing."""
    for code in (lang, "eng"):
        if code in _cache:
            return _cache[code]
        path = FOLDER / f"{code}.json"
        if path.is_file():
            try:
                _cache[code] = json.loads(path.read_text(encoding="utf-8"))
                return _cache[code]
            except (OSError, ValueError) as exc:
                logger.warning("Citations %s unreadable: %s", path.name, exc)
    return {}


def format_date(texts: Dict[str, Any], ymd: str) -> str:
    """'1951.04.23' in the language's own words."""
    try:
        y, m, d = (int(n) for n in ymd.split(".")[:3])
        return texts["date"].format(d=d, month=texts["months"][m - 1], y=y)
    except (ValueError, IndexError, KeyError):
        return ymd


def _fill(template: str, facts: Dict[str, Any]) -> str:
    class _Safe(dict):
        def __missing__(self, key):
            return ""
    return template.format_map(_Safe(facts))


def compose(lang: str, award_id: int, facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    The citation for one award as paragraphs, or None when the award has
    none (badges, wound stripes, promotions). `facts` carries the
    placeholders; see the module note and the aggregator's citation().
    """
    texts = strings(lang)
    fam = FAMILY.get(award_id)
    if not texts or fam is None:
        return None
    nation, family, kind = fam
    template = texts.get(nation, {}).get(family)
    if not template:
        return None
    facts = dict(facts)
    facts["order"] = ""
    if award_id in ORDER_NUMERAL:
        facts["order"] = f" ({ORDER_NUMERAL[award_id]})"
    lst = texts.get("list", {})
    kills = facts.get("kills") or {}
    items = [_fill(lst.get("item", "{n} {type}"), {"n": n, "type": t}) for t, n in kills.items()]
    if len(items) > 1:
        facts["air_list"] = lst.get("sep", ", ").join(items[:-1]) + lst.get("last", " and ") + items[-1]
    else:
        facts["air_list"] = items[0] if items else ""
    deed_t = texts.get("deed", {})
    deed: List[str] = []
    style = STYLE.get(family)
    outcome = facts.get("outcome")
    if kind == "sortie" and facts.get("has_sortie"):
        deed.append(_fill(deed_t["leader" if facts.get("leader") else "member"], facts))
        st = texts.get(style, {}) if style else {}
        if style == "wound":
            if outcome == "bailed":
                deed.append(_fill(st["bailed"], facts))
            elif outcome == "missing":
                deed.append(_fill(st["lost"], facts))
            elif facts.get("hits"):
                deed.append(_fill(st["hits"], facts))
            else:
                deed.append(_fill(st["plain"], facts))
        elif style == "valour":
            if facts.get("ground_n") and items:
                deed.append(_fill(st["air"], facts))
            elif facts.get("ground_n"):
                deed.append(_fill(st["ground"], facts))
            elif items:
                deed.append(_fill(st["air_only"], facts))
            if outcome == "bailed":
                deed.append(_fill(st["bailed"], facts))
            elif outcome == "missing":
                deed.append(_fill(st["lost"], facts))
            elif facts.get("hits"):
                deed.append(_fill(st["hits"], facts))
        else:
            if items:
                deed.append(_fill(deed_t["air"], facts))
            if facts.get("ground_n"):
                deed.append(_fill(deed_t["ground_flak" if facts.get("hits") else "ground"], facts))
            if facts.get("hits") and outcome == "ok":
                deed.append(_fill(deed_t["hits"], facts))
            if outcome == "bailed":
                deed.append(_fill(deed_t["bailed"], facts))
            elif outcome == "missing":
                deed.append(_fill(deed_t["lost"], facts))
    elif kind == "unit":
        deed.append(_fill(deed_t["unit_period"], facts))
    elif kind == "period" and facts.get("missions"):
        air, ground = facts.get("air_total") or 0, facts.get("ground_total") or 0
        key = "period" if air and ground else "period_air" if air else "period_ground" if ground else "period_plain"
        deed.append(_fill(deed_t.get(key) or deed_t["period"], facts))
    facts["deed"] = " ".join(deed)
    opening = _fill(template[0], facts).strip()
    closing = _fill(template[1], facts).strip() if len(template) > 1 else ""
    paragraphs = [opening]
    if kind != "unit" and facts["deed"]:
        paragraphs.append(facts["deed"])
    if closing:
        paragraphs.append(closing)
    return {"heading": texts.get("heading", "Citation"), "paragraphs": [p for p in paragraphs if p],
            "kind": kind, "family": family}
