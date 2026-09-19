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


_LADDERS = {}
for _table in (_USAF_SORTIE, _USAF_PERIOD, _USAF_UNIT, _USAF_SERVICE):
    _LADDERS.update(_table)
# Twin ids for one rung (the Bronze Star V ladder): both count as that rung.
_RUNG = {601058: 0, 601059: 1, 601061: 1, 601060: 2, 601062: 2}


def _rung(award_id: int) -> int:
    """How far up its ladder an award sits: 0 for the decoration itself."""
    if award_id in _RUNG:
        return _RUNG[award_id]
    fam = FAMILY.get(award_id)
    ids = _LADDERS.get(fam[1], ()) if fam else ()
    return ids.index(award_id) if award_id in ids else 0


def _ordinal(cert: Dict[str, Any], day: int) -> str:
    return cert.get("ordinal", {}).get(str(day), f"{day}TH")


def _caps_date(ymd: str) -> str:
    """'1951.04.23' -> '23 APRIL 1951', as the forms type it."""
    try:
        y, m, d = (int(n) for n in ymd.split(".")[:3])
        return f"{d} {strings('eng')['months'][m - 1].upper()} {y}"
    except (ValueError, IndexError, KeyError):
        return ymd


def _title_date(ymd: str) -> str:
    """'1951.04.23' -> '23 April 1951'."""
    try:
        y, m, d = (int(n) for n in ymd.split(".")[:3])
        return f"{d} {strings('eng')['months'][m - 1]} {y}"
    except (ValueError, IndexError, KeyError):
        return ymd


def certificate(lang: str, award_id: int, facts: Dict[str, Any], received: str,
                paragraphs: List[str]) -> Optional[Dict[str, Any]]:
    """
    The document the award came with. For the USAF the certificate, in the
    words of the real form for that decoration (transcribed from the
    forms, one line structure each), an English document whatever the
    page's language: the man, the reason with when and where, the deed,
    the date it was given and the signature of the man who signed such
    certificates on that date. For the Soviet-pattern nations the decree,
    in the page's language, with the citation as its text.
    """
    fam = FAMILY.get(award_id)
    if fam is None:
        return None
    nation, family, kind = fam
    if nation == "usaf":
        cert = strings("eng").get("certificate") or {}
        form = cert.get("forms", {}).get(family)
        if not form:
            return None
        rung = _rung(award_id)
        if family == "ksm":
            device = cert["star"].get(str(rung), "") if rung else ""
        elif rung and (family, award_id) in (("dfc", 601016), ("air_medal", 601007)):
            device = cert["cluster_silver"]
        else:
            device = cert["cluster"].get(str(rung), "") if rung else ""
        rank = facts.get("rank", ""); name = facts.get("name", "")
        # The forms type in capitals; the placeholders are filled to match.
        fill = {
            "RANK": rank.upper(), "NAME": name.upper(), "UNIT": (facts.get("unit") or "").upper(),
            "AIRCRAFT": (facts.get("aircraft") or "").upper(), "PLACE": (facts.get("place") or "").upper(),
            "DATE": _caps_date(facts.get("earned_raw", "")),
            "FROM": _caps_date(facts.get("period_from_raw", "")), "TO": _caps_date(facts.get("earned_raw", "")),
            "POSSESSIVE": f"{rank} {name.split()[-1] if name else ''}".strip().upper() + "'S",
            "Place": facts.get("place") or "", "Date": _title_date(facts.get("earned_raw", "")),
            "From": _title_date(facts.get("period_from_raw", "")), "To": _title_date(facts.get("earned_raw", "")),
        }
        given = []
        try:
            y, m, d = (int(n) for n in (received or facts.get("earned_raw") or "").split(".")[:3])
            fill.update({"DAY": _ordinal(cert, d), "MONTH": strings("eng")["months"][m - 1].upper(), "YEAR": str(y)})
        except (ValueError, IndexError):
            fill.update({"DAY": "", "MONTH": "", "YEAR": ""})
        given = [_fill(line, fill) for line in form.get("given", [])]
        reason = _fill(form.get("reason", ""), fill)
        if device:
            # The medal as the form names it, without its article.
            medal = form.get("title", "")
            medal = medal[4:] if medal.startswith("THE ") else medal
            clause = _fill(cert["repeat"], {"DEVICE": device, "MEDAL": medal})
            if reason and reason[0].isupper() and not reason.isupper():
                clause = clause.lower().replace("oak leaf cluster", "Oak Leaf Cluster").replace(medal.lower(), medal.title())
            reason = reason.rstrip(".") + clause
        offices = form.get("signer", "fifth")
        if isinstance(offices, str):
            offices = ["", offices]                      # right-hand signature only
        signers = []
        for office in offices:
            who = cert["signers"].get(office, []) if office else []
            s_ = next((s for s in who if received <= s[0]), who[-1] if who else ["", "", ""])
            signers.append({"name": s_[1], "title": s_[2] if len(s_) > 2 else ""})
        signer = signers[-1]
        return {
            "form": "usaf",
            "header": form.get("header", ""),
            "pre": [_fill(line, fill) for line in form.get("pre", [])],
            "name_first": bool(form.get("name_first")),
            "title": form.get("title", ""), "cluster": "",
            "sub": [_fill(line, fill) for line in form.get("sub", [])],
            "to": form.get("to", ""),
            "name": _fill(form.get("name", "{RANK} {NAME}"), fill),
            "service": form.get("service", ""),
            "for": form.get("for", ""),
            "reason": reason,
            "where": _fill(form.get("where", ""), fill),
            "deed": paragraphs[1] if len(paragraphs) > 2 else "",
            "close": [_fill(line, fill) for line in form.get("close", "").split(chr(10)) if line],
            "given": given, "seal": cert.get("seal", ""),
            "signer": signer["name"], "signer_title": signer["title"],
            "signers": signers,                          # [left, right]
        }
    texts = strings(lang)
    dec = texts.get("decree") or strings("eng").get("decree") or {}
    if not dec:
        return None
    return {
        "form": "decree", "title": dec["title"].get(nation, ""),
        "subject": _fill(dec["subject"], facts), "paragraphs": paragraphs,
        "place": dec["place"].get(nation, ""), "date": format_date(texts, received or facts.get("earned_raw", "")),
        "signers": dec["signers"].get(nation, []),
    }


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
