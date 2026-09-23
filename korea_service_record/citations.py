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
                "purple_heart": (601028, 601029, 601030)}
_USAF_PERIOD = {"bsm": (601008, 601009, 601010), "air_medal": (601002, 601003, 601004, 601005, 601006, 601007),
                "dfc": (601011, 601012, 601013, 601014, 601015, 601016),
                "commendation": (601054, 601055, 601056, 601057), "lom": (601017,), "dsm": (601052,)}
# bsm_v sits here, not among the sortie awards: the "V" denotes heroism
# that did NOT involve participation in aerial flight, so its citation must
# never narrate what the man did from the cockpit that day.
_USAF_SERVICE = {"ndsm": (601053,), "ksm": tuple(range(601031, 601039)), "un": (601039,),
                 "bsm_v": (601058, 601059, 601060, 601061, 601062),
                 "soldiers_medal": (601063,)}
_USAF_UNIT = {"duc": (601042, 601044, 601045, 601046), "rok_puc": (601043, 601047, 601048, 601049)}
_NAVAL_SORTIE = {
    "moh": (602027, 602038),
    "navy_cross": (602021, 602022, 602023, 602024, 602025, 602026),
    "silver_star": (602018, 602019, 602020, 602042, 602043),
    "purple_heart": (602028, 602029, 602030),
}
_NAVAL_PERIOD = {
    "bsm": (602008, 602009, 602010),
    "air_medal": (602002, 602003, 602004, 602005, 602006, 602007),
    "dfc": (602011, 602012, 602013, 602014, 602015, 602016),
    "navy_commendation": (602032, 602035, 602036, 602037),
    "lom": (602017,),
    "navy_dsm": (602031,),
}
_NAVAL_SERVICE = {"bsm_v": (602048, 602049, 602050, 602051, 602052),
                  "nmc_medal": (602053,)}
_NAVAL_UNIT = {
    "navy_puc": (602033, 602039, 602040, 602041),
    "navy_unit_commendation": (602034, 602044, 602045, 602046, 602047),
}
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
                            ("naval", _NAVAL_SORTIE, "sortie"), ("naval", _NAVAL_PERIOD, "period"),
                            ("naval", _NAVAL_UNIT, "unit"), ("naval", _NAVAL_SERVICE, "service"),
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


_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def _latin(text: str) -> str:
    """Cyrillic transliterated for a reader of the Latin alphabet; other text untouched."""
    out = []
    for ch in text:
        low = ch.lower()
        if low in _CYR:
            t = _CYR[low]
            out.append(t.capitalize() if ch.isupper() else t)
        else:
            out.append(ch)
    return "".join(out)


def _fill(template: str, facts: Dict[str, Any]) -> str:
    class _Safe(dict):
        def __missing__(self, key):
            return ""
    return template.format_map(_Safe(facts))


_LADDERS = {}
for _table in (_USAF_SORTIE, _USAF_PERIOD, _USAF_UNIT, _USAF_SERVICE,
               _NAVAL_SORTIE, _NAVAL_PERIOD, _NAVAL_UNIT, _NAVAL_SERVICE):
    _LADDERS.update(_table)
# Twin ids for one rung (the Bronze Star V ladder): both count as that rung.
_RUNG = {601058: 0, 601059: 1, 601061: 1, 601060: 2, 601062: 2}
_RUNG.update({602048: 0, 602049: 1, 602051: 1, 602050: 2, 602052: 2})

# Naval families whose citation prose follows an existing U.S. family. The
# award and service names are changed below; the deed remains the pilot's.
_NAVAL_CITATION_BASE = {
    "nmc_medal": "soldiers_medal",
    "navy_cross": "dsc",
    "navy_dsm": "dsm",
    "navy_commendation": "commendation",
    "navy_puc": "duc",
    "navy_unit_commendation": "duc",
}

# Naval awards whose citation is written for them, not an Air Force text
# with the service names changed.
NAVAL_OWN_TEXT = ("navy_unit_commendation", "nmc_medal")

# The supplied Navy-specific sheets. Other U.S. naval awards use the shared
# Army/Air Force sheet with the Navy seal overlay.
_NAVAL_TEMPLATE = {
    "nmc_medal": "Navy_MC_medal",
    "moh": "Navy_MoH",
    "navy_cross": "Navy_Cross",
    "navy_commendation": "Navy_commendation",
    "navy_puc": "Navy_puc",
    "navy_unit_commendation": "Navy_unit_commendation",
}


def _naval_text(text: str, texts: Dict[str, Any], country: int,
                family: str = "") -> str:
    """Change Air Force prose to Navy or Marine Corps prose in one locale."""
    naval = texts.get("naval") or {}
    branch = naval.get(str(country)) or naval.get("602") or {}
    def replace_term(value: str, source: str, target: str) -> str:
        return value.replace(source.upper(), target.upper()).replace(source, target)

    # Both the Navy and Marine Corps are administered by the Department of
    # the Navy. Handle those office names before replacing generic service
    # references such as "Air Force" with the member's actual branch.
    text = replace_term(text, "Department of the Air Force", "Department of the Navy")
    text = replace_term(text, "Secretary of the Air Force", "Secretary of the Navy")
    text = replace_term(text, naval.get("air_force", "United States Air Force"),
                        branch.get("service", "United States Navy"))
    text = replace_term(text, naval.get("air_command", "Far East Air Forces"),
                        branch.get("command", "United States Naval Forces, Far East"))
    if naval.get("air_force_short") and branch.get("service_short"):
        text = replace_term(text, naval["air_force_short"], branch["service_short"])
    awards = naval.get("awards") or {}
    base = _NAVAL_CITATION_BASE.get(family)
    if base and awards.get(base) and awards.get(family):
        text = replace_term(text, awards[base], awards[family])
    return text


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
    country = int(facts.get("country") or 0)
    is_naval = country in (602, 603) and nation in ("usaf", "naval")
    if nation in ("usaf", "naval"):
        cert = strings("eng").get("certificate") or {}
        base_family = _NAVAL_CITATION_BASE.get(family, family)
        base_form = cert.get("forms", {}).get(base_family)
        if not base_form:
            return None
        form = dict(base_form)
        if is_naval:
            def naval_value(value):
                if isinstance(value, str):
                    return _naval_text(value, strings("eng"), country, family)
                if isinstance(value, list):
                    return [naval_value(v) for v in value]
                return value
            form = {key: naval_value(value) for key, value in form.items()}
            form.update((cert.get("naval_forms") or {}).get(family, {}))
        rung = _rung(award_id)
        if family == "rok_puc":
            device = ""  # Further citations do not authorize a ribbon device.
        elif family == "ksm":
            device = cert["star"].get(str(rung), "") if rung else ""
        elif is_naval and rung and family in ("navy_commendation", "navy_puc",
                                               "navy_unit_commendation"):
            device = cert["naval_bronze_star"].get(str(rung), "")
        elif is_naval and rung:
            device = cert["gold_star"].get(str(rung), "")
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
        if is_naval:
            branch = (strings("eng").get("naval") or {}).get(str(country), {})
            fill["SERVICE"] = (branch.get("service") or "United States Navy").upper()
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
            if is_naval:
                office = {"chief": "navy_chief", "secretary": "navy_secretary",
                          "fifth": "navy_chief"}.get(office, office)
                if office == "navy_chief" and country == 603:
                    office = "marine_commandant"
            who = cert["signers"].get(office, []) if office else []
            s_ = next((s for s in who if received <= s[0]), who[-1] if who else ["", "", ""])
            signers.append({"name": s_[1], "title": s_[2] if len(s_) > 2 else "",
                            "image": f"/static/images/signatures/{s_[3]}.png" if len(s_) > 3 and
                            (Path(__file__).resolve().parent / "static" / "images" / "signatures" / f"{s_[3]}.png").is_file() else ""})
        signer = signers[-1]
        template = _NAVAL_TEMPLATE.get(family, base_family) if is_naval else family
        seal_overlay = (is_naval and family not in _NAVAL_TEMPLATE and
                        base_family not in ("un", "rok_puc"))
        return {
            "form": "usaf",
            "template": template,
            "seal_overlay": ("/static/images/certificates/Navy_seal_overlay_landscape.png"
                             if seal_overlay else ""),
            "header": form.get("header", ""),
            "pre": [_fill(line, fill) for line in form.get("pre", [])],
            "name_first": bool(form.get("name_first")),
            "title": form.get("title", ""), "cluster": "",
            "sub": [_fill(line, fill) for line in form.get("sub", [])],
            "to": form.get("to", ""),
            "name": _fill(form.get("name", "{RANK} {NAME}"), fill),
            "unit_line": _fill(form.get("unit_line", ""), fill),
            "service": _fill(form.get("service", ""), fill),
            "for": form.get("for", ""),
            "reason": reason,
            "where": _fill(form.get("where", ""), fill),
            "deed": paragraphs[1] if len(paragraphs) > 2 else "",
            "close": [_fill(line, fill) for line in form.get("close", "").split(chr(10)) if line],
            "given": given,
            "seal": "DEPARTMENT OF THE NAVY" if is_naval else cert.get("seal", ""),
            "signer": signer["name"], "signer_title": signer["title"],
            "signers": signers,                          # [left, right]
        }
    # Soviet pattern: the award recommendation sheet (наградной лист), a
    # Russian document whatever the page's language - the commander's
    # form with the man's particulars, the deed in the commander's words
    # and his conclusion. The KPA used the Soviet form.
    n = strings("rus").get("nagradnoy") or {}
    if not n:
        return None
    ru = strings("rus")
    deed = compose("rus", award_id, facts) or {}
    rus_facts = dict(facts)
    fam_key = family
    held = [n["held"].get(FAMILY[a][1], "") for a in facts.get("held_before", []) if a in FAMILY and FAMILY[a][1] in n["held"]]
    held = [h for h in held if h]
    date_raw = received or facts.get("earned_raw", "")
    # The player's game biography gives the particulars the form asks for;
    # an AI pilot has none, and those lines stay blank.
    bio = (strings("rus").get("bios") or {}).get(str(facts.get("bio_id") or ""), {})
    korea = _fill(n["battles"], {"from": format_date(ru, facts.get("period_from_raw", "") or date_raw), "to": format_date(ru, date_raw)})
    battles = (bio["battles"] + "; " + korea) if bio.get("battles") and bio["battles"] != "не участвовал" else korea
    prior = [bio["prior"]] if bio.get("prior") else []
    held_all = prior + held
    birth = facts.get("birth_date", "")
    # The same entries in the page's language, for the tooltips: the awards
    # by their game names in that language, the fixed phrases translated,
    # the biography's lines from its own language table, the deed as the
    # citation in that language.
    texts = strings(lang)
    tr = texts.get("nagradnoy_tr") or strings("eng").get("nagradnoy_tr") or {}
    bio_tr = (texts.get("bios_tr") or strings("eng").get("bios_tr") or {}).get(str(facts.get("bio_id") or ""), {})
    deed_tr = compose(lang, award_id, facts) or {}
    korea_tr = _fill(tr.get("battles", "Korea, {from} to {to}"), {"from": format_date(texts, facts.get("period_from_raw", "") or date_raw), "to": format_date(texts, date_raw)})
    battles_tr = ((bio_tr.get("battles", "") + "; ") if bio_tr.get("battles") and not bio_tr.get("none") else "") + korea_tr
    held_tr = ([bio_tr["prior"]] if bio_tr.get("prior") else []) + [facts.get("held_names", {}).get(a, "") for a in facts.get("held_before", []) if a in FAMILY and FAMILY[a][1] in n["held"]]
    held_tr = [h for h in held_tr if h]
    translation = {
        "name": _latin(facts.get("name", "")) if lang != "rus" else facts.get("name", ""),
        "rank": facts.get("rank_tr", ""),
        "sign": _latin(facts.get("commander", "")) if lang != "rus" else facts.get("commander", ""),
        "to": facts.get("award_name_tr", ""),
        "post": _fill(tr.get("post", "pilot, {unit}"), {"unit": facts.get("unit", "")}),
        "nationality": bio_tr.get("nationality", ""), "party": bio_tr.get("party", ""),
        "since": bio_tr.get("since", "") or _fill(tr.get("since", "since {from}"), {"from": format_date(texts, facts.get("period_from_raw", "") or date_raw)}),
        "battles": battles_tr,
        "wounds": _fill(tr.get("wounded", "yes ({date})"), {"date": format_date(texts, facts["wound_date"])}) if facts.get("wound_date") else tr.get("not_wounded", "none"),
        "held": ", ".join(held_tr) if held_tr else tr.get("not_awarded", "none"),
        "rvk": bio_tr.get("born", ""),
        "deed": " ".join((deed_tr.get("paragraphs") or [])[1:2]) + " " + _fill(tr.get("conclusion", "Conclusion: worthy of the {award}."), {"award": facts.get("award_name_tr", "")}),
        "date": format_date(texts, date_raw),
    }
    return {
        "form": "nagradnoy", "translation": translation,
        "name": facts.get("name_ru") or facts.get("name", ""),
        "rank": facts.get("rank_ru") or facts.get("rank", ""),
        "post": _fill(n["post"], {"unit": facts.get("unit", "")}),
        "to": n["to"].get(fam_key, ""),
        "born": birth[:4] if birth else "",
        "birthplace": bio.get("born", ""),
        "nationality": bio.get("nationality", ""),
        "party": bio.get("party", ""),
        "since": bio.get("since") or _fill(n["since"], {"from": format_date(ru, facts.get("period_from_raw", "") or date_raw)}),
        "battles": battles,
        "wounds": _fill(n["wounded"], {"date": format_date(ru, facts["wound_date"])}) if facts.get("wound_date") else n["not_wounded"],
        "held": ", ".join(held_all) if held_all else n["not_awarded"],
        "deed": [p_ for p_ in (deed.get("paragraphs") or [])[1:2]],
        "conclusion": _fill(n["conclusion"], {"reason": n["reason"].get(kind, n["reason"]["period"]), "worthy": n["worthy"].get(fam_key, "")}),
        "commander": _fill(n["commander"], {"unit": facts.get("unit", "")}),
        "commander_name": facts.get("commander", ""),
        "commissar": n["commissars"][sum(ord(ch) for ch in facts.get("unit", "")) % len(n["commissars"])] if n.get("commissars") else "",
        "commissar_tr": _latin(n["commissars"][sum(ord(ch) for ch in facts.get("unit", "")) % len(n["commissars"])]) if n.get("commissars") and lang != "rus" else "",
        "date": format_date(ru, date_raw),
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
    country = int(facts.get("country") or 0)
    is_naval = country in (602, 603) and nation in ("usaf", "naval")
    if family in NAVAL_OWN_TEXT:
        template = (texts.get("naval") or {}).get(family)
    else:
        template_family = _NAVAL_CITATION_BASE.get(family, family)
        template_nation = "usaf" if nation == "naval" else nation
        template = texts.get(template_nation, {}).get(template_family)
    if not template:
        return None
    facts = dict(facts)
    facts["order"] = ""
    if is_naval:
        facts["service"] = ((texts.get("naval") or {}).get(str(country), {})
                            .get("service", "United States Navy"))
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
    # Several phrasings per sentence, one chosen by the mission (and the
    # award, so two decorations for one day do not read alike): stable
    # for a given citation, different from day to day.
    variants = texts.get("variants", {})
    seed = int(facts.get("seed") or 0) * 1000003 + (award_id % 97) * 7919

    def pick(slot: str, fallback: str) -> str:
        options = variants.get(slot) or ([deed_t[fallback]] if fallback in deed_t else [])
        if not options:
            return ""
        # A small hash per slot, so the slots of one citation do not all
        # land on the same index.
        h = seed
        for ch in slot:
            h = (h * 31 + ord(ch)) % 2147483647
        return options[h % len(options)]

    if kind == "sortie" and facts.get("has_sortie"):
        deed.append(_fill(pick("opening_leader" if facts.get("leader") else "opening_member",
                               "leader" if facts.get("leader") else "member"), facts))
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
            air_n = sum(kills.values())
            if air_n >= 3:
                # "3 enemy aircraft: 3 Yak-9P" says it twice; with one type
                # the list becomes the type alone.
                one_type = len(kills) == 1
                deed.append(_fill(pick("air_many", "air"), dict(facts, air_n=air_n,
                                  air_list=(next(iter(kills)) + "s") if one_type else facts["air_list"])))
            elif items:
                deed.append(_fill(pick("air", "air"), facts))
            if facts.get("ground_n"):
                deed.append(_fill(pick("ground_flak", "ground_flak") if facts.get("hits") else pick("ground", "ground"), facts))
            if facts.get("wingman"):
                deed.append(_fill(pick("wingman", "wingman"), facts))
            if facts.get("hits") and outcome == "ok":
                deed.append(_fill(pick("hits", "hits"), facts))
            if outcome == "bailed":
                deed.append(_fill(pick("bailed", "bailed"), facts))
            elif outcome == "missing":
                deed.append(_fill(pick("lost", "lost"), facts))
    elif kind == "unit":
        deed.append(_fill(deed_t["unit_period"], facts))
    elif kind == "period" and facts.get("missions"):
        air, ground = facts.get("air_total") or 0, facts.get("ground_total") or 0
        if air and ground:
            deed.append(_fill(pick("period", "period"), facts))
        else:
            key = "period_air" if air else "period_ground" if ground else "period_plain"
            deed.append(_fill(deed_t.get(key) or deed_t["period"], facts))
    facts["deed"] = " ".join(deed)
    opening = _fill(template[0], facts).strip()
    closing = _fill(template[1], facts).strip() if len(template) > 1 else ""
    if is_naval:
        opening = _naval_text(opening, texts, country, family)
        closing = _naval_text(closing, texts, country, family)
    paragraphs = [opening]
    if kind != "unit" and facts["deed"]:
        paragraphs.append(facts["deed"])
    if closing:
        paragraphs.append(closing)
    return {"heading": texts.get("heading", "Citation"), "paragraphs": [p for p in paragraphs if p],
            "kind": kind, "family": family}
