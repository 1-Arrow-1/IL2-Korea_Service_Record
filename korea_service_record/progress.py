"""
How close a pilot is to his next decoration, read from ``awards.cfg`` itself.

Nothing in the game shows this. The conditions are there in the campaign data
and the career file has every number they ask about, so the only missing piece
is an evaluator — which is what this module is.

The grammar is small. Whitespace is stripped, ``&`` is and, ``|`` is or,
parentheses group, ``+`` sums, and a comparison is one of ``>= <= < > =``.
A bare identifier is a predicate that is true when non-zero, which is how
``(IsCommander)`` works. The engine lowercases identifiers, truncates them at
31 characters and **auto-creates anything it does not know as zero, without
complaining** — so a typo silently makes its branch unreachable rather than
raising. ``OpSuccess`` is exactly that: four awards test a variable the engine
has never heard of, and this evaluator reproduces the behaviour rather than
correcting it, because the question being answered is "what will the game do",
not "what did the author mean".

What comes back is not a yes or no but a route: the branch of the condition
the pilot is closest to satisfying, and what stands between him and it. An OR
is a choice of routes and the nearest one is the one worth showing; an AND
needs all of its parts, so its weakest part sets the distance.
"""

from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Optional, Tuple

# --- what each variable means -------------------------------------------
#
# Only the cumulative ones can be drawn as progress. A per-sortie count is a
# standing requirement — "three airborne kills in one flight" is not something
# you are 60% of the way through — and the dice are re-rolled on every read,
# so they are never progress and never a promise either.

CUMULATIVE = {
    "complsorties", "sorties", "goodsorties", "airobj", "seaobj", "grobj",
    "bldobj", "trnsobj", "fltime", "careerdays", "servicedays", "pcp",
    "efficiency",
}
PER_SORTIE = {
    "airobjsortie", "grobjsortie", "seaobjsortie", "bldobjsortie",
    "fghtobjsortie", "bmbrobjsortie", "trnsobjsortie", "wiasortie",
}
DICE = {"rnd", "rndsortie"}

# Context decides whether an award applies to this pilot at all, rather than
# how far along he is. A Country that does not match is not "no progress" —
# it means the award belongs to somebody else's air force.
CONTEXT = {
    "country", "cdate", "rankid", "iscommander", "isplayer", "wia",
    "opgood", "opsuccess", "battleend", "noawards",
}


class Gap(NamedTuple):
    """One unmet comparison, and how far off it is."""
    variable: str           # as written in the cfg, e.g. "AirObj+SeaObj"
    kind: str               # cumulative | per_sortie | dice | context
    current: float
    needed: float
    op: str

    @property
    def fraction(self) -> float:
        if self.kind != "cumulative" or self.needed <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current / self.needed))


# --- parsing -------------------------------------------------------------

_TOKEN = re.compile(r">=|<=|<>|[()&|+<>=]|[A-Za-z_][A-Za-z0-9_]*|\d+")


def _tokenise(expr: str) -> List[str]:
    return _TOKEN.findall((expr or "").replace(" ", ""))


class _Parser:
    """
    Recursive descent over the four levels the grammar actually has:
    or, and, comparison, sum.
    """

    def __init__(self, tokens: List[str]):
        self.t = tokens
        self.i = 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.or_()
        if self.i != len(self.t):           # trailing rubbish: treat as closed
            return ("lit", 0)
        return node

    def or_(self):
        node = self.and_()
        while self.peek() == "|":
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self):
        node = self.cmp_()
        while self.peek() == "&":
            self.take()
            node = ("and", node, self.cmp_())
        return node

    def cmp_(self):
        left = self.sum_()
        if self.peek() in (">=", "<=", "<", ">", "=", "<>"):
            op = self.take()
            return ("cmp", op, left, self.sum_())
        if left[0] in ("cmp", "and", "or", "truthy"):
            return left                     # already a condition: (A>=1)&(B)
        return ("truthy", left)             # a bare (IsCommander)

    def sum_(self):
        node = self.atom()
        while self.peek() == "+":
            self.take()
            node = ("add", node, self.atom())
        return node

    def atom(self):
        tok = self.peek()
        if tok is None:
            return ("lit", 0)
        if tok == "(":
            self.take()
            node = self.or_()
            if self.peek() == ")":
                self.take()
            # A bracketed sum is an operand, not a predicate: in
            # ((AirObj+GrObj)>=20) the inner group is the left-hand side of
            # the comparison that follows. cmp_ wraps it as a predicate on
            # the way out, so unwrap it again here - if it really is standing
            # alone as a condition, the next cmp_ up will re-wrap it.
            if node[0] == "truthy" and node[1][0] in ("add", "var", "lit"):
                return node[1]
            return node
        self.take()
        if tok.isdigit():
            return ("lit", int(tok))
        return ("var", tok)


def parse(expr: str):
    return _Parser(_tokenise(expr)).parse()


# --- evaluation ----------------------------------------------------------

def _value(node, values: Dict[str, float]) -> float:
    kind = node[0]
    if kind == "lit":
        return float(node[1])
    if kind == "var":
        # the engine lowercases, truncates at 31, and invents zero for
        # anything it has never heard of
        return float(values.get(node[1].lower()[:31], 0))
    if kind == "add":
        return _value(node[1], values) + _value(node[2], values)
    if kind == "truthy":
        return _value(node[1], values)
    return 0.0


def _text(node) -> str:
    kind = node[0]
    if kind == "lit":
        return str(node[1])
    if kind == "var":
        return node[1]
    if kind == "add":
        return f"{_text(node[1])}+{_text(node[2])}"
    if kind == "truthy":
        return _text(node[1])
    return "?"


def _kind_of(node) -> str:
    """What sort of thing a comparison's left side is."""
    names = set()

    def walk(n):
        if n[0] == "var":
            names.add(n[1].lower())
        elif n[0] == "add":
            walk(n[1])
            walk(n[2])
        elif n[0] == "truthy":
            walk(n[1])
    walk(node)
    if names & DICE:
        return "dice"
    if names & PER_SORTIE:
        return "per_sortie"
    if names & CONTEXT:
        return "context"
    if names & CUMULATIVE:
        return "cumulative"
    return "context"                        # unknown: it will never be true


def evaluate(node, values: Dict[str, float]) -> Tuple[bool, List[Gap]]:
    """
    Whether the condition holds, and if not, the nearest route to it.

    An AND reports every part that is missing, because all of them must be
    met. An OR reports only its most promising branch — the others are
    alternatives the pilot is further from, and listing them would bury the
    one he is actually going to reach.
    """
    kind = node[0]

    if kind == "and":
        ok_l, gap_l = evaluate(node[1], values)
        ok_r, gap_r = evaluate(node[2], values)
        return (ok_l and ok_r), (gap_l + gap_r)

    if kind == "or":
        ok_l, gap_l = evaluate(node[1], values)
        if ok_l:
            return True, [g for g in gap_l if g.kind == "dice"]
        ok_r, gap_r = evaluate(node[2], values)
        if ok_r:
            return True, [g for g in gap_r if g.kind == "dice"]
        return False, min((gap_l, gap_r), key=_distance)

    if kind == "truthy":
        if _value(node[1], values) != 0:
            return True, []
        return False, [Gap(_text(node[1]), _kind_of(node[1]), 0, 1, ">=")]

    if kind == "cmp":
        op, left, right = node[1], node[2], node[3]
        lv, rv = _value(left, values), _value(right, values)
        # The dice are never a barrier and never a promise. RND is re-rolled
        # on every read, so there is no "current value" to be short of - the
        # branch stays live and the threshold is carried out as a chance, so
        # a one-in-three-hundred roll is not reported in the same breath as a
        # condition already met.
        if _kind_of(left) == "dice":
            return True, [Gap(_text(left), "dice", 0.0, rv, op)]
        ok = {">=": lv >= rv, "<=": lv <= rv, "<": lv < rv,
              ">": lv > rv, "=": lv == rv, "<>": lv != rv}[op]
        if ok:
            return True, []
        return False, [Gap(_text(left), _kind_of(left), lv, rv, op)]

    return bool(_value(node, values)), []


def _distance(gaps: List[Gap]) -> float:
    """
    How far a branch is from being satisfied, lower being nearer.

    A branch is only as close as its furthest part, so the weakest gap sets
    the distance. Anything resting on a context test that is false — the
    wrong air force, a date that has not arrived — is unreachable rather than
    distant, and sorts last.
    """
    if not gaps:
        return 0.0
    worst = 1.0
    for gap in gaps:
        if gap.kind == "context":
            return 99.0
        if gap.kind == "dice":
            continue                        # never a barrier, only a chance
        worst = min(worst, gap.fraction)
    return 1.0 - worst


# --- what the career says the variables are ------------------------------

def _days(start: str, now: str) -> int:
    """Whole days between two of the game's ``YYYY.MM.DD`` stamps."""
    from datetime import date
    try:
        a = date(*(int(x) for x in (start or "")[:10].split(".")))
        b = date(*(int(x) for x in (now or "")[:10].split(".")))
    except (ValueError, TypeError):
        return 0
    return max(0, (b - a).days)


def _cdate(now: str) -> int:
    """``CDate`` is the current date as a plain YYYYMMDD number."""
    try:
        return int((now or "")[:10].replace(".", ""))
    except ValueError:
        return 0


def pilot_variables(pilot, career, squadron=None) -> Dict[str, float]:
    """
    Every variable an award condition can ask about this pilot.

    The awkward ones, all established by experiment rather than guessed:
    ``FlTime`` is in **hours** while the database stores seconds; ``AirObj``
    is aircraft *minus* those destroyed on the ground, because a parked plane
    counts as a ground kill and appears in ``GrObj`` instead; and ``CDate`` is
    the campaign date as a bare YYYYMMDD integer.

    ``ComplSorties`` is read as the pilot's *good* sorties and ``Sorties`` as
    his total. On this career the two are equal so the choice is not yet
    settled by evidence - if an award ever fires a sortie early or late, this
    is the first line to suspect. ``TrnsObj`` is left at zero: the variable
    exists in the engine but nothing in the shipped conditions uses it, and
    the kill blob has no transport category to read it from.
    """
    from .career.killstats import KillStats

    kills = KillStats(pilot["killStats"] if "killStats" in pilot.keys() else "")
    start = pilot["careerStartDate"] if "careerStartDate" in pilot.keys() else None
    now = career["currentDate"] if career is not None else ""
    days = _days(start or (career["startDate"] if career is not None else ""), now)
    values = {
        "country": float(pilot["country"] or 0),
        "rankid": float(pilot["rankId"] or 0),
        "pcp": float(pilot["pcp"] or 0),
        "sorties": float(pilot["sorties"] or 0),
        "complsorties": float(pilot["goodSorties"] or 0),
        "goodsorties": float(pilot["goodSorties"] or 0),
        "fltime": float(pilot["flightTime"] or 0) / 3600.0,
        "careerdays": float(days),
        "servicedays": float(days),
        "cdate": float(_cdate(now)),
        "iscommander": 1.0 if pilot["isPlayer"] else 0.0,
        "isplayer": 1.0 if pilot["isPlayer"] else 0.0,
        "airobj": float(kills.airborne),
        "grobj": float(kills.get("Materiel") + kills.static_air),
        "bldobj": float(kills.get("Building")),
        "seaobj": float(kills.category_totals().get("naval", 0)),
        "trnsobj": 0.0,
        "wia": float(pilot["wounded"] or 0) if "wounded" in pilot.keys() else 0.0,
        "efficiency": float(squadron["efficiency"] or 0) if squadron is not None else 0.0,
    }
    return values


def squadron_variables(squadron, career, country: int) -> Dict[str, float]:
    """
    The same vocabulary, but counted for the unit.

    A unit citation asks about the squadron's totals, not the player's, and
    ``Efficiency`` is defined only here - which is why the same condition
    text means different things on a squadron award and a personal one.
    """
    from .career.killstats import KillStats

    kills = KillStats(squadron["killStats"] if squadron is not None else "")
    now = career["currentDate"] if career is not None else ""
    days = _days(career["startDate"] if career is not None else "", now)
    return {
        "country": float(country),
        "complsorties": float(squadron["goodSorties"] or 0) if squadron is not None else 0.0,
        "sorties": float(squadron["sorties"] or 0) if squadron is not None else 0.0,
        "goodsorties": float(squadron["goodSorties"] or 0) if squadron is not None else 0.0,
        "efficiency": float(squadron["efficiency"] or 0) if squadron is not None else 0.0,
        "airobj": float(kills.airborne),
        "grobj": float(kills.get("Materiel") + kills.static_air),
        "bldobj": float(kills.get("Building")),
        "seaobj": float(kills.category_totals().get("naval", 0)),
        "careerdays": float(days),
        "servicedays": float(days),
        "cdate": float(_cdate(now)),
    }


# --- which rung is next --------------------------------------------------

class Rung(NamedTuple):
    """One award the pilot could reasonably reach next."""
    award_id: int
    name: str
    eligible: bool          # the condition holds; only the dice are left
    gaps: List[Gap]
    distance: float         # 0 is there, 1 is nowhere near, 99 is not for him

    @property
    def bars(self) -> List[Gap]:
        return [g for g in self.gaps if g.kind == "cumulative"]

    @property
    def conditions(self) -> List[Gap]:
        return [g for g in self.gaps if g.kind == "per_sortie"]

    @property
    def chance(self) -> Optional[float]:
        """
        The odds per evaluation, where the condition rests on a dice roll.

        RND is an integer the engine re-rolls on every read and the shipped
        conditions compare it against thresholds from 3 to 500, which only
        makes sense on a scale of a thousand: the Navy work confirmed 199
        passes ``RND<200`` and 200 does not. So the threshold is the chance
        in a thousand, and a Soldier's Medal at ``RND<3`` is a different
        proposition from a Commendation Ribbon at ``RND<200``.
        """
        dice = [g for g in self.gaps if g.kind == "dice"]
        if not dice:
            return None
        return min(g.needed for g in dice) / 1000.0


def next_rungs(awards, held: set, values: Dict[str, float],
               country: int, squadron: bool = False) -> List[Rung]:
    """
    The next rung of every ladder this pilot is standing on.

    A ladder is a chain of ``RequiredAward``, so the next rung finds itself:
    an award whose requirement is held and which is not, and nothing further
    up, because rung three needs rung two which he has not got. Ladders he
    has not started contribute their first rung, which is how a man who has
    never been decorated still sees where the Air Medal is.

    Promotions are left out - they are pseudo-awards with no artwork and no
    name, and they belong beside the rank rather than in the medal list.
    Squadron citations are asked for separately, because they are counted on
    the unit's totals and not the man's.

    A requirement must be **held**, which in the engine means received rather
    than merely earned: an award still sitting pending does not unlock the
    rung above it.

    Only ``AwardInProc`` is consulted - see the note in the body for why
    ``AwardByDef`` is not a route a player can count on.
    """
    prefix = str(country)
    out: List[Rung] = []
    for award in sorted(awards.definitions.values(), key=lambda a: a.order):
        if award.is_promotion or bool(award.is_squadron) != squadron:
            continue
        if not str(award.award_id).startswith(prefix):
            continue
        if award.award_id in held:
            continue
        if any(req not in held for req in award.required):
            continue
        if not award.reachable_in_proc and not award.reachable_by_def:
            continue

        # Only AwardInProc. AwardByDef looks like a second route and is not
        # one: across a whole career of daily roster sweeps, no award whose
        # only live path is a dice-gated AwardByDef has ever been granted to
        # anybody. The Senior Pilot Wings sit behind (RankID>=2)&(RND<500) -
        # a coin flip per sweep, some thirty sweeps - and have nought
        # holders; so do the Command Pilot Wings. Every Purple Heart in this
        # career went to a man who was actually wounded, through the debrief.
        # Presenting AwardByDef as live would promise medals that never come.
        expr = award.in_proc
        if not expr or expr.replace(" ", "") == "(RND<0)":
            continue
        ok, gaps = evaluate(parse(expr), values)
        best = (ok, gaps)

        ok, gaps = best
        if any(g.kind == "context" for g in gaps):
            continue                        # not this pilot's award at all
        blocking = [g for g in gaps if g.kind in ("cumulative", "per_sortie")]
        out.append(Rung(award.award_id, award.name, ok and not blocking, gaps,
                        0.0 if ok else _distance(gaps)))

    out.sort(key=lambda r: (not r.eligible, r.distance))
    return out
