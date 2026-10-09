"""
The documents of a North Korean pilot's personnel file, in Korean.

    order booklets  훈장증, after a National Flag order booklet issued by the
                    Presidium on 22 February 1949 (cover, personal page, award
                    page with the order's founding decree): one booklet per
                    order he holds -
                        국기훈장증         the Hero's Order of the National Flag 1st class
                        전사의영예훈장증    Soldier's Medal of Honour (503003, 503004)
                        자유독립훈장증      Order of Freedom and Independence (503005, 503006)
    표창장          the Presidium's certificate of commendation that came with
                    the Hero title (regulations of 30 June 1950, art. 3 and 4);
                    no example survives in the sources, so it is typeset plainly
    typed pages     간부리력서 (cadre record), 복무경력 (record of service) -
                    drawn by personnel_dprk.js

The game has no Korean: names come from its Chinese name table (Korean names
in Chinese characters) read in Korean (locales/dprk/korean_readings.json, the North's
readings: 李 리, 良 량). Everything printed on the booklets is typeset here,
in the Korean print face, from the original's wording; the decrees of the
two later orders are modelled on the National Flag one and their tooltips
say so. Seals are typeset from the issuing body's name, never copied.
"""

import functools
import hashlib
import io
import json
import math
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .filetips import biography_tips, long_date

HERE = Path(__file__).resolve().parent
CERTS = HERE / "static" / "images" / "certificates"
COVER = CERTS / "dprk_order_book_cover.jpg"
COVER_BLANK = CERTS / "dprk_order_book_cover_blank.jpg"
BOOK_NAME = CERTS / "dprk_order_book_name.jpg"
BOOK_AWARDS = CERTS / "dprk_order_book_awards.jpg"
PRINT_FONT = CERTS / "KoreaRecordPrint.ttf"
HAND_FONT = CERTS / "KoreaRecordHand.ttf"
READINGS = HERE / "locales" / "dprk" / "korean_readings.json"
TIPS = HERE / "locales" / "dprk"

PRINT = (38, 34, 30)
INK = (34, 40, 86)           # blue-black office ink
SEAL_INK = (196, 44, 38)

HERO = 503007
MEDALS = (503002, 503008, 503001)

# The booklets: title, the order's name in the decree, its classes, the date
# of its founding decree, whether that decree is the original's own text.
ORDERS = {
    "flag": {"title": "국기훈장증", "name": "국기", "classes": 3, "founded": "一九四八년十월十二일",
             "founded_raw": "1948.10.12", "authentic": True},
    "soldier": {"title": "전사의영예훈장증", "name": "전사의 영예", "classes": 2, "founded": "一九五〇년七월一일",
                "founded_raw": "1950.07.01", "authentic": False},
    "freedom": {"title": "자유독립훈장증", "name": "자유독립", "classes": 2, "founded": "一九五一년七월十七일",
                "founded_raw": "1951.07.17", "authentic": False},
}
# game award -> (booklet, class)
BOOKLET = {HERO: ("flag", 1), 503003: ("soldier", 2), 503004: ("soldier", 1),
           503005: ("freedom", 2), 503006: ("freedom", 1)}
CLASS_HANJA = {1: "제一급", 2: "제二급", 3: "제三급"}
# The orders' numbers, low as the North's were: (first, last) issued by 1953.
RANGES = {("flag", 1): (40, 420), ("soldier", 1): (900, 6400), ("soldier", 2): (3000, 41000),
          ("freedom", 1): (150, 900), ("freedom", 2): (400, 3200)}

# The founding decrees. The National Flag one is the 1949 booklet's own text.
DECREE_BODY = {
    "flag": "조선의 자유와 독립 또는 조선민주주의인민공화국의 건설에 공훈이있는 이들에게 훈장을 수여하기 위하여 "
            "조선최고인민회의상임위원회는 다음과같이 결정한다.",
    "soldier": "조국해방전쟁에서 조국과 인민을 위하여 용감성과 대담성을 발휘한 조선인민군 전사들에게 훈장을 수여하기 위하여 "
               "조선최고인민회의상임위원회는 다음과같이 결정한다.",
    "freedom": "조국해방전쟁에서 부대를 능숙하게 지휘하여 원쑤를 소멸하는데 공훈을 세운 지휘관들에게 훈장을 수여하기 위하여 "
               "조선최고인민회의상임위원회는 다음과같이 결정한다.",
}

# -- the man ----------------------------------------------------------------------

RANKS = ("중위", "상위", "대위", "소좌", "중좌", "상좌", "대좌", "소장")
POSTS = [("비행사", "post_pilot"), ("선임비행사", "post_senior_pilot"), ("편대장", "post_flight"),
         ("비행중대장", "post_squadron"), ("부련대장", "post_deputy_regiment"), ("련대장", "post_regiment"),
         ("사단장", "post_division"), ("군단장", "post_corps")]
UNITS = {503056: (56, "전투"), 503057: (57, "습격"), 503058: (58, "전투"), 503059: (59, "전투"),
         503060: (60, "전투")}


def rank(rank_id: int) -> str:
    return RANKS[max(0, min(7, int(rank_id or 0)))]


def post(rank_id: int) -> Tuple[str, str]:
    return POSTS[max(0, min(len(POSTS) - 1, int(rank_id or 0)))]


def unit(code: int) -> Dict[str, Any]:
    number, kind = UNITS.get(int(code or 0), (0, ""))
    full = f"조선인민군 공군 제{number}{kind}비행련대" if number else "조선인민군 공군"
    return {"full": full, "short": f"제{number}{kind}비행련대" if number else "조선인민군 공군",
            "number": number, "kind": "attack" if kind == "습격" else "fighter"}


# Biography -> (본적 place, party, enlisted, battles) in Korean. The facts are
# the citation table's (locales/citations bios), put into the North's terms.
PROFILES = {
    "503001": ("서울시", "무소속", "1949", "1937년부터 중국 국민당 공군에서 중일전쟁 참가"),
    "503002": ("평안북도 신의주시", "조선로동당", "1945", "1945년까지 만주에서 항일유격투쟁"),
    "503003": ("강원도 원산시", "조선로동당", "1949", "1940~1945년 만주에서 항일유격투쟁"),
    "503004": ("평안남도 평양시 근교", "조선로동당", "1947", ""),
    "503005": ("평안남도 평양시", "조선로동당", "1945", "1945년까지 항일지하투쟁"),
    "503006": ("함경남도 함흥시", "조선로동당", "1945", "1942~1945년 만주에서 항일유격투쟁"),
    "503007": ("평안남도 평양시 근교", "조선로동당", "1949", ""),
    "503008": ("평안남도 평양시", "조선로동당", "1945", "1942~1945년 만주에서 항일유격투쟁"),
    "503009": ("평안남도 평양시", "조선로동당", "1949", ""),
    "503010": ("강원도 원산시", "조선로동당", "1948", ""),
    "503011": ("함경북도 청진시", "조선로동당", "1945", "만주에서 항일유격투쟁"),
    "503012": ("강원도 원산시 근교", "조선로동당", "1949", ""),
    "503013": ("평안남도 평양시 근교", "조선로동당", "1945", "만주에서 항일유격투쟁"),
    "503014": ("강원도 원산시", "조선로동당", "1945", "1945년까지 만주에서 항일유격투쟁 (동북항일련군)"),
}


@functools.lru_cache(maxsize=1)
def _readings() -> Dict[str, str]:
    try:
        return json.loads(READINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def korean_name(first: str, last: str, resolver) -> str:
    """'Il-seong Her' -> 허일성, through the game's Chinese name table."""
    from .native_names import native
    hanja = native(last, resolver, "chs") + native(first, resolver, "chs")
    table = _readings()
    if not hanja or any(ch not in table for ch in hanja):
        return ""
    return "".join(table[ch] for ch in hanja)


def year_hanja(y: int) -> str:
    return "".join("〇一二三四五六七八九"[int(c)] for c in str(y))


def num_hanja(n: int) -> str:
    d = "〇一二三四五六七八九"
    n = int(n)
    if n < 10:
        return d[n]
    t, o = divmod(n, 10)
    return ("" if t == 1 else d[t]) + "十" + (d[o] if o else "")


def date_hangul(ymd: str) -> str:
    try:
        y, m, d = (int(x) for x in ymd[:10].split("."))
    except ValueError:
        return ""
    return f"{y}년 {m}월 {d}일"


def date_hanja(ymd: str) -> str:
    try:
        y, m, d = (int(x) for x in ymd[:10].split("."))
    except ValueError:
        return ""
    return f"{year_hanja(y)}년{num_hanja(m)}월{num_hanja(d)}일"


def _hash(*parts) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def order_number(booklet: str, cls: int, ymd: str, *seed) -> str:
    lo, hi = RANGES.get((booklet, cls), (100, 1000))
    try:
        y, m, d = (int(x) for x in ymd[:10].split("."))
        frac = min(1.0, max(0.0, ((y - 1950) * 12 + m - 6) / 37.0))
    except ValueError:
        frac = 0.5
    return str(int(lo + (hi - lo) * frac) + _hash(booklet, cls, ymd, *seed) % max(5, (hi - lo) // 40))


# -- tooltips -----------------------------------------------------------------------

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


# -- assembling ----------------------------------------------------------------------

def assemble(basics: Dict[str, Any], detail: Dict[str, Any], detail_tr: Dict[str, Any],
             names_tr: Dict[int, str], lang: str, resolver) -> Dict[str, Any]:
    from . import citations
    from .i18n import game_code
    name = korean_name(basics["first_name"], basics["last_name"], resolver) or \
        f"{basics['last_name']} {basics['first_name']}"
    latin = f"{basics['first_name']} {basics['last_name']}".strip()
    seed = latin + str(basics["unit_code"])
    u = unit(basics["unit_code"])
    rank_id = int(basics["rank_id"] or 0)
    post_ko, post_key = post(rank_id)
    prof = PROFILES.get(str(basics["bio_id"]), ("", "", "", ""))
    bio_tr = (citations.strings(game_code(lang)).get("bios_tr") or citations.strings("eng").get("bios_tr") or {}).get(
        str(basics["bio_id"]), {})
    unit_tip = _t(lang, "unit_" + u["kind"], number=u["number"]) if u["number"] else _t(lang, "unit_af")

    # one booklet per order, each class he holds on its own line
    books: Dict[str, Dict[str, Any]] = {}
    for a in basics["awards"]:
        if a["type"] not in BOOKLET:
            continue
        key, cls = BOOKLET[a["type"]]
        book = books.setdefault(key, {"key": key, "entries": [], "issued": a["received"] or a["earned"],
                                      "no": str(1000 + _hash(seed, key) % 8999)})
        if any(e["cls"] == cls for e in book["entries"]):
            continue                                # a second Gold Star; the order is not given again
        book["entries"].append({"cls": cls, "type": a["type"], "earned": a["earned"],
                                "number": order_number(key, cls, a["earned"], seed)})
    heroes = [a for a in basics["awards"] if a["type"] == HERO]

    record = [{"date": a["earned"], "date_ko": date_hangul(a["earned"]),
               "name": AWARD_KO.get(a["type"], a["name"]), "name_tip": names_tr.get(a["type"], a["name"])}
              for a in basics["awards"]]
    promotions = [{"date_ko": date_hangul(str(p.get("date") or "")[:10]), "date": str(p.get("date") or "")[:10],
                   "rank": rank(int(p.get("rank_id") or 0)), "rank_tip": p.get("rank", "")}
                  for p in detail_tr.get("promotions") or []]
    player = detail.get("player") or {}
    return {
        "name": name, "latin": latin, "unit": u, "unit_tip": unit_tip,
        "rank": rank(rank_id), "rank_tip": (detail_tr.get("player") or {}).get("rank", ""),
        "post": post_ko, "post_tip": _t(lang, post_key),
        "born_place": prof[0], "party": prof[1], "enlisted": prof[2], "battles": prof[3] or "없음",
        "bio_tip": {"born": bio_tr.get("born", ""), "party": bio_tr.get("party", ""),
                    "since": bio_tr.get("since", ""), "battles": bio_tr.get("battles", "")},
        "birth": basics["birth_date"], "birth_ko": date_hangul(basics["birth_date"]) if basics["birth_date"] else "",
        "books": [books[k] for k in ("flag", "soldier", "freedom") if k in books],
        "heroes": [{"earned": h["earned"], "received": h["received"] or h["earned"], "n": i + 1,
                    "no": str(30 + _hash(seed, "hero", i) % 260)} for i, h in enumerate(heroes)],
        "record": record, "promotions": promotions,
        "stats": {"sorties": player.get("sorties"), "hours": player.get("flight_hours"),
                  "air": player.get("airborne"), "ground": player.get("ground_targets")},
        "start": detail.get("start_date") or "",
    }


# The game's North Korean awards in Korean.
AWARD_KO = {503001: "비행사휘장", 503002: "군공메달", 503003: "전사의 영예훈장 제二급",
            503004: "전사의 영예훈장 제一급", 503005: "자유독립훈장 제二급", 503006: "자유독립훈장 제一급",
            503007: "조선민주주의인민공화국 영웅 (국기훈장 제一급, 금별메달)",
            503008: "조국해방전쟁승리기념메달"}


# -- drawing -------------------------------------------------------------------------

def _font(size: int, hand: bool = False) -> ImageFont.FreeTypeFont:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    paths = [HAND_FONT, windir / "malgun.ttf"] if hand else [PRINT_FONT, windir / "batang.ttc", windir / "malgun.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return ImageFont.load_default()


HANJA = set("〇一二三四五六七八九十年月日級")


def _hanja_font(size: int, hand: bool = False) -> ImageFont.FreeTypeFont:
    """The Korean faces have no Chinese characters; the numerals of the
    period (제一급, 一九四八년) come from a Ming face, or the hand one."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    paths = ([CERTS / "LXGWWenKaiTC-PRC.ttf"] if hand else [windir / "simsun.ttc", CERTS / "LXGWWenKaiTC-PRC.ttf"])
    for p in paths:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return _font(size, hand)


def _runs(s: str):
    """The string in runs of Korean and of Chinese characters."""
    out = []
    for ch in s:
        kind = ch in HANJA
        if out and out[-1][0] == kind:
            out[-1][1] += ch
        else:
            out.append([kind, ch])
    return out


def _width(draw, s: str, size: int, hand: bool, spacing: float = 0.0) -> float:
    w = 0.0
    for kind, run in _runs(s):
        f = _hanja_font(size, hand) if kind else _font(size, hand)
        w += draw.textlength(run, font=f)
    return w + spacing * size * max(0, len(s) - 1)


def _draw(draw, s: str, x: float, y: float, size: int, hand: bool, ink, spacing: float, stroke: int) -> None:
    """Left-aligned on its baseline, run by run (and letter by letter when spaced)."""
    for kind, run in _runs(s):
        f = _hanja_font(size, hand) if kind else _font(size, hand)
        for piece in (run if spacing else [run]):
            draw.text((x, y), piece, font=f, fill=ink, anchor="ls", stroke_width=stroke, stroke_fill=ink)
            x += draw.textlength(piece, font=f) + (spacing * size if spacing else 0)


def text(draw, s: str, x: float, y: float, size: int, hand: bool = False, ink=None,
         right: Optional[float] = None, anchor: str = "ls", spacing: float = 0.0, stroke: int = 0) -> None:
    """One line on its baseline; shrinks to fit before ``right``; ``spacing`` spreads the letters (em)."""
    if not s:
        return
    ink = ink or (INK if hand else PRINT)
    if right is not None:
        while size > 10 and _width(draw, s, size, hand, spacing) > right - x:
            size -= 1
    w = _width(draw, s, size, hand, spacing)
    left = x if anchor[0] == "l" else (x - w / 2 if anchor[0] == "m" else x - w)
    _draw(draw, s, left, y, size, hand, ink, spacing, stroke)


def paragraph(draw, s: str, x: float, y: float, width: float, size: int, leading: float = 1.75,
              indent: float = 1.0) -> float:
    """Korean set the way the booklet sets it: wrapped at any syllable, a first-line indent."""
    line, first, yy = "", True, y
    for ch in s:
        room = width - (indent * size if first else 0)
        if _width(draw, line + ch, size, False) > room:
            _draw(draw, line, x + (indent * size if first else 0), yy, size, False, PRINT, 0, 0)
            line, first, yy = ch.lstrip(), False, yy + size * leading
        else:
            line += ch
    if line:
        _draw(draw, line, x + (indent * size if first else 0), yy, size, False, PRINT, 0, 0)
    return yy + size * leading


def _emblem_mask(size: int) -> Optional[Image.Image]:
    """The state emblem, from the gold of the booklet cover."""
    try:
        im = Image.open(COVER).convert("RGB").crop((345, 180, 760, 655))
    except OSError:
        return None
    r, g, b = im.split()
    mask = Image.eval(Image.merge("RGB", (r, g, b)).convert("L"), lambda v: 255 if v > 150 else 0)
    return mask.resize((size, int(size * mask.height / mask.width)), Image.LANCZOS)


def presidium_seal(size: int, seed: str) -> Image.Image:
    """Round seal: the Presidium's name round the rim, the emblem inside."""
    s = size * 2
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    w = max(4, s // 60)
    d.ellipse((w, w, s - w, s - w), outline=255, width=w)
    inner = int(s * 0.31)
    d.ellipse((s / 2 - inner, s / 2 - inner, s / 2 + inner, s / 2 + inner), outline=255, width=max(2, w // 2))
    rim = "조선민주주의인민공화국 최고인민회의 상임위원회 ★ "
    f = _font(int(s * 0.085))
    r = s * 0.395
    for i, ch in enumerate(rim):
        a = -math.pi / 2 + 2 * math.pi * i / len(rim)
        tile = Image.new("L", (int(s * 0.12), int(s * 0.12)), 0)
        ImageDraw.Draw(tile).text((tile.width / 2, tile.height / 2), ch, font=f, fill=255, anchor="mm")
        tile = tile.rotate(-math.degrees(a) - 90, resample=Image.BICUBIC)
        mask.paste(255, (int(s / 2 + r * math.cos(a) - tile.width / 2), int(s / 2 + r * math.sin(a) - tile.height / 2)), tile)
    emblem = _emblem_mask(int(inner * 1.45))
    if emblem is not None:
        mask.paste(255, (int(s / 2 - emblem.width / 2), int(s / 2 - emblem.height / 2)), emblem)
    rnd = random.Random(_hash(seed))
    px = mask.load()
    for _ in range(s * 30):
        px[rnd.randrange(s), rnd.randrange(s)] = 0
    mask = mask.filter(ImageFilter.GaussianBlur(1.0)).resize((size, size), Image.LANCZOS)
    return mask.rotate(rnd.uniform(-10, 10), resample=Image.BICUBIC)


def _stamp(im: Image.Image, mask: Image.Image, cx: float, cy: float, alpha: float = 0.78) -> None:
    colour = Image.new("RGB", mask.size, SEAL_INK)
    im.paste(colour, (int(cx - mask.width / 2), int(cy - mask.height / 2)), mask.point(lambda v: int(v * alpha)))


def _jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def cover_with_title(title: str) -> Image.Image:
    """The blank cover with a title in gold, in the original title's band (y 956-1078)."""
    im = Image.open(COVER_BLANK).convert("RGB")
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    f = ImageFont.truetype(str(windir / "malgunbd.ttf"), 132)
    mask = Image.new("L", (2400, 200), 0)
    d = ImageDraw.Draw(mask)
    x = 10
    for ch in title:                       # spaced like the original
        d.text((x, 100), ch, font=f, fill=255, anchor="lm", stroke_width=2, stroke_fill=255)
        x += d.textlength(ch, font=f) + 34
    mask = mask.crop(mask.getbbox())
    width = min(800, 133 * len(title) + 26 * (len(title) - 1))     # the original's pitch, condensed to fit
    mask = mask.resize((min(width, mask.width), 122), Image.LANCZOS)
    gold = Image.new("RGB", mask.size, (236, 194, 64))
    grad = Image.linear_gradient("L").resize(mask.size)
    gold = Image.composite(Image.new("RGB", mask.size, (252, 216, 92)), gold, grad.point(lambda v: 255 - v))
    left = int((im.width - mask.width) / 2) + 6
    shadow = mask.filter(ImageFilter.GaussianBlur(2)).point(lambda v: int(v * 0.45))
    im.paste((40, 10, 8), (left + 2, 958), shadow)
    im.paste(gold, (left, 956), mask)
    return im


def render_cover(key: str) -> bytes:
    if key == "flag":
        return COVER.read_bytes()
    path = CERTS / f"dprk_order_book_cover_{key}.jpg"
    if path.is_file():
        return path.read_bytes()
    return _jpeg(cover_with_title(ORDERS[key]["title"]))


def render_name(doc: Dict[str, Any]) -> bytes:
    im = Image.open(BOOK_NAME).convert("RGB")
    d = ImageDraw.Draw(im)
    text(d, "사진부치는곳", 400, 340, 30, anchor="ms")
    text(d, "훈장소유자의", 400, 760, 30, anchor="ms", spacing=0.6)
    text(d, "수표", 128, 878, 30)
    text(d, "성명", 820, 120, 32, spacing=0.4)
    text(d, "년", 1010, 214, 30)
    text(d, "월", 1145, 214, 30)
    text(d, "일생", 1275, 214, 30)
    text(d, "본적", 820, 319, 32, spacing=0.4)
    text(d, "주소", 820, 453, 32, spacing=0.4)
    text(d, "직업", 820, 774, 32, spacing=0.4)
    # handwritten
    text(d, doc["name"], 960, 114, 46, hand=True, right=1420)
    text(d, doc["name"], 260, 872, 42, hand=True, right=680)
    try:
        y, m, dd = doc["birth"][:10].split(".")
        text(d, y, 925, 210, 40, hand=True)
        text(d, str(int(m)), 1085, 210, 40, hand=True)
        text(d, str(int(dd)), 1210, 210, 40, hand=True)
    except ValueError:
        pass
    text(d, doc["born_place"], 920, 315, 40, hand=True, right=1420)
    text(d, doc["unit"]["full"], 905, 449, 38, hand=True, right=1425)
    text(d, "군인 (조선인민군 공군)", 905, 770, 38, hand=True, right=1425)
    text(d, f"{doc['post']} · {doc['rank']}", 870, 828, 38, hand=True, right=1425)
    return _jpeg(im)


def render_awards(doc: Dict[str, Any], key: str) -> bytes:
    im = Image.open(BOOK_AWARDS).convert("RGB")
    d = ImageDraw.Draw(im)
    book = next(b for b in doc["books"] if b["key"] == key)
    order = ORDERS[key]
    # left: the order received, the certification, the secretary
    text(d, "다음의 훈장을 수여받음", 138, 150, 27, spacing=0.3)
    text(d, "훈장번호", 642, 150, 27, spacing=0.3, anchor="rs")
    for i, e in enumerate(sorted(book["entries"], key=lambda e: -e["cls"])[:3]):
        y = (226, 293, 359)[i] - 8
        text(d, CLASS_HANJA[e["cls"]], 170, y, 44, hand=True)
        text(d, e["number"], 470, y, 42, hand=True, right=640)
    yy = paragraph(d, f"『{order['name']}』훈장에 관한 규정에 의하여 위 사람이 이 훈장을 수여받았으며 그에 따르는 "
                      "모든 특권과 권리를 향유함을 증명함.", 100, 450, 580, 27)
    text(d, "조선민주주의인민공화국", 380, yy + 40, 27, anchor="ms", spacing=0.15)
    text(d, "최고인민회의상임위원회", 380, yy + 82, 27, anchor="ms", spacing=0.15)
    text(d, "서기장    강  량  욱", 380, yy + 124, 27, anchor="ms")
    _stamp(im, presidium_seal(250, doc["latin"] + key), 205, yy + 95)
    text(d, date_hangul(book["issued"]), 370, 848, 40, hand=True, anchor="ms")
    text(d, book["no"], 410, 952, 40, hand=True, anchor="ms")
    # right: the founding decree
    x, y = 905, 110
    for line in ("조선민주주의인민공화국", "최고인민회의상임위원회  정령"):
        text(d, line, x, y, 30, spacing=0.2)
        y += 46
    classes = " ".join(CLASS_HANJA[c].replace("급", "") for c in range(1, order["classes"] + 1)) + "급"
    text(d, f"『{order['name']}』훈장 {classes}의", x - 5, y, 30, spacing=0.12, right=1420)
    y += 46
    text(d, "제정에관하여", x, y, 30, spacing=0.2)
    y += 68
    y = paragraph(d, DECREE_BODY[key], 815, y, 590, 27, leading=1.62)
    for numeral, rest in (("一、", f"『{order['name']}』훈장 {classes}을 제정한다."),
                          ("二、", f"『{order['name']}』훈장 {classes}에 관한 규정을 승인한다."),
                          ("三、", f"『{order['name']}』훈장 {classes}의 도해를 승인한다.")):
        y = paragraph(d, numeral + rest, 815, y + 4, 590, 27, leading=1.62, indent=0)
    y += 18
    for head, office, person in (("조선민주주의인민공화국", "최고인민회의상임위원회", "위원장    김  두  봉"),
                                 ("조선민주주의인민공화국", "최고인민회의상임위원회", "서기장    강  량  욱")):
        text(d, head, 1105, y, 27, anchor="ms", spacing=0.15)
        text(d, office, 1105, y + 40, 27, anchor="ms", spacing=0.15)
        text(d, person, 1150, y + 86, 28, anchor="ms")
        y += 128
    text(d, order["founded"], 960, y + 2, 28)
    text(d, "평   양   시", 1300, y + 44, 28, anchor="rs")
    return _jpeg(im)


def render_hero_certificate(doc: Dict[str, Any], n: int) -> bytes:
    """표창장 of the Presidium, set plainly on paper with a ruled border."""
    hero = next(h for h in doc["heroes"] if h["n"] == n)
    W, H = 1000, 1400
    # the booklet's own paper: its blank right page, inside the cover's red edge
    try:
        im = Image.open(BOOK_AWARDS).convert("RGB").crop((790, 40, 1420, 1010)).resize((W, H), Image.LANCZOS)
    except OSError:
        im = Image.new("RGB", (W, H), (240, 230, 205))
    d = ImageDraw.Draw(im)
    for inset, width in ((40, 6), (56, 2)):
        d.rectangle((inset, inset, W - inset, H - inset), outline=(150, 112, 40), width=width)
    emblem = _emblem_mask(190)
    if emblem is not None:
        im.paste((176, 132, 44), (int(W / 2 - emblem.width / 2), 110), emblem)
    text(d, "표 창 장", W / 2, 440, 92, anchor="ms", stroke=1)
    text(d, f"{doc['name']}  동무", W / 2, 560, 50, hand=True, anchor="ms")
    second = "거듭 영웅적 위훈을 세운 공로로 두번째 금별메달을" if n > 1 else \
        "조선민주주의인민공화국 영웅 칭호를 수여하고 국기훈장 제一급과 금별메달을"
    body = (f"조선민주주의인민공화국 최고인민회의 상임위원회는 {date_hanja(hero['earned'])} 정령으로 "
            f"조국과 인민을 위하여 영웅적 위훈을 세운 {doc['name']} 동무에게 {second} 수여하였음을 증명함.")
    paragraph(d, body, 130, 680, 740, 34, leading=1.85)
    y = 1040
    text(d, "조선민주주의인민공화국", W / 2, y, 30, anchor="ms", spacing=0.15)
    text(d, "최고인민회의 상임위원회", W / 2, y + 44, 30, anchor="ms", spacing=0.15)
    text(d, "위원장    김  두  봉", W / 2, y + 100, 32, anchor="ms")
    text(d, "서기장    강  량  욱", W / 2, y + 148, 32, anchor="ms")
    _stamp(im, presidium_seal(250, doc["latin"] + "hero" + str(n)), W / 2 - 170, y + 90)
    text(d, f"{date_hanja(hero['received'])}  평양시", W / 2, y + 220, 28, anchor="ms")
    text(d, f"No {hero['no']}", 120, y + 220, 28, hand=True)
    return _jpeg(im)


def size_of(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size


# -- hover regions ----------------------------------------------------------------------

def name_regions(doc, lang) -> List[List[Any]]:
    return [[279, 178, 241, 304, _t(lang, "book_photo")],
            [100, 720, 600, 180, tip(lang, "book_signature", doc["latin"])],
            [800, 70, 640, 70, tip(lang, "book_name", doc["latin"])],
            [800, 170, 640, 70, tip(lang, "book_born", long_date(lang, doc["birth"]))],
            [800, 270, 640, 70, tip(lang, "book_home", doc["bio_tip"]["born"])],
            [800, 400, 640, 260, tip(lang, "book_address", doc["unit_tip"])],
            [800, 720, 640, 240, tip(lang, "book_occupation", f"{doc['post_tip']} · {doc['rank_tip']}")]]


def award_regions(doc, key, lang, names_tr) -> List[List[Any]]:
    book = next(b for b in doc["books"] if b["key"] == key)
    out = [[110, 110, 560, 50, _t(lang, "book_received")]]
    for i, e in enumerate(sorted(book["entries"], key=lambda e: -e["cls"])[:3]):
        y = (226, 293, 359)[i]
        out.append([110, y - 55, 560, 60, tip(lang, "book_entry", f"{names_tr.get(e['type'], '')} · "
                                                                   f"№ {e['number']} · {long_date(lang, e['earned'])}")])
    out += [[90, 410, 610, 330, _t(lang, "book_certify", order=_t(lang, "order_" + key))],
            [140, 800, 460, 70, tip(lang, "book_issued", long_date(lang, book["issued"]))],
            [260, 920, 260, 60, _t(lang, "book_no")],
            [790, 70, 640, 950, _t(lang, "decree_" + key + ("" if ORDERS[key]["authentic"] else "_modelled"),
                                   date=long_date(lang, ORDERS[key]["founded_raw"]))]]
    return out


def hero_regions(doc, n, lang) -> List[List[Any]]:
    hero = next(h for h in doc["heroes"] if h["n"] == n)
    return [[300, 340, 400, 130, _t(lang, "hero_title")],
            [200, 500, 600, 80, tip(lang, "hero_to", doc["latin"])],
            [110, 630, 780, 330, _t(lang, "hero_body_second" if n > 1 else "hero_body",
                                    date=long_date(lang, hero["earned"]))],
            [200, 1000, 600, 170, _t(lang, "hero_signers")],
            [200, 1220, 600, 50, tip(lang, "hero_issued", long_date(lang, hero["received"]))]]


# -- the file's JSON ------------------------------------------------------------------------

PAGE_KO = {
    "cover_title": "간부리력서", "contents": "문건목록",
    "label_name": "성명", "label_sex": "성별", "label_born": "생년월일", "label_home": "출생지",
    "label_nation": "민족별", "label_party": "당별", "label_enlisted": "입대년도",
    "label_rank": "군사칭호", "label_post": "직위", "label_unit": "소속",
    "record_title": "복무경력", "record_ranks": "군사칭호 수여", "record_battles": "참전경력",
    "record_awards": "수훈", "record_combat": "전투실적",
    "col_date": "날자", "col_rank": "군사칭호", "col_award": "훈장 및 메달",
    "stat_sorties": "전투출격", "stat_hours": "비행시간", "stat_air": "격추한 적기", "stat_ground": "소멸한 지상목표",
    "part_record": "복무경력", "part_books": "훈장증", "part_hero": "표창장", "part_medals": "훈장 및 메달",
    "part_sheets": "수훈 제의서", "part_biography": "자서전", "part_shadowbox": "훈장함",
    "biography_title": "자서전", "medals_title": "훈장 및 메달", "translation": "번역",
}


def file_json(career_id: str, pilot_id: int, en_agg, reader_agg, lang: str) -> Optional[Dict[str, Any]]:
    basics = en_agg.pilot_basics(career_id, pilot_id)
    if basics is None or basics["country"] != 503:
        return None
    detail = en_agg.career_detail(career_id, pilot_id)
    detail_tr = reader_agg.career_detail(career_id, pilot_id)
    if detail is None or detail_tr is None:
        return None
    names_tr = {a["type"]: a["name"] for a in (reader_agg.pilot_basics(career_id, pilot_id) or {}).get("awards", [])}
    doc = assemble(basics, detail, detail_tr, names_tr, lang, en_agg.resolver)
    base = f"/api/dprk-doc/{career_id}/{pilot_id}"
    images = []
    for book in doc["books"]:
        k = book["key"]
        images.append({"part": "books", "src": f"{base}/cover-{k}", "size": list(size_of(COVER)),
                       "regions": [[0, 0, *size_of(COVER), _t(lang, "book_cover_" + k)]]})
        images.append({"part": "books", "src": f"{base}/name", "size": list(size_of(BOOK_NAME)),
                       "regions": name_regions(doc, lang), "photo": [283, 182, 234, 296]})
        images.append({"part": "books", "src": f"{base}/awards-{k}", "size": list(size_of(BOOK_AWARDS)),
                       "regions": award_regions(doc, k, lang, names_tr)})
    for h in doc["heroes"]:
        images.append({"part": "hero", "src": f"{base}/hero-{h['n']}", "size": [1000, 1400],
                       "regions": hero_regions(doc, h["n"], lang)})
    latest: Dict[Any, Dict[str, Any]] = {}
    for a in basics["awards"]:
        if a["type"] in BOOKLET:
            latest[BOOKLET[a["type"]][0] if a["type"] != HERO else "hero"] = a
    sheets = sorted(({"type": a["type"], "earned": a["earned"]} for a in latest.values()), key=lambda s: s["earned"])
    bio_tr = reader_agg.biography(career_id, pilot_id) or {}
    paragraphs = bio_tr.get("paragraphs") or []
    korean = korean_biography(basics["bio_id"]) if not bio_tr.get("custom") else []
    medals = [{"type": a["type"], "name": AWARD_KO.get(a["type"], a["name"]), "name_tip": names_tr.get(a["type"], "")}
              for a in basics["awards"]]
    doc.update({"pilot": detail_tr.get("player") or {}, "images": images, "sheets": sheets, "medals": medals,
                "strings": {k: {"ko": v, "tip": _t(lang, k)} for k, v in PAGE_KO.items()},
                "biography": korean or paragraphs, "biography_korean": bool(korean),
                "biography_tips": biography_tips(bio_tr, len(korean), lang) if korean else [],
                "bio_fields": {"name": doc["name"] if korean else doc["latin"],
                               "firstName": doc["name"][1:] if korean else basics["first_name"],
                               "lastName": doc["name"][:1] if korean else basics["last_name"],
                               "birthDate": (date_hangul(basics["birth_date"]) if korean else
                                             long_date(lang, basics["birth_date"])) if basics["birth_date"] else "",
                               "startRank": rank(_starting_rank(detail, int(basics["rank_id"] or 0))) if korean
                               else (bio_tr.get("pilot") or {}).get("starting_rank", "")},
                "born_tip": long_date(lang, basics["birth_date"]) if basics["birth_date"] else ""})
    return doc


# The game has no Korean. A Korean version of each of its fourteen North Korean
# biographies - translated from the English for the tracker, in the North's
# usage of the time, same paragraphs and $[...] fields - is read from
# locales/dprk/bios/<id>.txt. A biography rewritten in the Career Helper wins.
BIOS = [TIPS / "bios"]


def _starting_rank(detail: Dict[str, Any], current: int) -> int:
    """The rank he joined the unit with: the one before his first promotion here."""
    promotions = detail.get("promotions") or []
    return int(promotions[0].get("rank_id") or 1) - 1 if promotions else current


def korean_biography(bio_id: str) -> List[str]:
    """The paragraphs of the Korean version, read like the game's own files."""
    from .custombio import html_paragraphs
    for folder in BIOS:
        try:
            raw = (folder / f"{bio_id}.txt").read_text(encoding="utf-8-sig")
        except OSError:
            continue
        return html_paragraphs(raw)
    return []


def render_doc(career_id: str, pilot_id: int, which: str, en_agg) -> Optional[bytes]:
    basics = en_agg.pilot_basics(career_id, pilot_id)
    if basics is None or basics["country"] != 503:
        return None
    detail = en_agg.career_detail(career_id, pilot_id) or {}
    doc = assemble(basics, detail, detail, {}, "en", en_agg.resolver)
    keys = {b["key"] for b in doc["books"]}
    if which.startswith("cover-") and which[6:] in ORDERS:
        return render_cover(which[6:])
    if which == "name":
        return render_name(doc)
    if which.startswith("awards-") and which[7:] in keys:
        return render_awards(doc, which[7:])
    if which.startswith("hero-") and which[5:].isdigit() and any(h["n"] == int(which[5:]) for h in doc["heroes"]):
        return render_hero_certificate(doc, int(which[5:]))
    return None
