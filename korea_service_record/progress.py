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
            return True, []
        ok_r, gap_r = evaluate(node[2], values)
        if ok_r:
            return True, []
        return False, min((gap_l, gap_r), key=_distance)

    if kind == "truthy":
        if _value(node[1], values) != 0:
            return True, []
        return False, [Gap(_text(node[1]), _kind_of(node[1]), 0, 1, ">=")]

    if kind == "cmp":
        op, left, right = node[1], node[2], node[3]
        lv, rv = _value(left, values), _value(right, values)
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
