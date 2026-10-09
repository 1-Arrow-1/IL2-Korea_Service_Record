"""
The documents of a Soviet pilot's personnel file, in Russian.

    order booklet   орденская книжка, 1948 edition (Москва. Гознак. 1948)
                    ussr_order_book_cover / _name / _awards / _back.jpg:
                    the name page in his hand's place, every order and medal
                    on the award page with its number, signed for the
                    Presidium by its secretary
    Hero            грамота Героя Советского Союза, ussr_hero_cert_template.jpg
    typed pages     личное дело (cover), послужной список (record of service),
                    аттестация (attestation), выписки из приказов (one per
                    promotion) - typed, as they were; drawn by personnel_ussr.js
    nomination      наградной лист for each order at its latest awarding -
                    the existing certificate page, embedded

Handwriting is Bad Script in violet ink, the ink of a 1950s Soviet office.
Seals are typeset from the issuing body's name; the officials' names are
written in the hand face, never their own hands. Order numbers are made
up within the range each order had reached at the date (estimates; the
registers are not public), the same number every time for the same award.

Every field carries a tooltip in the reader's language (locales/ussr/).
"""

import functools
import hashlib
import io
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import russian as ru
from .filetips import biography_tips, long_date

HERE = Path(__file__).resolve().parent
CERTS = HERE / "static" / "images" / "certificates"
BOOK_COVER = CERTS / "ussr_order_book_cover.jpg"
BOOK_NAME = CERTS / "ussr_order_book_name.jpg"
BOOK_AWARDS = CERTS / "ussr_order_book_awards.jpg"
BOOK_BACK = CERTS / "ussr_order_book_back.jpg"
HERO_TEMPLATE = CERTS / "ussr_hero_cert_template.jpg"
HAND_FONT = CERTS / "BadScript-Regular.ttf"
TIPS = HERE / "locales" / "ussr"

INK = (78, 48, 138)          # violet office ink
SEAL_INK = (92, 64, 160)

HERO = 501022
# What the booklet lists: orders by the name after "Награжден орденом",
# medals in full and without a number ("б/н"), as the books were kept.
BOOK = {
    501024: ("Ленина", "lenin"), HERO: ("Медаль «Золотая Звезда»", "gold_star"),
    501016: ("Красного Знамени", "red_banner"), 501018: ("Красного Знамени", "red_banner"),
    501020: ("Красного Знамени", "red_banner"), 501014: ("Суворова III степени", "suvorov3"),
    501012: ("Александра Невского", "nevsky"), 501006: ("Красной Звезды", "red_star"),
    501002: ("Медаль «За отвагу»", None), 501004: ("Медаль «За боевые заслуги»", None),
}
# The nomination sheet is drawn for each order at its latest awarding.
LADDERS = {501016: "red_banner", 501018: "red_banner", 501020: "red_banner"}

# Number ranges by date: the first and last number in use between November
# 1950 and July 1953. Red Star 1951 ran 2 861 237 - 3 001 481; the rest are
# estimates from the same tables.
RANGES = {
    "red_star": (2_830_000, 3_240_000), "red_banner": (355_000, 415_000),
    "lenin": (95_000, 125_000), "gold_star": (9_000, 10_300),
    "nevsky": (41_000, 42_500), "suvorov3": (4_900, 5_200),
}
WAR = ("1950.11.01", "1953.07.27")

# -- the unit ------------------------------------------------------------------

# Game unit code -> (regiment, guards, division, PVO division, independent
# night regiment). The divisions are those of the 64th Fighter Aviation Corps.
UNITS = {
    501016: (16, False, 97, True, False), 501017: (17, False, 303, False, False),
    501018: (18, True, 303, False, False), 501097: (0, False, 97, True, False),
    501147: (147, True, 133, False, False), 501148: (148, True, 97, True, False),
    501149: (147, True, 133, False, False), 501176: (176, True, 324, False, False),
    501196: (196, False, 324, False, False), 501224: (224, False, 32, False, False),
    501298: (298, False, 0, False, True), 501300: (298, False, 0, False, True),
    501351: (351, False, 0, False, True), 501352: (351, False, 0, False, True),
    501494: (494, False, 190, False, False), 501518: (518, False, 216, False, False),
    501523: (523, False, 303, False, False), 501535: (535, False, 32, False, False),
    501536: (535, False, 32, False, False), 501726: (726, False, 133, False, False),
    501821: (821, False, 190, False, False), 501878: (878, False, 216, False, False),
}


def unit(code: int) -> Dict[str, Any]:
    """The regiment, as typed in the documents ('176 гв. иап, 324 иад')."""
    reg, guards, div, pvo, night = UNITS.get(int(code or 0), (0, False, 0, False, False))
    regiment = (f"{reg} {'гв. ' if guards else ''}{'ониап' if night else 'иап'}") if reg else ""
    division = f"{div} иад{' ПВО' if pvo else ''}" if div else ""
    short = ", ".join(x for x in (regiment, division) if x) or "64 иак"
    return {"regiment": regiment, "division": division, "short": short, "number": reg, "div": div,
            "guards": guards, "night": night}


# Posts by rank: nominative, dative, genitive and the tooltip key.
POSTS = [("лётчик", "лётчику", "лётчика", "post_pilot"),
         ("старший лётчик", "старшему лётчику", "старшего лётчика", "post_senior_pilot"),
         ("командир звена", "командиру звена", "командира звена", "post_flight"),
         ("командир эскадрильи", "командиру эскадрильи", "командира эскадрильи", "post_squadron"),
         ("заместитель командира полка", "заместителю командира полка", "заместителя командира полка",
          "post_deputy_regiment"),
         ("командир полка", "командиру полка", "командира полка", "post_regiment"),
         ("командир дивизии", "командиру дивизии", "командира дивизии", "post_division"),
         ("командир корпуса", "командиру корпуса", "командира корпуса", "post_corps")]


def post(rank_id: int) -> Tuple[str, str, str, str]:
    return POSTS[max(0, min(len(POSTS) - 1, int(rank_id or 0)))]


# The patronymic, from the father each biography names; 501005 names none.
PATRONYMICS = {"501001": "Михайлович", "501002": "Юрьевич", "501003": "Игоревич", "501004": "Дмитриевич",
               "501006": "Васильевич", "501007": "Сергеевич", "501008": "Талгатович", "501009": "Андреевич",
               "501010": "Дмитриевич", "501011": "Сергеевич", "501012": "Иванович", "501013": "Сергеевич",
               "501014": "Иванович"}
COMMON_PATRONYMICS = ("Иванович", "Петрович", "Николаевич", "Алексеевич", "Фёдорович", "Степанович",
                      "Васильевич", "Михайлович", "Григорьевич", "Павлович")


def patronymic(bio_id: str, name: str) -> str:
    return PATRONYMICS.get(str(bio_id)) or COMMON_PATRONYMICS[_hash(name) % len(COMMON_PATRONYMICS)]


# -- officials by date ------------------------------------------------------------

def presidium(ymd: str) -> Tuple[str, str, str, str]:
    """Chairman and secretary of the Presidium of the Supreme Soviet: hand, latin."""
    if ymd < "1953.03.15":
        return "Н. Шверник", "А. Горкин", "Nikolai Shvernik", "Alexander Gorkin"
    return "К. Ворошилов", "Н. Пегов", "Kliment Voroshilov", "Nikolai Pegov"


def corps_commander(ymd: str) -> Tuple[str, str]:
    """Commander of the 64th Fighter Aviation Corps: typed, latin."""
    if ymd < "1951.09.18":
        return "генерал-майор авиации И. Белов", "Major General Ivan Belov"
    if ymd < "1952.08.26":
        return "генерал-майор авиации Г. Лобов", "Major General Georgy Lobov"
    return "генерал-лейтенант авиации С. Слюсарев", "Lieutenant General Sidor Slyusarev"


def promotion_order(new_rank: int, ymd: str) -> Dict[str, str]:
    """Whose order conferred the rank, and who signed it."""
    if new_rank <= 2:
        return {"of": "Главнокомандующего Военно-Воздушными Силами", "kind": "приказа",
                "signed": "Главнокомандующий ВВС маршал авиации П. Жигарев",
                "key": "order_af", "latin": "Pavel Zhigarev"}
    if new_rank <= 5:
        if ymd < "1953.03.15":
            return {"of": "Военного министра Союза ССР", "kind": "приказа",
                    "signed": "Военный министр Союза ССР Маршал Советского Союза А. Василевский",
                    "key": "order_war", "latin": "Aleksandr Vasilevsky"}
        return {"of": "Министра обороны Союза ССР", "kind": "приказа",
                "signed": "Министр обороны Союза ССР Маршал Советского Союза Н. Булганин",
                "key": "order_defence", "latin": "Nikolai Bulganin"}
    head = "И. Сталин" if ymd < "1953.03.06" else "Г. Маленков"
    return {"of": "Совета Министров Союза ССР", "kind": "постановления",
            "signed": f"Председатель Совета Министров Союза ССР {head}",
            "key": "order_council", "latin": "Joseph Stalin" if ymd < "1953.03.06" else "Georgy Malenkov"}


# -- numbers ------------------------------------------------------------------------

def _hash(*parts) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _days(ymd: str) -> int:
    try:
        y, m, d = (int(x) for x in ymd[:10].split("."))
    except ValueError:
        return 0
    return y * 372 + m * 31 + d


def order_number(kind: Optional[str], ymd: str, *seed) -> str:
    """A number within what the order had reached by that date; 'б/н' for a medal."""
    if kind is None:
        return "б/н"
    lo, hi = RANGES[kind]
    start, end = _days(WAR[0]), _days(WAR[1])
    frac = min(1.0, max(0.0, (_days(ymd) - start) / max(1, end - start)))
    spread = max(10, (hi - lo) // 60)
    return str(int(lo + (hi - lo) * frac) + _hash(kind, ymd, *seed) % spread)


# -- tooltips -------------------------------------------------------------------------

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
    head = _t(lang, label)
    return f"{head}: {value}" if value else head


# -- assembling ------------------------------------------------------------------------

def _book_entries(awards: List[Dict[str, Any]], seed: str) -> List[Dict[str, Any]]:
    out = []
    for a in awards:
        if a["type"] not in BOOK:
            continue
        line, kind = BOOK[a["type"]]
        out.append({"type": a["type"], "line": line, "earned": a["earned"], "received": a["received"],
                    "number": order_number(kind, a["earned"], seed, a["type"], len(out))})
    return out


def _attestation(basics, ru_names, bio, rank_id, post_ru, unit_info, stats, lang, start, end, levels) -> Dict[str, Any]:
    skill, courage, discipline = levels
    lines = []

    def add(key, ru_text, **values):
        lines.append({"ru": ru_text, "tip": _t(lang, key, **values)})

    add("att_loyal", "Делу партии Ленина – Сталина и социалистической Родине предан.")
    add(*_graded("att_skill", skill, (
        "Лётную подготовку имеет слабую, нуждается в дополнительной тренировке.",
        "Технику пилотирования освоил удовлетворительно, над ней необходимо работать.",
        "Технику пилотирования и боевое применение самолёта освоил хорошо.",
        "Лётную технику освоил отлично, в воздухе действует грамотно и уверенно.")))
    add(*_graded("att_courage", courage, (
        "В воздушных боях действует нерешительно.",
        "В воздушных боях действует осмотрительно.",
        "В воздушных боях действует смело и инициативно.",
        "В воздушных боях проявляет мужество, смелость и решительность.")))
    add(*_graded("att_discipline", discipline, (
        "Недостаточно дисциплинирован.",
        "Дисциплинирован, но имеет отдельные замечания.",
        "Дисциплинирован, исполнителен.",
        "Дисциплинирован, требователен к себе и подчинённым.")))
    n, k = int(stats.get("sorties") or 0), int(stats.get("air") or 0)
    hours = str(stats.get("hours") or "0").replace(".", ",")
    kills = (f"лично сбил {k} {ru.plural(k, 'самолёт', 'самолёта', 'самолётов')} противника" if k
             else "сбитых самолётов противника не имеет")
    add("att_combat", f"За период боевой работы произвёл {n} {ru.plural(n, 'боевой вылет', 'боевых вылета', 'боевых вылетов')}, "
        f"налёт {hours} ч, {kills}.", sorties=n, hours=stats.get("hours") or 0, kills=k)
    if skill >= 2 and courage >= 2 and rank_id < 7:
        nxt = post(rank_id + 1)
        conclusion = {"ru": f"Вывод: Занимаемой должности соответствует. Достоин выдвижения на должность {nxt[2]}.",
                      "tip": _t(lang, "att_promote", post=_t(lang, nxt[3]))}
    else:
        conclusion = {"ru": "Вывод: Занимаемой должности соответствует.", "tip": _t(lang, "att_keep")}
    return {
        "title": "АТТЕСТАЦИЯ",
        "subject": f"на {ru.rank(rank_id, 'gen')} {ru.full_name(*ru_names, case='gen')}",
        "period": f"за период с {ru.date(start)} г. по {ru.date(end)} г.",
        "facts": [("Год рождения", basics["birth_date"][:4] if basics["birth_date"] else "", "label_born"),
                  ("Национальность", bio.get("nationality", ""), "label_nationality"),
                  ("Партийность", bio.get("party", ""), "label_party"),
                  ("В Советской Армии", ("с " + bio["since"]) if bio.get("since") else "", "label_since"),
                  ("Занимаемая должность", f"{post_ru} {unit_info['short']}", "label_post")],
        "lines": lines, "conclusion": conclusion,
        "commander": f"Командир {unit_info['regiment'] or unit_info['short']}",
        "senior": "Заключение старших начальников: С выводом аттестации согласен.",
        "corps": "Командир 64 иак " + corps_commander(end)[0],
        "date": ru.date(end) + " г.",
        "tips": {"title": _t(lang, "att_title"), "subject": _t(lang, "att_subject", rank=stats.get("rank", ""),
                                                               name=stats.get("name", "")),
                 "period": _t(lang, "att_period", start=long_date(lang, start), end=long_date(lang, end)),
                 "commander": _t(lang, "att_commander"), "senior": _t(lang, "att_senior"),
                 "corps": _t(lang, "att_corps", name=corps_commander(end)[1]), "date": long_date(lang, end)},
    }


def _graded(key: str, level: int, texts) -> Tuple[str, str]:
    i = max(0, min(3, int(level)))
    return f"{key}_{i}", texts[i]


def assemble(basics: Dict[str, Any], detail_ru: Dict[str, Any], detail_tr: Dict[str, Any],
             awards_tr: Dict[int, str], lang: str, resolver, levels=(2, 2, 2)) -> Dict[str, Any]:
    """Everything the Soviet documents say, with its reader-language tooltip."""
    from . import citations
    from .native_names import native
    first = native(basics["first_name"], resolver, "rus") or basics["first_name"]
    last = native(basics["last_name"], resolver, "rus") or basics["last_name"]
    father = patronymic(basics["bio_id"], basics["first_name"] + basics["last_name"])
    names = (last, first, father)
    latin = f"{basics['first_name']} {basics['last_name']}".strip()
    seed = latin + str(basics["unit_code"])
    unit_info = unit(basics["unit_code"])
    rank_id = int(basics["rank_id"] or 0)
    post_ru, _dat, _gen, post_key = post(rank_id)
    bio = (citations.strings("rus").get("bios") or {}).get(str(basics["bio_id"]), {})
    bio_tr = (citations.strings(_game(lang)).get("bios_tr") or citations.strings("eng").get("bios_tr") or {}).get(
        str(basics["bio_id"]), {})
    player = detail_ru.get("player") or {}
    player_tr = detail_tr.get("player") or {}
    start, end = detail_ru.get("start_date") or "", detail_ru.get("current_date") or ""
    unit_tip = _t(lang, "unit_value", regiment=unit_info["number"] or "", division=unit_info["div"] or "",
                  guards=_t(lang, "guards") if unit_info["guards"] else "")

    entries = _book_entries(basics["awards"], seed)
    issued = min((e["received"] for e in entries), default="")
    chairman, secretary, chairman_lat, secretary_lat = presidium(issued or end)

    # promotions: one order extract each
    extracts = []
    previous = None
    for i, pr in enumerate(detail_ru.get("promotions") or []):
        rid = int(pr.get("rank_id") or 0)
        old = rid - 1 if previous is None else previous
        previous = rid
        when = str(pr.get("date") or "")[:10]
        order = promotion_order(rid, when)
        number = f"0{_hash(seed, 'order', i) % 900 + 100}"
        post_then = post(old)
        extracts.append({
            "head": f"ВЫПИСКА ИЗ {order['kind'].upper()} {order['of'].upper()}",
            "number": f"№ {number}", "date": f"{ru.date(when)} г.",
            "section": "(по личному составу)",
            "text": f"Присвоить воинское звание «{ru.rank(rid)}» {ru.rank(old, 'dat')} "
                    f"{ru.full_name(*names, case='dat')}, {post_then[1]} {unit_info['short']}.",
            "signed": "Подлинный подписал: " + order["signed"],
            "certified": f"Верно: Начальник штаба {unit_info['regiment'] or unit_info['short']}",
            "tips": {"head": _t(lang, order["key"]), "number": _t(lang, "order_number"),
                     "date": long_date(lang, when),
                     "text": _t(lang, "order_text", rank=_rank_tr(detail_tr, rid), name=latin,
                                post=_t(lang, post_then[3])),
                     "signed": _t(lang, "order_signed", name=order["latin"]),
                     "certified": _t(lang, "order_certified")},
        })

    record_awards = [{"date": a["earned"], "date_ru": ru.date(a["earned"]) + " г.",
                      "name": a["name"], "name_tip": awards_tr.get(a["type"], a["name"]),
                      "number": next((e["number"] for e in entries if e["type"] == a["type"]
                                      and e["earned"] == a["earned"]), "")}
                     for a in basics["awards"] if a["type"] in BOOK or 501050 <= a["type"] <= 501054]
    stats = {"sorties": player.get("sorties"), "hours": player.get("flight_hours"),
             "air": player.get("airborne"), "ground": player.get("ground_targets"),
             "rank": player_tr.get("rank", ""), "name": latin}
    out = {
        "names": {"last": last, "first": first, "father": father, "latin": latin},
        "unit": unit_info, "unit_tip": unit_tip, "rank_ru": ru.rank(rank_id), "rank_tip": player_tr.get("rank", ""),
        "post": post_ru, "post_tip": _t(lang, post_key),
        "bio": {k: bio.get(k, "") for k in ("born", "nationality", "party", "since", "battles")},
        "bio_tip": {k: bio_tr.get(k, "") for k in ("born", "nationality", "party", "since", "battles")},
        "book": {"entries": entries, "issued": issued, "secretary": secretary, "secretary_lat": secretary_lat,
                 "series": str(100000 + _hash(seed, "book") % 899999)},
        "extracts": extracts, "record_awards": record_awards, "stats": stats,
        "attestation": _attestation(basics, names, bio, rank_id, post_ru, unit_info, stats, lang, start, end, levels),
    }
    hero = next((a for a in basics["awards"] if a["type"] == HERO), None)
    if hero:
        gold = next((e["number"] for e in entries if e["type"] == HERO), "")
        h_chair, h_sec, h_chair_lat, h_sec_lat = presidium(hero["earned"])
        out["hero"] = {"earned": hero["earned"], "received": hero["received"], "number": gold,
                       "chairman": h_chair, "secretary": h_sec,
                       "chairman_lat": h_chair_lat, "secretary_lat": h_sec_lat}
    return out


def _rank_tr(detail_tr: Dict[str, Any], rank_id: int) -> str:
    for pr in detail_tr.get("promotions") or []:
        if int(pr.get("rank_id") or -1) == rank_id:
            return pr.get("rank", "")
    return str(rank_id)


def _game(lang: str) -> str:
    from .i18n import game_code
    return game_code(lang)


# -- hover regions -----------------------------------------------------------------------

def name_regions(doc: Dict[str, Any], lang: str) -> List[List[Any]]:
    n = doc["names"]
    return [[193, 183, 402, 458, _t(lang, "book_photo")],
            [90, 700, 610, 90, tip(lang, "book_signature", n["latin"])],
            [828, 240, 580, 90, tip(lang, "book_surname", n["latin"].split(" ")[-1])],
            [828, 355, 580, 90, tip(lang, "book_name", n["latin"].split(" ")[0])],
            [828, 470, 580, 90, tip(lang, "book_father", n["father"])]]


def award_regions(doc: Dict[str, Any], page: int, lang: str, names_tr: Dict[int, str]) -> List[List[Any]]:
    book = doc["book"]
    out = [[750, 190, 700, 740, _t(lang, "book_extract")]]
    for i, e in enumerate(book["entries"][page * 8:(page + 1) * 8]):
        y = 163 + 53 * i
        out.append([100, y - 45, 590, 52, tip(lang, "book_entry", f"{names_tr.get(e['type'], e['line'])} · "
                                                                   f"№ {e['number']} · {long_date(lang, e['earned'])}")])
    out += [[100, 650, 590, 90, tip(lang, "book_secretary", book["secretary_lat"])],
            [100, 750, 590, 70, tip(lang, "book_date", long_date(lang, book["issued"]))],
            [230, 870, 300, 60, _t(lang, "book_series")]]
    return out


def hero_regions(doc: Dict[str, Any], lang: str) -> List[List[Any]]:
    h = doc["hero"]
    return [[470, 280, 920, 70, _t(lang, "hero_heading")],
            [870, 380, 510, 95, tip(lang, "hero_to", doc["names"]["latin"])],
            [560, 480, 830, 140, _t(lang, "hero_citation")],
            [720, 600, 670, 130, _t(lang, "hero_decree", date=long_date(lang, h["earned"]))],
            [540, 800, 900, 100, _t(lang, "hero_signers", chairman=h["chairman_lat"], secretary=h["secretary_lat"])],
            [200, 890, 450, 60, tip(lang, "hero_issued", long_date(lang, h["received"]))],
            [200, 955, 200, 60, tip(lang, "hero_number", h["number"])],
            [60, 150, 330, 270, _t(lang, "hero_emblem")]]


# -- drawing -----------------------------------------------------------------------------

def _font(size: int, printed: bool = False) -> ImageFont.FreeTypeFont:
    import os
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    paths = [windir / "timesbd.ttf", windir / "georgiab.ttf"] if printed else [HAND_FONT, windir / "segoesc.ttf"]
    for path in paths:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def write(draw, text: str, x: float, baseline: float, size: int, right: Optional[float] = None,
          centre: bool = False, ink=INK, printed: bool = False) -> None:
    """One line of handwriting sitting on a printed line; shrinks to fit."""
    if not text:
        return
    f = _font(size, printed)
    if right is not None:
        while size > 12 and draw.textlength(text, font=f) > right - x:
            size -= 1
            f = _font(size, printed)
    w = draw.textlength(text, font=f)
    left = (x + ((right or x) - x - w) / 2) if centre and right else x
    draw.text((left, baseline), text, font=f, fill=ink, anchor="ls")


def _seal_emblem(size: int) -> Optional[Image.Image]:
    """The state emblem from the Hero template, as a mask for the seal's centre."""
    try:
        crop = Image.open(HERO_TEMPLATE).convert("L").crop((88, 168, 332, 408))
    except OSError:
        return None
    crop = crop.point(lambda v: 255 if v < 200 else 0).resize((size, size), Image.LANCZOS)
    return crop


def presidium_seal(size: int, seed: str) -> Image.Image:
    """Round seal of the Presidium: its name round the rim, the emblem inside."""
    s = size * 2
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    w = max(4, s // 70)
    d.ellipse((w, w, s - w, s - w), outline=255, width=w)
    inner = int(s * 0.30)
    d.ellipse((s / 2 - inner, s / 2 - inner, s / 2 + inner, s / 2 + inner), outline=255, width=max(2, w // 2))
    text = "ПРЕЗИДИУМ ВЕРХОВНОГО СОВЕТА СОЮЗА СОВЕТСКИХ СОЦИАЛИСТИЧЕСКИХ РЕСПУБЛИК • "
    f = _font(int(s * 0.072), printed=True)
    r = s * 0.40
    for i, ch in enumerate(text):
        a = -math.pi / 2 + 2 * math.pi * i / len(text)
        tile = Image.new("L", (int(s * 0.1), int(s * 0.1)), 0)
        ImageDraw.Draw(tile).text((tile.width / 2, tile.height / 2), ch, font=f, fill=255, anchor="mm")
        tile = tile.rotate(-math.degrees(a) - 90, resample=Image.BICUBIC)
        mask.paste(255, (int(s / 2 + r * math.cos(a) - tile.width / 2), int(s / 2 + r * math.sin(a) - tile.height / 2)), tile)
    emblem = _seal_emblem(int(inner * 1.5))
    if emblem is not None:
        mask.paste(255, (int(s / 2 - emblem.width / 2), int(s / 2 - emblem.height / 2)), emblem)
    rnd = random.Random(_hash(seed))
    px = mask.load()
    for _ in range(s * 30):
        px[rnd.randrange(s), rnd.randrange(s)] = 0
    mask = mask.filter(ImageFilter.GaussianBlur(1.0)).resize((size, size), Image.LANCZOS)
    return mask.rotate(rnd.uniform(-12, 12), resample=Image.BICUBIC)


def _stamp(im: Image.Image, mask: Image.Image, cx: float, cy: float, alpha: float = 0.75) -> None:
    colour = Image.new("RGB", mask.size, SEAL_INK)
    im.paste(colour, (int(cx - mask.width / 2), int(cy - mask.height / 2)), mask.point(lambda v: int(v * alpha)))


def _jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def render_name(doc: Dict[str, Any]) -> bytes:
    im = Image.open(BOOK_NAME).convert("RGB")
    d = ImageDraw.Draw(im)
    n = doc["names"]
    for text, y in ((n["last"], 298), (n["first"], 414), (n["father"], 530)):
        write(d, text, 840, y, 46, right=1400, centre=True)
    write(d, n["last"], 300, 742, 38, right=600)
    return _jpeg(im)


def render_awards(doc: Dict[str, Any], page: int = 0) -> bytes:
    im = Image.open(BOOK_AWARDS).convert("RGB")
    d = ImageDraw.Draw(im)
    book = doc["book"]
    for i, e in enumerate(book["entries"][page * 8:(page + 1) * 8]):
        y = 163 + 53 * i - 6
        write(d, e["line"], 112, y, 34, right=505)
        write(d, e["number"], 552, y, 34, right=682, centre=True)
    write(d, book["secretary"], 450, 706, 36, right=680, centre=True)
    if book["issued"]:
        yy, mm, dd = book["issued"][:10].split(".")
        write(d, str(int(dd)), 125, 784, 34, right=235, centre=True)
        write(d, ru.MONTHS_GEN[int(mm) - 1], 280, 784, 34, right=550, centre=True)
        write(d, yy[2:], 607, 784, 34, right=655, centre=True)
    write(d, book["series"], 340, 912, 34, ink=(30, 30, 34), printed=True)
    _stamp(im, presidium_seal(250, doc["names"]["latin"] + "book"), 285, 610)
    return _jpeg(im)


def render_hero(doc: Dict[str, Any]) -> bytes:
    im = Image.open(HERO_TEMPLATE).convert("RGB")
    d = ImageDraw.Draw(im)
    n, h = doc["names"], doc["hero"]
    write(d, ru.surname(n["last"], "dat"), 945, 406, 40, right=1365, centre=True)
    write(d, f"{ru.first_name(n['first'], 'dat')} {ru.patronymic(n['father'], 'dat')}", 895, 451, 40,
          right=1365, centre=True)
    # the formula of the Korea decrees, written on as the wartime ones were
    write(d, "за мужество и героизм,", 1105, 520, 34, right=1380)
    write(d, "проявленные при выполнении специального", 735, 560, 34, right=1380)
    write(d, "задания Правительства,", 735, 598, 34, right=1380)
    write(d, ru.date(h["earned"]), 978, 673, 34, right=1155, centre=True)
    write(d, h["chairman"], 1230, 842, 38, right=1440)
    write(d, h["secretary"], 1230, 884, 38, right=1440)
    when = h["received"] or h["earned"]
    if when:
        write(d, ru.date(when, year=False), 422, 920, 32, right=545, centre=True)
        write(d, when[2:4], 583, 920, 32, right=610)
    write(d, h["number"], 268, 988, 36, right=375, centre=True)
    _stamp(im, presidium_seal(210, n["latin"] + "hero"), 345, 792)
    return _jpeg(im)


def size_of(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size


# -- the file's JSON ------------------------------------------------------------------------

def file_json(career_id: str, pilot_id: int, ru_agg, reader_agg, lang: str) -> Optional[Dict[str, Any]]:
    basics = ru_agg.pilot_basics(career_id, pilot_id)
    if basics is None or basics["country"] != 501:
        return None
    detail_ru = ru_agg.career_detail(career_id, pilot_id)
    detail_tr = reader_agg.career_detail(career_id, pilot_id)
    if detail_ru is None or detail_tr is None:
        return None
    levels = _levels(basics)
    names_tr = {a["type"]: a["name"] for a in (reader_agg.pilot_basics(career_id, pilot_id) or {}).get("awards", [])}
    doc = assemble(basics, detail_ru, detail_tr, names_tr, lang, ru_agg.resolver, levels)
    base = f"/api/ussr-doc/{career_id}/{pilot_id}"
    images = []
    if doc["book"]["entries"]:
        images.append({"part": "book", "src": "/static/images/certificates/ussr_order_book_cover.jpg",
                       "size": list(size_of(BOOK_COVER)), "regions": [[0, 0, *size_of(BOOK_COVER), _t(lang, "book_cover")]]})
        images.append({"part": "book", "src": base + "/name", "size": list(size_of(BOOK_NAME)),
                       "regions": name_regions(doc, lang), "photo": [193, 183, 402, 458]})
        for page in range(-(-len(doc["book"]["entries"]) // 8)):
            images.append({"part": "book", "src": f"{base}/awards-{page}", "size": list(size_of(BOOK_AWARDS)),
                           "regions": award_regions(doc, page, lang, names_tr)})
        images.append({"part": "book", "src": "/static/images/certificates/ussr_order_book_back.jpg",
                       "size": list(size_of(BOOK_BACK)), "regions": [[0, 0, *size_of(BOOK_BACK), _t(lang, "book_back")]]})
    if "hero" in doc:
        images.append({"part": "hero", "src": base + "/hero", "size": list(size_of(HERO_TEMPLATE)),
                       "regions": hero_regions(doc, lang)})
    # one nomination sheet per order, at its latest awarding
    latest: Dict[Any, Dict[str, Any]] = {}
    for a in basics["awards"]:
        if a["type"] in BOOK:
            latest[LADDERS.get(a["type"], a["type"])] = a
    sheets = sorted(({"type": a["type"], "earned": a["earned"]} for a in latest.values()), key=lambda s: s["earned"])
    bio_ru = ru_agg.biography(career_id, pilot_id) or {}
    paragraphs = bio_ru.get("paragraphs") or []
    doc.update({"pilot": detail_tr.get("player") or {}, "images": images, "sheets": sheets,
                "strings": {k: {"ru": v, "tip": _t(lang, k)} for k, v in PAGE_RU.items()},
                "biography": paragraphs,
                "biography_tips": biography_tips(reader_agg.biography(career_id, pilot_id) or {}, len(paragraphs), lang),
                "bio_fields": {"name": f"{doc['names']['first']} {doc['names']['last']}",
                               "firstName": doc["names"]["first"], "lastName": doc["names"]["last"],
                               "birthDate": ru.date(basics["birth_date"]) + " г." if basics["birth_date"] else "",
                               "startRank": ru.rank(_starting_rank(detail_ru, int(basics["rank_id"] or 0)))},
                "start_date": ru.date(detail_ru.get("start_date") or "") + " г." if detail_ru.get("start_date") else "",
                "birth_year": basics["birth_date"][:4],
                "born": long_date(lang, basics["birth_date"]) if basics["birth_date"] else "",
                "born_ru": ru.date(basics["birth_date"]) + " г." if basics["birth_date"] else ""})
    return doc


def _levels(basics: Dict[str, Any]) -> Tuple[int, int, int]:
    """Skill, courage and discipline from pilot.leadLevel - the attestation's grades."""
    from .custombio import boosters
    b = boosters(basics.get("lead_level") or 0)
    return b["skill"], b["courage"], b["discipline"]


def _starting_rank(detail: Dict[str, Any], current: int) -> int:
    """The rank he joined the unit with: the one before his first promotion here."""
    promotions = detail.get("promotions") or []
    return int(promotions[0].get("rank_id") or 1) - 1 if promotions else current


def render_doc(career_id: str, pilot_id: int, which: str, ru_agg) -> Optional[bytes]:
    basics = ru_agg.pilot_basics(career_id, pilot_id)
    if basics is None or basics["country"] != 501:
        return None
    detail = ru_agg.career_detail(career_id, pilot_id) or {}
    doc = assemble(basics, detail, detail, {}, "ru", ru_agg.resolver, _levels(basics))
    if which == "name":
        return render_name(doc)
    if which.startswith("awards-") and which[7:].isdigit():
        return render_awards(doc, int(which[7:]))
    if which == "hero" and "hero" in doc:
        return render_hero(doc)
    return None


# The typed pages' Russian, keyed like their tooltips.
PAGE_RU = {
    "cover_title": "ЛИЧНОЕ ДЕЛО", "contents": "Опись документов",
    "label_surname": "Фамилия", "label_first": "Имя", "label_father": "Отчество",
    "label_rank": "Воинское звание", "label_post": "Должность", "label_unit": "Часть",
    "label_born": "Год и место рождения", "label_nationality": "Национальность",
    "label_party": "Партийность", "label_since": "В Советской Армии",
    "record_title": "ПОСЛУЖНОЙ СПИСОК", "record_ranks": "Присвоение воинских званий",
    "record_service": "Прохождение службы", "record_battles": "Участие в боях",
    "record_awards": "Награды", "record_combat": "Боевая работа",
    "col_date": "Дата", "col_rank": "Звание", "col_order": "Приказ", "col_award": "Награда", "col_number": "№",
    "stat_sorties": "Боевых вылетов", "stat_hours": "Налёт, часов", "stat_air": "Сбито самолётов противника",
    "stat_ground": "Уничтожено наземных целей",
    "part_record": "Послужной список", "part_attestation": "Аттестация", "part_orders": "Выписки из приказов",
    "part_book": "Орденская книжка", "part_hero": "Грамота Героя Советского Союза",
    "part_sheets": "Наградные листы", "part_biography": "Биография", "part_shadowbox": "Награды",
    "biography_title": "БИОГРАФИЯ",
}
