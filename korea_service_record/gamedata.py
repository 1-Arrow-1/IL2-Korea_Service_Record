"""
Access to the game's own data files: rank names, award names and award rules.

Where things live
-----------------
``<game>/data/scg/2/awards.cfg``
    Award definitions. Ships **unencrypted** inside ``Missions.gtp``, and a
    loose copy at that path shadows the archive. Read the loose file when it
    exists, because a modded install will have one and it is what the engine
    actually uses.

``<game>/data/NSData/assets/locale/awards.locale=<lang>.json``
``<game>/data/NSData/assets/locale/ranks.locale=<lang>.json``
    Display names. These live inside ``Interface.gtp``, which is **encrypted**,
    so they are only present loose on an install that has extracted them. When
    missing we fall back to the internal ``name="..."`` from awards.cfg, which
    is always English but always available — the tool must never hard-require
    an extraction step just to render a roster.

Rank keys are ``rank<country><index>``: ``rank6010`` = country 601, rank 0.
Confirmed USAF ladder: 0 Second Lieutenant, 1 First Lieutenant, 2 Captain,
3 Major, 4 Lieutenant Colonel, 5 Colonel.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_LANG = "eng"
SUPPORTED_LANGS = ("eng", "ger", "fra", "spa", "rus", "chs")

# The game's JSON is not strict. missiontypes.locale=eng.json has a trailing
# comma before its closing brace, and the worldobject info.json files carry
# // line comments:
#     "requiredAirfield": 1, // 0 - any, 1 - small, 2- medium, 3 - large
# json.loads rejects both, which would silently drop a whole file, so comments
# and trailing commas are removed before parsing.
_TRAILING_COMMA = re.compile(r',(\s*[}\]])')


def _strip_line_comments(text: str) -> str:
    """
    Remove ``//`` comments that are not inside a string.

    Scanning rather than a regex because values are file paths — "graphics/
    planes/yak9p.mgm" — and a naive rule would happily cut one in half.
    """
    out = []
    in_string = escaped = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def loads_lenient(text: str) -> dict:
    """Parse the game's near-JSON. Returns {} if it is genuinely malformed."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_TRAILING_COMMA.sub(r'\1', _strip_line_comments(text)))
    except json.JSONDecodeError as exc:
        logger.warning("File is not parseable even leniently: %s", exc)
        return {}


# Aircraft the game ships, from the per-plane folders under nsdata/.../planes/.
# Kill events name their target with these (case-insensitively), which is how an
# airborne victory is told apart from a truck: the alternative — guessing from
# name prefixes — misses jets and miscounts ground clutter such as "Windsock".
PLANE_TYPES = {
    "b29", "c47b", "f51d", "f80c10", "f84e", "f86a5",
    "il10", "la11", "li2t", "mig15bis", "tu2", "yak9p",
}

# Theatre id. career.tvd is 2 for Korea; the awards folder is scg/<tvd>.
DEFAULT_TVD = 2


def resolve_game_dir(start: Path) -> Optional[Path]:
    """
    Accept the game folder, its ``data`` folder, or anything below, and return
    the install root (the folder containing ``data``).

    Delegates to :mod:`locate`, which owns the definition of what an IL-2
    installation looks like. This used to insist on ``data\\Career`` — a folder
    the game only creates once a career has been flown — and so rejected
    perfectly good installations.
    """
    from .locate import normalise
    return normalise(start)


# ---------------------------------------------------------------------------
# frontline.cfg
# ---------------------------------------------------------------------------


class FrontLines:
    """
    The career generator's front lines, ``scg/2/frontline.cfg`` inside
    Missions.gtp: one ``[frontline]`` block per period, ``period="from","to"``
    inclusive, and the line as ``p=x,z`` points in the flight log's metres.
    Each block is closed into a polygon by way of the map's corners; those
    corner points are dropped for drawing.
    """

    VPATH = "scg/2/frontline.cfg"
    EDGE = 499199

    def __init__(self, resolver: Optional["AssetResolver"]):
        self.periods: List[Tuple[str, str, List[List[int]]]] = []
        text = resolver.read_text(self.VPATH) if resolver is not None else None
        if text:
            self._parse(text)

    def _parse(self, text: str) -> None:
        for block in re.findall(r"\[frontline\](.*?)\[end\]", text, re.S):
            period = re.search(r'period\s*=\s*"([\d.]+)"\s*,\s*"([\d.]+)"', block)
            if not period:
                continue
            points = [[int(x), int(z)] for x, z in re.findall(r"p\s*=\s*(-?\d+)\s*,\s*(-?\d+)", block)]
            on_edge = lambda pt: pt[0] <= 0 or pt[1] <= 0 or pt[0] >= self.EDGE or pt[1] >= self.EDGE
            while points and on_edge(points[0]):
                points.pop(0)
            while points and on_edge(points[-1]):
                points.pop()
            if points:
                self.periods.append((period.group(1), period.group(2), points))

    def for_date(self, date: str) -> List[List[int]]:
        """The line in force on a career date (``1951.04.23``), or []."""
        for start, end, points in self.periods:
            if start <= date[:10] <= end:
                return points
        return []


# awards.cfg
# ---------------------------------------------------------------------------

class AwardDefinition(NamedTuple):
    award_id: int
    order: int              # position in file; the engine evaluates in this order
    name: str               # internal English name
    in_proc: str            # condition at mission debrief
    by_def: str             # condition during roster sweeps / pilot generation
    required: List[int]     # RequiredAward / 2 / 3
    removes: str            # AwardRemove expression
    combo: Optional[str]
    is_promotion: bool

    @property
    def reachable_in_proc(self) -> bool:
        """``(RND<0)`` is the file's idiom for a permanently closed route."""
        return self.in_proc.replace(" ", "") not in ("", "(RND<0)")

    @property
    def reachable_by_def(self) -> bool:
        return self.by_def.replace(" ", "") not in ("", "(RND<0)")


class AwardsConfig:
    """Parsed ``awards.cfg``."""

    _BLOCK_RE = re.compile(r'\[Award=(\d+)\](.*?)\[end\]', re.S)

    # Where the file lives inside Missions.gtp, and on disk once a mod has
    # placed a loose copy over it.
    VPATH = "scg/2/awards.cfg"

    def __init__(self, path: Path, resolver: Optional["AssetResolver"] = None):
        """
        ``resolver`` makes this work on a stock installation.

        A direct path only finds the file when something has already written a
        loose copy — which is true on a machine with the awards mod installed
        and false on every other one. The game keeps awards.cfg inside
        Missions.gtp, so a stock install read nothing and every award
        definition came back empty. The resolver checks loose first, exactly as
        the engine does, so a modded install still sees the mod's awards.
        """
        self.path = Path(path)
        self.resolver = resolver
        self.definitions: Dict[int, AwardDefinition] = {}
        self._load()

    def _field(self, body: str, key: str) -> str:
        match = re.search(rf'{key}\s*=\s*"(.*?)"', body)
        return match.group(1) if match else ""

    def _load(self) -> None:
        text = None
        if self.resolver is not None:
            text = self.resolver.read_text(self.VPATH)
        if text is None:
            try:
                text = self.path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read awards.cfg at %s: %s", self.path, exc)
                return
        self.source = ("loose or archive" if self.resolver is not None
                       else str(self.path))

        for order, match in enumerate(self._BLOCK_RE.finditer(text)):
            award_id = int(match.group(1))
            body = match.group(2)
            required = []
            for key in ("RequiredAward", "RequiredAward2", "RequiredAward3"):
                value = self._field(body, key)
                if value.isdigit():
                    required.append(int(value))
            self.definitions[award_id] = AwardDefinition(
                award_id=award_id,
                order=order,
                name=self._field(body, "name"),
                in_proc=self._field(body, "AwardInProc"),
                by_def=self._field(body, "AwardByDef"),
                required=required,
                removes=self._field(body, "AwardRemove"),
                combo=self._field(body, "AwardCombo") or None,
                is_promotion="IsPromotion=1" in body.replace(" ", ""),
            )
        logger.info("Loaded %d award definitions from %s",
                    len(self.definitions), self.path)

    def get(self, award_id: int) -> Optional[AwardDefinition]:
        return self.definitions.get(award_id)

    def promotions(self) -> List[AwardDefinition]:
        return [d for d in self.definitions.values() if d.is_promotion]

    def for_country(self, country: int) -> List[AwardDefinition]:
        """Awards whose id is in the country's block (601xxx for USAF)."""
        prefix = str(country)
        return [d for d in sorted(self.definitions.values(), key=lambda d: d.order)
                if str(d.award_id).startswith(prefix) and not d.is_promotion]


# ---------------------------------------------------------------------------
# Locale
# ---------------------------------------------------------------------------

class LocaleStrings:
    """
    Award and rank display names.

    Resolved through the asset layer, so a loose (modded) file wins over the
    archive copy exactly as it does in game, and a stock install still gets
    real names by extracting from the encrypted ``Interface.gtp``.
    """

    def __init__(self, game_dir: Path, lang: str = DEFAULT_LANG,
                 resolver: Optional["AssetResolver"] = None):
        self.game_dir = Path(game_dir)
        self.lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
        if resolver is None:
            from .assets import AssetResolver
            resolver = AssetResolver(self.game_dir)
        self.resolver = resolver
        self.awards: Dict[str, str] = self._load("awards")
        self.ranks: Dict[str, str] = self._load("ranks")
        self.mission_types: Dict[str, str] = self._load("missiontypes")
        # Not under assets/locale with the others, and easy to miss: the game
        # names every killStats category here, in all six languages, keyed
        # exactly as the save data keys them.
        self.stat_objects: Dict[str, str] = self._load_at(
            f"nsdata/assets/worldobjects/statobjects.locale={self.lang}.json")
        # 659 designations keyed by the same folder names the kill events use:
        # yak9p -> "Yak-9P". Without it the air-kill panel prints the raw key.
        self.stat_names: Dict[str, str] = self._load_at(
            f"nsdata/assets/worldobjects/statnames.locale={self.lang}.json")

    def vpath(self, stem: str) -> str:
        return f"nsdata/assets/locale/{stem}.locale={self.lang}.json"

    def _load_at(self, vpath: str) -> Dict[str, str]:
        text = self.resolver.read_text(vpath)
        if text is None:
            logger.info("Locale not found: %s", vpath)
            return {}
        return loads_lenient(text)

    def _load(self, stem: str) -> Dict[str, str]:
        vpath = self.vpath(stem)
        text = self.resolver.read_text(vpath)
        if text is None:
            logger.info("Locale not found in loose files, cache or archives: %s", vpath)
            return {}
        return loads_lenient(text)

    def sources(self) -> Dict[str, str]:
        """Where each locale file came from — useful in a debug endpoint."""
        return {stem: self.resolver.source_of(self.vpath(stem))
                for stem in ("awards", "ranks", "missiontypes")}

    # The game's own slips in its English statobjects file, reported from the
    # forum: "Train Vagon" (the other five languages have it right) and the
    # one lower-case "Heavy gun" beside "Light Gun". Corrected here rather
    # than in the game's file, which the mod does not ship.
    STAT_NAME_FIXES = {
        ("eng", "TrainVagon"): "Train Wagon",
        ("eng", "HeavyGun"): "Heavy Gun",
    }

    def stat_name(self, category: str) -> str:
        """
        The game's own name for a killStats category.

        killStats keys the categories bare — ``LightFlak``, ``StaticPlane`` —
        and statobjects keys them with a ``kill`` prefix. A few have no entry
        in any language: the rollups the tracker computes rather than
        categories the game counts (``Building``, ``Aircraft``), and
        ``Materiel`` and ``Railroad``; the caller supplies those from the
        tracker's own locale.
        """
        fixed = self.STAT_NAME_FIXES.get((self.lang, category))
        if fixed:
            return fixed
        name = self.stat_objects.get("kill" + category)
        return name.strip() if isinstance(name, str) and name.strip() else ""

    def plane_name(self, key: str) -> str:
        """The game's designation for an aircraft — "yak9p" -> "Yak-9P"."""
        name = self.stat_names.get((key or "").strip().lower())
        return name.strip() if isinstance(name, str) and name.strip() else ""

    def mission_type_name(self, type_id: int) -> str:
        """
        A readable name for a mission type.

        The locale holds per-objective strings (missionType1128Obj0 = "Find and
        destroy ground targets"); Obj0 is the actual task, the others are always
        take-off and landing.
        """
        return (self.mission_types.get(f"missionType{type_id}Obj0")
                or self.mission_types.get(f"missionType{type_id}")
                or f"Mission type {type_id}")

    @property
    def has_awards(self) -> bool:
        return bool(self.awards)

    def award_name(self, award_id: int, fallback: str = "") -> str:
        return self.awards.get(f"award{award_id}") or fallback or f"Award {award_id}"

    def rank_name(self, country: int, rank_id: int) -> str:
        """
        ``rank<country><index>`` — e.g. rank6011 = USAF First Lieutenant.

        This is the correct rank for a pilot. The game's own "Award and
        Promotion" panel shifts every row up by the number of promotions the
        pilot has had, so it must not be used as a reference.
        """
        key = f"rank{country}{rank_id}"
        return self.ranks.get(key) or f"Rank {rank_id}"


# Rank locale keys give the country codes away: 501 runs Lieutenant/Senior
# Lieutenant, 502 Zhongwei/Shangwei, 503 Chungwi/Sangwi, and 601/602/603 are
# the three US services (Air Force, Navy ranks, Marines) flying the same flag.
COUNTRY_FLAGS = {
    501: "ussr",
    502: "china",
    503: "dprk",
    601: "us",
    602: "us",
    603: "us",
}

COUNTRY_NAMES = {
    501: "Soviet Union",
    502: "China",
    503: "North Korea",
    601: "United States",
    602: "United States",
    603: "United States",
}


# Which language the classification stamp is impressed in. The record belongs
# to the air force the pilot serves in, so it follows the country, not the UI.
COUNTRY_STAMPS = {
    501: "rus",     # СЕКРЕТНО
    502: "chi",     # 機密
    503: "kor",     # 비밀
    601: "eng",
    602: "eng",
    603: "eng",
}

# The round seal struck across the corner of the pilot's photograph, as a
# clerk would have done to authenticate it. One per nation rather than per
# branch: it names the theatre formation the air arm actually fought under in
# Korea, and the US one — Far East Command — covered Air Force, Navy and
# Marines alike. Files are static/images/stamps/seal_<name>.png.
COUNTRY_SEALS = {
    501: "ussr",    # 64 ИАК — the corps that was officially never there
    502: "prc",     # 中国人民志愿军空军 — the "volunteers"
    503: "dprk",    # 조선인민군 공군
    601: "usa",     # FAR EAST COMMAND
    602: "usa",
    603: "usa",
}


# ---------------------------------------------------------------------------
# Mission objectives, in every language the game ships
# ---------------------------------------------------------------------------

class MissionDescriptions:
    """
    The briefing objective for a mission type, translated.

    The career database stores the briefing as finished prose — airfield,
    unit, crew list, weather and objective, rendered when the mission was
    generated and in whatever language the game was running at the time. That
    text cannot be re-rendered, so a German reader was stuck with an English
    briefing for every mission flown before he switched.

    The generator's own sources survive that, though, and this is where they
    live::

        scg/<tvd>/blocks_career/localisation/descriptions/
            <missiontype>_primary-action_v1.<lang>

    62 mission types, seven languages each, UTF-16 with a leading slot index
    on the first line. Nothing found them by grep because of the encoding.

    Only the objective is taken. The rest of the stored briefing is either
    shown elsewhere on the page already — the crew is a table in the same
    modal — or is weather detail that reads as padding beside it.
    """

    DIR = "scg/{tvd}/blocks_career/localisation/descriptions"
    VARIANTS = ("{type}_primary-action_v1", "{type}_primary-action_night_v1")

    def __init__(self, resolver, lang: str = DEFAULT_LANG, tvd: int = DEFAULT_TVD):
        self.resolver = resolver
        self.lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
        self.tvd = tvd
        self._cache: Dict[int, str] = {}

    def _decode(self, raw: bytes) -> str:
        # UTF-16 with a BOM; the fallbacks are for a modded file saved otherwise.
        for encoding in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return ""

    @staticmethod
    def _repair(text: str) -> str:
        r"""
        Undo the stray escaping in the French files.

        Only French carries backslashes — 23 of them across 12 files. Twenty-one
        are an escaped apostrophe, written for a format that never needed one;
        the other two are "d\être" and "d\endommager", where the backslash has
        replaced the apostrophe outright rather than escaping it. Both resolve
        the same way, so the rule is: a backslash before an apostrophe goes, and
        a backslash before a letter becomes one.

        Deliberately not a general unescape — nothing else in these files uses
        a backslash, so there is no \n or \t to protect.
        """
        text = text.replace("\\'", "'")
        return re.sub(r"\\(?=[^\W\d_])", "'", text)

    def objective(self, mission_type: Optional[int]) -> str:
        """The primary-objective text, or "" when the game has none."""
        if mission_type is None:
            return ""
        if mission_type in self._cache:
            return self._cache[mission_type]
        text = ""
        for pattern in self.VARIANTS:
            stem = pattern.format(type=mission_type)
            vpath = f"{self.DIR.format(tvd=self.tvd)}/{stem}.{self.lang}"
            raw = self.resolver.read(vpath)
            if not raw:
                continue
            body = self._decode(raw).strip()
            # The first line carries the slot index the generator writes it
            # into — "3: Your target ..." — which is not part of the briefing.
            body = re.sub(r"^\s*\d+\s*:\s*", "", body)
            body = self._repair(body)
            if body:
                text = body
                break
        self._cache[mission_type] = text
        return text
