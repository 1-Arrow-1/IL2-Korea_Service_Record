"""
Chinese text for the period documents of the Chinese personnel file.

The game writes Chinese in simplified characters; a document of 1951 is in
traditional ones, so everything is converted with OpenCC's s2tw table (phrase-aware, so
发 becomes 發 or 髮 by context). Personal names are converted character by
character instead, because a surname is not a phrase: OpenCC turns the
surname 涂 into 塗 and 于 into 於. Without OpenCC installed the text stays
simplified rather than failing.
"""

from functools import lru_cache
from typing import Optional

# Surnames (and given-name characters) that are already their own
# traditional form; the phrase converter would "correct" them.
KEEP = set("涂范于余沈干谷姜党丑朴志后")

DIGITS = "〇一二三四五六七八九"


@lru_cache(maxsize=1)
def _converter():
    try:
        from opencc import OpenCC
    except ImportError:
        return None
    # s2tw, not s2t: the plain table prefers rare variants (峯, 羣衆) where
    # the forms in common use are 峰 and 群眾.
    return OpenCC("s2tw")


def to_trad(text: Optional[str]) -> str:
    """Simplified to traditional, by phrase."""
    if not text:
        return ""
    cc = _converter()
    return cc.convert(text) if cc else text


def name_to_trad(text: Optional[str]) -> str:
    """A personal name, character by character, keeping the surname set."""
    if not text:
        return ""
    cc = _converter()
    if cc is None:
        return text
    return "".join(ch if ch in KEEP else cc.convert(ch) for ch in text)


def number(n: int) -> str:
    """A count in words: 3 三, 12 十二, 20 二十, 41 四十一 (0-99)."""
    n = int(n)
    if n < 10:
        return DIGITS[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else DIGITS[tens]) + "十" + (DIGITS[ones] if ones else "")


def year(y: int) -> str:
    """A year digit by digit, as written: 1951 一九五一."""
    return "".join(DIGITS[int(c)] for c in str(int(y)))


def date(ymd: str, day: bool = True) -> str:
    """'1951.11.09' -> 一九五一年十一月九日 (or without the day)."""
    try:
        y, m, d = (int(x) for x in str(ymd)[:10].replace("-", ".").split("."))
    except ValueError:
        return ""
    text = f"{year(y)}年{number(m)}月"
    return text + (f"{number(d)}日" if day else "")


def ordinal_count(n: int) -> str:
    """The financial form used in records: 1 壹, 2 貳 ... for 立功壹次."""
    return "零壹貳參肆伍陸柒捌玖拾"[int(n)] if 0 <= int(n) <= 10 else number(n)
