"""
The Russian the Soviet documents need: names, ranks and posts in the
genitive ("аттестация на капитана Дунаева") and dative ("тов. Дунаеву",
"присвоить капитану Дунаеву"), the plural after a number, dates in words.

Male names only - every pilot in the game is a man. Surnames that do not
decline in Russian (Шевченко, Кабиски) are left as they are.
"""

from typing import Optional

MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_PREP = ("январе", "феврале", "марте", "апреле", "мае", "июне", "июле",
               "августе", "сентябре", "октябре", "ноябре", "декабре")

_HUSHING = set("гкхжшщч")
_UNCHANGED_ENDINGS = ("о", "е", "э", "и", "ы", "у", "ю")


def _noun(word: str, case: str) -> str:
    """A masculine noun or name in the genitive ('gen') or dative ('dat')."""
    if not word:
        return word
    low = word.lower()
    if low.endswith(_UNCHANGED_ENDINGS):
        return word
    if low.endswith("ь") or (low.endswith("й") and not low.endswith(("ый", "ой", "ий"))):
        return word[:-1] + ("я" if case == "gen" else "ю")
    if low.endswith("ий"):                     # Виталий, Георгий
        return word[:-1] + ("я" if case == "gen" else "ю")
    if low.endswith("а"):
        stem = word[:-1]
        return stem + (("и" if stem[-1:].lower() in _HUSHING else "ы") if case == "gen" else "е")
    if low.endswith("я"):
        return word[:-1] + ("и" if case == "gen" else "е")
    return word + ("а" if case == "gen" else "у")


def surname(word: str, case: str) -> str:
    """A man's surname: adjectival (Покрышкин is not, Луковский is) or noun-like."""
    low = (word or "").lower()
    if low.endswith("ний"):                    # Верхний
        return word[:-2] + ("его" if case == "gen" else "ему")
    if low.endswith(("ский", "цкий", "ой", "ый")):
        return word[:-2] + ("ого" if case == "gen" else "ому")
    return _noun(word, case)


def first_name(word: str, case: str) -> str:
    return _noun(word, case)


def patronymic(word: str, case: str) -> str:
    return _noun(word, case)


def full_name(last: str, first: str, father: str, case: Optional[str] = None) -> str:
    """'Дунаев Святослав Игоревич', or in a case."""
    if case is None:
        return " ".join(x for x in (last, first, father) if x)
    return " ".join(x for x in (surname(last, case), first_name(first, case), patronymic(father, case)) if x)


# Ranks as the game names them, lower case, in the two cases the orders use.
RANKS = {
    0: ("лейтенант", "лейтенанта", "лейтенанту"),
    1: ("старший лейтенант", "старшего лейтенанта", "старшему лейтенанту"),
    2: ("капитан", "капитана", "капитану"),
    3: ("майор", "майора", "майору"),
    4: ("подполковник", "подполковника", "подполковнику"),
    5: ("полковник", "полковника", "полковнику"),
    6: ("генерал-майор авиации", "генерал-майора авиации", "генерал-майору авиации"),
    7: ("генерал-лейтенант авиации", "генерал-лейтенанта авиации", "генерал-лейтенанту авиации"),
}


def rank(rank_id: int, case: str = "nom") -> str:
    forms = RANKS.get(max(0, min(7, int(rank_id or 0))))
    return forms[{"nom": 0, "gen": 1, "dat": 2}[case]]


def plural(n: int, one: str, few: str, many: str) -> str:
    """1 вылет, 2 вылета, 5 вылетов - the form after the number n."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def date(ymd: str, year: bool = True) -> str:
    """'1952.04.22' -> '22 апреля 1952' (without 'г.', which forms print)."""
    try:
        y, m, d = (int(x) for x in str(ymd)[:10].replace("-", ".").split("."))
    except ValueError:
        return ""
    return f"{d} {MONTHS_GEN[m - 1]}" + (f" {y}" if year else "")
