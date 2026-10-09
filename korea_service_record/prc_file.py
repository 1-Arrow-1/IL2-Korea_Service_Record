"""
The documents of a Chinese pilot's personnel file, filled in by hand.

    merit booklet   立功證明書   prc_merit_book_cover.jpg / prc_merit_book_inside.jpg
                    the inside spread: profile (功臣簡歷) right, merit form 一 left;
                    every further merit on its own form page, numbered
    award           空軍司令部政治部獎狀   prc_award_cert_template.jpg
                    for the highest First and Special Class merit: the grades
                    approved at Air Force level (Hua Longyi's of 9 November
                    1951 is the model)

Both templates are period documents with the handwriting removed. What was
written by hand is written back here in a handwriting face; what was printed
(the form numeral) in a Ming face. Seals are typeset from the issuing
organisation's name, never copied from a real one, and the signatures of the
three Air Force officers are their names in the hand face, not their hands.

A merit was recorded, not decorated, so the booklet holds every merit; the
Combat Hero title is not a merit grade and has no form of its own - it is
noted on the form of the sortie that earned it, as period records do.

Every field also carries a tooltip region: what the printed label means and
what was written in it, in the reader's language (locales/prc/<lang>.json).
"""

import functools
import hashlib
import io
import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import hanzi
from .filetips import biography_tips, long_date

HERE = Path(__file__).resolve().parent
CERTS = HERE / "static" / "images" / "certificates"
BOOK_INSIDE = CERTS / "prc_merit_book_inside.jpg"
BOOK_COVER = CERTS / "prc_merit_book_cover.jpg"
AWARD_TEMPLATE = CERTS / "prc_award_cert_template.jpg"
HAND_FONT = CERTS / "LXGWWenKaiTC-PRC.ttf"
HAND_CHARS = CERTS / "LXGWWenKaiTC-PRC.chars.txt"
TIPS = HERE / "locales" / "prc"

PEN = (34, 38, 64)          # the booklet's ink
BRUSH = (24, 21, 19)        # the certificate's
SEAL = (190, 38, 34)

# -- what the awards are ------------------------------------------------------

MERITS = {**{i: "third" for i in range(502005, 502010)},
          **{i: "second" for i in range(502010, 502015)},
          **{i: "first" for i in range(502015, 502018)},
          **{i: "special" for i in range(502018, 502020)}}
HEROES = {502020: "third", 502021: "second", 502022: "first"}
GRADE_ZH = {"third": "三等", "second": "二等", "first": "一等", "special": "特等"}
# Grades whose merit Air Force headquarters approved - and certified.
CERTIFIED = ("first", "special")


def kind_of(award_id: int) -> Optional[str]:
    """'merit', 'hero' or None for every other award."""
    if award_id in MERITS:
        return "merit"
    if award_id in HEROES:
        return "hero"
    return None


# -- the unit -------------------------------------------------------------------

# Game unit code -> (regiment, division). The codes are the regiment numbers;
# the divisions are those the regiments belonged to in Korea.
UNITS = {502004: (4, 2), 502007: (7, 3), 502009: (9, 3), 502010: (10, 4),
         502012: (12, 4), 502016: (16, 6), 502018: (18, 6), 502034: (34, 12),
         502036: (36, 12), 502040: (40, 14), 502042: (42, 14), 502043: (43, 15),
         502045: (45, 15)}


def unit(code: int) -> Tuple[str, Dict[str, int]]:
    reg, div = UNITS.get(int(code or 0), (0, 0))
    if not reg:
        return "空軍", {}
    return f"空軍第{hanzi.number(div)}師第{hanzi.number(reg)}團", {"division": div, "regiment": reg}


# The approving authority of each grade, under the merit rules of the
# Volunteers: the regiment, the division, the Volunteers' air force, and for
# Special Class merit Air Force headquarters itself.
def approver(grade: str, code: int) -> Tuple[str, str]:
    reg, div = UNITS.get(int(code or 0), (0, 0))
    if grade == "third" and reg:
        return f"空軍第{hanzi.number(div)}師第{hanzi.number(reg)}團", "approver_regiment"
    if grade in ("third", "second") and div:
        return f"空軍第{hanzi.number(div)}師", "approver_division"
    if grade in ("third", "second", "first"):
        return "中國人民志願軍空軍", "approver_cpvaf"
    return "中國人民解放軍空軍司令部", "approver_hq"


# The PLA had no ranks until 1955: the documents name the post. The game's
# rank picks it.
POSTS = [("飛行員", "post_pilot"), ("副中隊長", "post_deputy_flight"), ("中隊長", "post_flight"),
         ("副大隊長", "post_deputy_group"), ("大隊長", "post_group"), ("副團長", "post_deputy_regiment"),
         ("團長", "post_regiment"), ("副師長", "post_deputy_division")]


def post(rank_id: int) -> Tuple[str, str]:
    return POSTS[max(0, min(len(POSTS) - 1, int(rank_id or 0)))]


# -- the profile, from the fourteen Chinese biographies -------------------------

# biographyId -> province, county or city (both as the forms of 1951 name
# them: Harbin lay in Songjiang Province), their romanisation, family
# background, own status, and enlistment and Party entry where the
# biography says. What it does not say stays blank, as on real booklets.
PROFILES = {
    "502001": ("河南", "開封", "Henan", "Kaifeng", "middle_peasant", "student", "", "蘇聯", ""),
    "502002": ("江蘇", "江寧", "Jiangsu", "Jiangning", "poor_peasant", "peasant", "", "", ""),
    "502003": ("廣東", "番禺", "Guangdong", "Panyu", "rich_peasant", "peasant", "", "陝西", ""),
    "502004": ("松江", "哈爾濱", "Songjiang", "Harbin", "middle_peasant", "worker", "1945", "哈爾濱", "1945"),
    "502005": ("", "北京", "", "Beijing", "professional", "student", "", "華北", ""),
    "502006": ("", "上海", "", "Shanghai", "officer", "student", "", "", ""),
    "502007": ("江蘇", "松江", "Jiangsu", "Songjiang", "fisherman", "student", "", "蘇聯", ""),
    "502008": ("湖北", "武漢", "Hubei", "Wuhan", "officer", "soldier", "1931", "南京", ""),
    "502009": ("", "北京", "", "Beijing", "professional", "worker", "", "東北", ""),
    "502010": ("松江", "哈爾濱", "Songjiang", "Harbin", "middle_peasant", "worker", "", "蘇聯", ""),
    "502011": ("湖北", "漢陽", "Hubei", "Hanyang", "official", "student", "", "", ""),
    "502012": ("", "南京", "", "Nanjing", "officer", "student", "1938", "", ""),
    "502013": ("", "上海", "", "Shanghai", "officer", "student", "", "", ""),
    "502014": ("廣東", "廣州", "Guangdong", "Guangzhou", "official", "student", "", "", ""),
}
FAMILY_ZH = {"poor_peasant": "貧農", "middle_peasant": "中農", "rich_peasant": "富農", "fisherman": "漁民",
             "official": "職員", "officer": "軍官", "professional": "自由職業"}
STATUS_ZH = {"student": "學生", "peasant": "農民", "worker": "工人", "soldier": "軍人"}
PLACE_PY = {"蘇聯": "Soviet Union", "陝西": "Shaanxi", "哈爾濱": "Harbin", "華北": "North China",
            "南京": "Nanjing", "東北": "Northeast China"}

# Air Force headquarters in 1951-1953: commander, deputy political commissar
# and director of the political department, chief of staff - the three who
# signed Hua Longyi's certificate.
SIGNERS = ("劉亞樓", "吳法憲", "王秉璋")
SIGNERS_PY = ("Liu Yalou", "Wu Faxian", "Wang Bingzhang")


# -- reader-language tooltips ---------------------------------------------------

@functools.lru_cache(maxsize=8)
def tips(lang: str) -> Dict[str, str]:
    for code in (lang, "en"):
        try:
            return json.loads((TIPS / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _t(lang: str, key: str, **values) -> str:
    text = tips(lang).get(key) or tips("en").get(key) or key
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def tip(lang: str, label: str, value: str = "") -> str:
    """'Merit grade: Second Class' - the label in the reader's words, then what was written."""
    head = _t(lang, label)
    return f"{head}: {value}" if value else head


# -- names, places, kills -------------------------------------------------------

def chinese_name(first: str, last: str, resolver) -> str:
    """The game's pinyin name back to characters, surname first, traditional."""
    from .native_names import native
    parts = [native(word, resolver, "chs") for word in (last, first)]
    return hanzi.name_to_trad("".join(parts)) if all(parts) else ""


def aircraft_type(name: str) -> str:
    """'F-86A-5' -> 'F-86': the type is what a merit record names."""
    m = re.match(r"^([A-Z]{1,3}-\d+)", name or "")
    return m.group(1) if m else (name or "")


def kills_zh(kills: Dict[str, int]) -> str:
    merged: Dict[str, int] = {}
    for name, n in kills.items():
        merged[aircraft_type(name)] = merged.get(aircraft_type(name), 0) + n
    return "、".join(f"{t}型機{hanzi.number(n)}架" for t, n in merged.items())


def kills_tip(lang: str, kills: Dict[str, int]) -> str:
    merged: Dict[str, int] = {}
    for name, n in kills.items():
        merged[aircraft_type(name)] = merged.get(aircraft_type(name), 0) + n
    return ", ".join(_t(lang, "kill_item", n=n, type=t) for t, n in merged.items())


# -- assembling the file --------------------------------------------------------

def assemble(zh: Dict[str, Any], reader: Dict[str, Any], lang: str, resolver) -> Dict[str, Any]:
    """
    Everything the documents say, in Chinese, with its reader-language
    tooltip. ``zh`` and ``reader`` are CareerAggregator.prc_merits() in
    Chinese and in the reader's language: the same entries, named twice.
    """
    name = chinese_name(zh["first_name"], zh["last_name"], resolver)
    unit_zh, unit_n = unit(zh["unit_code"])
    unit_tip = (_t(lang, "unit_value", **unit_n) if unit_n else _t(lang, "unit_af"))
    rows = list(zip(zh["entries"], reader["entries"]))
    merits = [(z, r) for z, r in rows if z["kind"] == "merit"]
    heroes = [(z, r) for z, r in rows if z["kind"] == "hero"]
    hero_on = {z["earned"]: (z, r) for z, r in heroes}

    forms = []
    for n, (z, r) in enumerate(merits, start=1):
        grade = MERITS[z["type"]]
        post_zh, post_key = post(z["rank_id"])
        deed, deed_tip = _deed(z, r, lang)
        hero = hero_on.pop(z["earned"], None)
        if hero:
            cls = HEROES[hero[0]["type"]]
            deed += f"同時被授予{GRADE_ZH[cls]}戰鬥英雄稱號。"
            deed_tip += " " + _t(lang, "hero_line", cls=_t(lang, "class_" + cls))
        appr, appr_key = approver(grade, zh["unit_code"])
        forms.append({
            "n": n, "type": z["type"], "grade": grade, "earned": z["earned"],
            "unit": unit_zh, "post": post_zh, "grade_zh": GRADE_ZH[grade] + "功",
            "date_zh": hanzi.date(z["earned"], day=False), "deed": deed, "approver": appr,
            "tips": {
                "title": tip(lang, "form_title", hanzi.number(n) + " (" + str(n) + ")"),
                "unit": tip(lang, "label_unit", unit_tip),
                "post": tip(lang, "label_post", _t(lang, post_key) + " · " + _t(lang, "game_rank", rank=r["rank_name"])),
                "grade": tip(lang, "label_grade", _t(lang, "grade_" + grade)),
                "date": tip(lang, "label_merit_date", long_date(lang, z["earned"])),
                "deed": tip(lang, "label_deed", deed_tip),
                "approver": tip(lang, "label_approver", _t(lang, appr_key, **unit_n)),
                "responsible": tip(lang, "label_responsible"),
            },
        })

    first = merits[0][0] if merits else None
    profile = _profile(zh, name, unit_zh, unit_tip, first, reader, lang)

    certs = []
    for grade in CERTIFIED:
        held = [(z, r) for z, r in merits if MERITS[z["type"]] == grade]
        if held:
            z, r = held[-1]
            certs.append({"type": z["type"], "grade": grade, "earned": z["earned"], "name": name,
                          "tips": _cert_tips(lang, name, reader, grade, z["earned"])})
    certs.sort(key=lambda c: c["earned"])

    hero_pages = [{"type": z["type"], "cls": HEROES[z["type"]], "earned": z["earned"],
                   "title_zh": GRADE_ZH[HEROES[z["type"]]] + "戰鬥英雄",
                   "date_zh": hanzi.date(z["earned"]), "name": name,
                   "tip_title": _t(lang, "hero_title", cls=_t(lang, "class_" + HEROES[z["type"]])),
                   "tip_date": long_date(lang, z["earned"]),
                   "tip_by": _t(lang, "hero_by")} for z, r in heroes]
    return {"name_zh": name, "unit_zh": unit_zh, "unit_tip": unit_tip, "profile": profile,
            "forms": forms, "certs": certs, "heroes": hero_pages}


@functools.lru_cache(maxsize=1)
def _hand_chars() -> Optional[str]:
    """The characters the subset face holds, listed beside it by make_prc_font.py."""
    try:
        return HAND_CHARS.read_text(encoding="utf-8")
    except OSError:
        return None


def writable(text: str) -> bool:
    """Whether the hand face has every character (some game place names carry Hangul)."""
    chars = _hand_chars()
    return chars is None or all(c in chars for c in text)


def _deed(z: Dict[str, Any], r: Dict[str, Any], lang: str) -> Tuple[str, str]:
    day = hanzi.date(z["earned"])
    when = long_date(lang, z["earned"])
    if z["flown"] and z["kills"]:
        place = hanzi.to_trad(z["place"])
        if not writable(place):
            place = ""
        text = (f"{day}於{place}上空與敵機空戰，擊落敵{kills_zh(z['kills'])}。" if place
                else f"{day}與敵機空戰，擊落敵{kills_zh(z['kills'])}。")
        tip_text = _t(lang, "deed_combat" if place else "deed_combat_noplace",
                      date=when, place=r["place"], kills=kills_tip(lang, r["kills"]))
        if z["outcome"] == "bailed":
            text += "座機中彈後跳傘。"
            tip_text += " " + _t(lang, "deed_bailed")
        elif z["hits"]:
            text += "座機中彈，仍堅持戰鬥，安全返航。"
            tip_text += " " + _t(lang, "deed_hit")
        return text, tip_text
    return f"{day}在空戰中英勇機智，戰績卓著。", _t(lang, "deed_general", date=when)


def _age(birth: str, on: str) -> Optional[int]:
    try:
        b = [int(x) for x in birth[:10].split(".")]
        d = [int(x) for x in on[:10].split(".")]
    except ValueError:
        return None
    return d[0] - b[0] - ((d[1], d[2]) < (b[1], b[2]))


def _profile(zh, name, unit_zh, unit_tip, first, reader, lang) -> Dict[str, Any]:
    on = first["earned"] if first else ""
    rank_id = first["rank_id"] if first else zh["rank_id"]
    post_zh, post_key = post(rank_id)
    prof = PROFILES.get(str(zh["bio_id"]))
    age = _age(zh["birth_date"], on) if on else None
    out = {"unit": unit_zh, "post": post_zh, "name": name,
           "age": (hanzi.number(age) + "歲") if age is not None and 0 < age < 100 else "", "sex": "男",
           "province": "", "county": "", "family": "", "status": "", "enlisted": "", "party": ""}
    t = {"title": tip(lang, "profile_title"),
         "unit": tip(lang, "label_unit", unit_tip),
         "post": tip(lang, "label_post", _t(lang, post_key)),
         "original_name": tip(lang, "label_original_name"),
         "name": tip(lang, "label_current_name", reader["name"]),
         "age": tip(lang, "label_age", str(age) if out["age"] else ""),
         "sex": tip(lang, "label_sex", _t(lang, "sex_male")),
         "native": tip(lang, "label_native"), "family": tip(lang, "label_family"),
         "status": tip(lang, "label_status"), "enlisted": tip(lang, "label_enlisted"),
         "party": tip(lang, "label_party"), "remarks": tip(lang, "label_remarks")}
    if prof:
        prov, county, prov_py, county_py, family, status, enl_y, enl_p, party_y = prof
        out.update({"province": prov, "county": county, "family": FAMILY_ZH[family],
                    "status": STATUS_ZH[status],
                    "enlisted": (hanzi.year(int(enl_y)) + "年" if enl_y else "") + (("於" if enl_y else "") + enl_p if enl_p else ""),
                    "party": hanzi.year(int(party_y)) + "年" if party_y else ""})
        t["native"] = tip(lang, "label_native", ", ".join(x for x in (prov_py, county_py) if x))
        t["family"] = tip(lang, "label_family", _t(lang, "family_" + family))
        t["status"] = tip(lang, "label_status", _t(lang, "status_" + status))
        if enl_y or enl_p:
            t["enlisted"] = tip(lang, "label_enlisted", " · ".join(x for x in (enl_y, PLACE_PY.get(enl_p, "")) if x))
        if party_y:
            t["party"] = tip(lang, "label_party", party_y)
    out["tips"] = t
    return out


def _cert_tips(lang, name, reader, grade, earned) -> Dict[str, str]:
    g = _t(lang, "grade_" + grade)
    return {
        "heading": tip(lang, "cert_heading"),
        "name": tip(lang, "cert_name", reader["name"]),
        "body": _t(lang, "cert_body", grade=g),
        "grade": tip(lang, "label_grade", g),
        "commander": tip(lang, "cert_commander", SIGNERS_PY[0]),
        "polcom": tip(lang, "cert_polcom", SIGNERS_PY[1]),
        "chief": tip(lang, "cert_chief", SIGNERS_PY[2]),
        "date": tip(lang, "cert_date", long_date(lang, earned)),
        "seal": tip(lang, "cert_seal"),
    }


# -- the file's own pages ---------------------------------------------------------

# The typeset pages (cover, record, decorations): their Chinese, keyed like
# the tooltips, which explain each in the reader's language.
PAGE_ZH = {
    "cover_title": "幹部履歷表", "contents": "目錄",
    "part_record": "立功受獎登記", "part_booklet": "立功證明書", "part_certs": "獎狀",
    "part_heroes": "戰鬥英雄", "part_medals": "獎章", "part_biography": "簡歷",
    "label_name": "姓名", "label_sex": "性別", "label_born": "出生年月", "label_native": "籍貫",
    "label_family": "家庭出身", "label_status": "本人成份", "label_enlisted": "何時何地入伍",
    "label_party": "何時入黨", "label_unit": "部別", "label_post": "職別",
    "record_title": "立功受獎登記", "col_date": "日期", "col_award": "功別或獎章",
    "combat_title": "戰績", "stat_sorties": "出擊次數", "stat_hours": "飛行小時",
    "stat_air": "擊落敵機", "stat_ground": "擊毀地面目標",
    "medals_title": "獎章", "biography_title": "簡歷", "hero_by": "中國人民志願軍總部授予",
}


def page_strings(lang: str) -> Dict[str, Dict[str, str]]:
    """Each Chinese heading with its reader-language tooltip."""
    return {k: {"zh": v, "tip": _t(lang, k)} for k, v in PAGE_ZH.items()}


def file_json(career_id: str, pilot_id: int, zh_agg, reader_agg, lang: str) -> Optional[Dict[str, Any]]:
    """Everything the Chinese personnel file shows, for personnel.js."""
    zh = zh_agg.prc_merits(career_id, pilot_id)
    reader = reader_agg.prc_merits(career_id, pilot_id)
    detail = reader_agg.career_detail(career_id, pilot_id)
    zh_detail = zh_agg.career_detail(career_id, pilot_id)
    if zh is None or reader is None or detail is None or zh_detail is None:
        return None
    doc = assemble(zh, reader, lang, zh_agg.resolver)
    base = f"/api/prc-doc/{career_id}/{pilot_id}"
    spread_size, form_size, cert_size = size_of(BOOK_INSIDE), (768, 1024), size_of(AWARD_TEMPLATE)
    forms = doc["forms"]
    images = [{"part": "booklet", "src": "/static/images/certificates/prc_merit_book_cover.jpg",
               "size": list(size_of(BOOK_COVER)), "regions": [[0, 0, *size_of(BOOK_COVER), tip(lang, "booklet_cover")]]},
              {"part": "booklet", "src": base + "/spread", "size": list(spread_size),
               "regions": spread_regions(forms[0] if forms else _blank_form(lang), doc["profile"])}]
    images += [{"part": "booklet", "src": f"{base}/form-{f['n']}", "size": list(form_size),
                "regions": form_regions(f), "pair": True} for f in forms[1:]]
    images += [{"part": "certs", "src": f"{base}/cert-{c['type']}", "size": list(cert_size),
                "regions": cert_regions(c)} for c in doc["certs"]]

    zh_awards = {a["type"]: a for a in zh_detail.get("awards") or []}
    medals = []
    for a in detail.get("awards") or []:
        if a.get("pending") or a["type"] in MERITS:
            continue
        medals.append({"type": a["type"], "earned": a.get("earned") or "",
                       "name_zh": hanzi.to_trad((zh_awards.get(a["type"]) or {}).get("name") or ""),
                       "name_tip": a.get("name") or ""})
    # One row per merit grade, its latest awarding (the name counts them:
    # 三等功（第三次授予）), with the earlier ones' dates beneath - as the
    # USAF record lists a decoration as worn. The booklet keeps every form.
    record = []
    latest: Dict[str, Dict[str, Any]] = {}
    for z, r in zip(zh["entries"], reader["entries"]):
        row = {"date_zh": hanzi.date(z["earned"]), "date": z["earned"],
               "name_zh": hanzi.to_trad(z["name"]), "name_tip": r["name"], "earlier": []}
        if z["kind"] == "merit":
            grade = MERITS[z["type"]]
            if grade in latest:
                row["earlier"] = latest[grade]["earlier"] + [
                    {k: latest[grade][k] for k in ("date_zh", "date", "name_zh", "name_tip")}]
            latest[grade] = row
        else:
            record.append(row)
    record += latest.values()
    for m in medals:
        if m["type"] not in HEROES:
            record.append({"date_zh": hanzi.date(m["earned"]), "date": m["earned"],
                           "name_zh": m["name_zh"], "name_tip": m["name_tip"]})
    record.sort(key=lambda r: r["date"])
    bio = zh_agg.biography(career_id, pilot_id) or {}
    biography = [hanzi.to_trad(p) for p in bio.get("paragraphs") or []]
    player = detail.get("player") or {}
    post_now, post_key = post(zh["rank_id"])
    return {
        "pilot": player,
        "post_now": post_now,
        "post_now_tip": tip(lang, "label_post", _t(lang, post_key) + " · " +
                            _t(lang, "game_rank", rank=player.get("rank") or "")),
        "name_zh": doc["name_zh"], "unit_zh": doc["unit_zh"], "unit_tip": doc["unit_tip"],
        "profile": doc["profile"], "born_zh": hanzi.date(zh["birth_date"]) if zh["birth_date"] else "",
        "born": long_date(lang, zh["birth_date"]) if zh["birth_date"] else "",
        "strings": page_strings(lang),
        "images": images, "heroes": doc["heroes"], "medals": medals, "record": record,
        "biography": biography,
        "biography_tips": biography_tips(reader_agg.biography(career_id, pilot_id) or {},
                                          len(biography), lang),
        "bio_fields": {"name": doc["name_zh"], "firstName": doc["name_zh"][1:], "lastName": doc["name_zh"][:1],
                       "birthDate": hanzi.date(zh["birth_date"]) if zh["birth_date"] else "",
                       "startRank": post(zh["rank_id"])[0]},
    }


def _blank_form(lang: str) -> Dict[str, Any]:
    return {"tips": {k: tip(lang, v) for k, v in (
        ("title", "form_title"), ("unit", "label_unit"), ("post", "label_post"), ("grade", "label_grade"),
        ("date", "label_merit_date"), ("deed", "label_deed"), ("approver", "label_approver"),
        ("responsible", "label_responsible"))}}


def render_doc(career_id: str, pilot_id: int, doc: str, zh_agg) -> Optional[bytes]:
    """One document image: 'spread', 'form-<n>' or 'cert-<award id>'."""
    zh = zh_agg.prc_merits(career_id, pilot_id)
    if zh is None:
        return None
    built = assemble(zh, zh, "zh", zh_agg.resolver)
    forms = built["forms"]
    if doc == "spread":
        return render_spread(built["profile"], forms[0] if forms else None)
    if doc.startswith("form-"):
        n = int(doc[5:]) if doc[5:].isdigit() else 0
        form = next((f for f in forms if f["n"] == n), None)
        return render_form(form) if form else None
    if doc.startswith("cert-"):
        cert = next((c for c in built["certs"] if str(c["type"]) == doc[5:]), None)
        return render_cert(cert) if cert else None
    return None


# -- hover regions (template pixels) --------------------------------------------

def spread_regions(f: Dict[str, Any], p: Dict[str, Any]) -> List[List[Any]]:
    t, pt = f["tips"], p["tips"]
    return [
        [630, 220, 70, 330, t["title"]],
        [545, 112, 75, 410, t["unit"]], [545, 640, 75, 300, t["post"]],
        [468, 112, 77, 410, t["grade"]], [468, 640, 77, 300, t["date"]],
        [238, 112, 230, 810, t["deed"]], [165, 112, 71, 810, t["approver"]],
        [95, 112, 70, 810, t["responsible"]],
        [1395, 150, 60, 420, pt["title"]],
        [1301, 112, 75, 410, pt["unit"]], [1301, 637, 75, 300, pt["post"]],
        [1224, 112, 77, 410, pt["original_name"]], [1224, 637, 77, 300, pt["age"]],
        [1145, 112, 79, 410, pt["name"]], [1145, 637, 79, 300, pt["sex"]],
        [1071, 112, 74, 820, pt["native"]],
        [993, 112, 78, 410, pt["family"]], [993, 637, 78, 300, pt["status"]],
        [916, 112, 77, 410, pt["enlisted"]], [916, 637, 77, 300, pt["party"]],
        [846, 112, 70, 820, pt["remarks"]],
    ]


def form_regions(f: Dict[str, Any]) -> List[List[Any]]:
    return [r for r in spread_regions(f, {"tips": {k: "" for k in (
        "title", "unit", "post", "original_name", "age", "name", "sex", "native", "family",
        "status", "enlisted", "party", "remarks")}}) if r[0] < 768]


def cert_regions(c: Dict[str, Any]) -> List[List[Any]]:
    t = c["tips"]
    return [
        [1110, 200, 105, 700, t["heading"]],
        [1000, 170, 70, 400, t["name"]],
        [650, 250, 310, 600, t["body"]],
        [745, 390, 60, 215, t["grade"]],
        [550, 495, 50, 420, t["commander"]],
        [455, 495, 80, 420, t["polcom"]],
        [395, 495, 55, 420, t["chief"]],
        [280, 230, 75, 640, t["date"]],
        [150, 520, 130, 160, t["seal"]],
    ]


# -- drawing --------------------------------------------------------------------

def _font(size: int, printed: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if printed:
        candidates += [windir / "simsun.ttc", windir / "mingliu.ttc"]
    candidates += [HAND_FONT, windir / "kaiu.ttf", windir / "simkai.ttf", windir / "msjh.ttc"]
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _seed(*parts) -> random.Random:
    return random.Random(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest())


def vertical(draw, text: str, cx: float, top: float, bottom: float, size: int, ink,
             gap: float = 1.12, align: str = "top", printed: bool = False,
             rnd: Optional[random.Random] = None, stroke: int = 0) -> None:
    """Top to bottom, centred on cx; shrinks until it fits between top and bottom."""
    if not text:
        return
    while size > 12 and len(text) * size * gap > bottom - top:
        size -= 1
    f = _font(size, printed)
    step = size * gap
    span = len(text) * step
    y = top if align == "top" else (bottom - span if align == "bottom" else top + (bottom - top - span) / 2)
    for ch in text:
        w = draw.textlength(ch, font=f)
        jx = rnd.uniform(-1.5, 1.5) if rnd else 0
        draw.text((cx - w / 2 + jx, y), ch, font=f, fill=ink, stroke_width=stroke, stroke_fill=ink)
        y += step


def columns(draw, text: str, right: float, left: float, top: float, bottom: float, size: int,
            ink, pitch: float, rnd: Optional[random.Random] = None) -> None:
    """Several columns right to left, like the deed summary; shrinks to fit."""
    while size > 14:
        per = int((bottom - top) // (size * 1.08))
        cols = -(-len(text) // max(per, 1))
        if right - (cols - 1) * pitch >= left:
            break
        size -= 1
        pitch = max(size * 1.3, pitch - 1)
    f = _font(size)
    step = size * 1.08
    per = int((bottom - top) // step)
    x = right
    for i in range(0, len(text), per):
        y = top
        for ch in text[i:i + per]:
            w = draw.textlength(ch, font=f)
            jx = rnd.uniform(-1, 1) if rnd else 0
            draw.text((x - w / 2 + jx, y), ch, font=f, fill=ink)
            y += step
        x -= pitch


def seal(im: Image.Image, text: str, cx: float, cy: float, size: int, angle: float = 0.0) -> None:
    """A square red organisation seal, the name in columns read right to left."""
    import math
    n = len(text)
    cols = max(2, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)
    layer = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(layer)
    border = max(3, size // 22)
    d.rectangle((border, border, size - border - 1, size - border - 1), outline=255, width=border)
    inner = size - 4 * border
    cw, ch_ = inner / cols, inner / rows
    f = _font(int(min(cw, ch_) * 0.92))
    for i, c in enumerate(text):
        col, row = divmod(i, rows)
        x = size - 2 * border - (col + 0.5) * cw
        y = 2 * border + (row + 0.5) * ch_
        w = d.textlength(c, font=f)
        d.text((x - w / 2, y - f.size * 0.55), c, font=f, fill=255, stroke_width=1, stroke_fill=255)
    rnd = _seed(text, cx, cy)
    px = layer.load()
    for _ in range(size * 8):                      # worn ink
        px[rnd.randrange(size), rnd.randrange(size)] = 0
    layer = layer.filter(ImageFilter.GaussianBlur(0.7)).rotate(angle, resample=Image.BICUBIC)
    colour = Image.new("RGB", (size, size), SEAL)
    im.paste(colour, (int(cx - size / 2), int(cy - size / 2)), layer.point(lambda v: int(v * 0.82)))


def _form_left(im: Image.Image, f: Dict[str, Any]) -> None:
    d = ImageDraw.Draw(im)
    rnd = _seed(f["type"], f["earned"])
    vertical(d, f["unit"], 582, 250, 498, 26, PEN, rnd=rnd)
    vertical(d, f["post"], 582, 665, 925, 26, PEN, rnd=rnd)
    vertical(d, f["grade_zh"], 506, 250, 498, 28, PEN, rnd=rnd)
    vertical(d, f["date_zh"], 506, 665, 925, 26, PEN, rnd=rnd)
    columns(d, f["deed"], 396, 255, 118, 910, 24, PEN, 34, rnd=rnd)
    vertical(d, f["approver"], 200, 365, 905, 26, PEN, rnd=rnd)
    seal(im, f["approver"], 205, 760, 96, angle=rnd.uniform(-6, 6))


def _numeral(im: Image.Image, n: int) -> None:
    """The printed form number: cover the 一 with blank paper, print n."""
    if n == 1:
        return
    patch = im.crop((632, 560, 690, 616))
    im.paste(patch, (632, 490))
    d = ImageDraw.Draw(im)
    vertical(d, hanzi.number(n), 661, 494, 494 + 50 * len(hanzi.number(n)), 40, (30, 28, 26),
             gap=1.15, printed=True, stroke=1)


def _profile_right(im: Image.Image, p: Dict[str, Any]) -> None:
    d = ImageDraw.Draw(im)
    rnd = _seed(p["name"], p["unit"])
    vertical(d, p["unit"], 1338, 240, 495, 26, PEN, rnd=rnd)
    vertical(d, p["post"], 1338, 650, 920, 26, PEN, rnd=rnd)
    vertical(d, p["name"], 1184, 240, 495, 30, PEN, rnd=rnd)
    vertical(d, p["age"], 1262, 650, 920, 26, PEN, rnd=rnd)
    vertical(d, p["sex"], 1184, 650, 920, 26, PEN, rnd=rnd)
    vertical(d, p["province"], 1108, 245, 350, 26, PEN, align="center", rnd=rnd)
    vertical(d, p["county"], 1108, 392, 522, 26, PEN, align="center", rnd=rnd)
    vertical(d, p["family"], 1032, 240, 495, 26, PEN, rnd=rnd)
    vertical(d, p["status"], 1032, 650, 920, 26, PEN, rnd=rnd)
    vertical(d, p["enlisted"], 955, 240, 495, 26, PEN, rnd=rnd)
    vertical(d, p["party"], 955, 650, 920, 26, PEN, rnd=rnd)


def _jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def render_spread(profile: Dict[str, Any], form: Optional[Dict[str, Any]]) -> bytes:
    """The inside spread: profile on the right, the first merit on the left."""
    im = Image.open(BOOK_INSIDE).convert("RGB")
    _profile_right(im, profile)
    if form:
        _form_left(im, form)
    return _jpeg(im)


def render_form(form: Dict[str, Any]) -> bytes:
    """A further merit: the left-hand page alone, with its own number."""
    im = Image.open(BOOK_INSIDE).convert("RGB").crop((0, 0, 768, 1024))
    _numeral(im, form["n"])
    _form_left(im, form)
    return _jpeg(im)


def render_cert(cert: Dict[str, Any]) -> bytes:
    """The Air Force headquarters certificate for one merit."""
    im = Image.open(AWARD_TEMPLATE).convert("RGB")
    d = ImageDraw.Draw(im)
    rnd = _seed("cert", cert["type"], cert["earned"])
    vertical(d, cert["name"], 1032, 175, 405, 58, BRUSH, gap=1.08, align="bottom", rnd=rnd, stroke=1)
    for i, ch in enumerate(GRADE_ZH[cert["grade"]]):
        vertical(d, ch, 773, 427 + 85 * i, 427 + 85 * i + 66, 60, BRUSH, gap=1.0, rnd=rnd, stroke=1)
    try:
        y, m, dd = (int(x) for x in cert["earned"][:10].split("."))
    except ValueError:
        y = m = dd = 0
    if y:
        vertical(d, hanzi.year(y), 318, 250, 520, 50, BRUSH, gap=1.18, align="bottom", rnd=rnd, stroke=1)
        vertical(d, hanzi.number(m), 318, 574, 676, 46, BRUSH, gap=1.1, align="center", rnd=rnd, stroke=1)
        vertical(d, hanzi.number(dd), 318, 724, 856, 44, BRUSH, gap=1.08, align="center", rnd=rnd, stroke=1)
    for name, cx, top in zip(SIGNERS, (575, 494, 420), (650, 672, 650)):
        vertical(d, name, cx + rnd.uniform(-3, 3), top, top + 170, 40, BRUSH, gap=1.0, rnd=rnd)
    # over the year, as on Hua Longyi's
    seal(im, "中國人民解放軍空軍司令部", 300, 420, 124, angle=rnd.uniform(-4, 4))
    return _jpeg(im)


def size_of(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size
