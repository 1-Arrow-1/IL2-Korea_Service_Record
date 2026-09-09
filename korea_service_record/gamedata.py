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
from typing import Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

DEFAULT_LANG = "eng"
SUPPORTED_LANGS = ("eng", "ger", "fra", "spa", "rus", "chs")

# The game's locale files are not strict JSON — missiontypes.locale=eng.json has
# a trailing comma before its closing brace. json.loads rejects that, which would
# silently drop a whole file's strings, so trailing commas are stripped first.
_TRAILING_COMMA = re.compile(r',(\s*[}\]])')


def loads_lenient(text: str) -> dict:
    """Parse JSON that may carry trailing commas. Returns {} on real errors."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return json.loads(_TRAILING_COMMA.sub(r'\1', text))
        except json.JSONDecodeError as exc:
            logger.warning("Locale file is not parseable even leniently: %s", exc)
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
    """
    path = Path(start).resolve()
    for candidate in (path, *path.parents):
        if (candidate / "data" / "Career").is_dir():
            return candidate
        if candidate.name.lower() == "data" and (candidate / "Career").is_dir():
            return candidate.parent
    return None


# ---------------------------------------------------------------------------
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

    def __init__(self, path: Path):
        self.path = Path(path)
        self.definitions: Dict[int, AwardDefinition] = {}
        self._load()

    def _field(self, body: str, key: str) -> str:
        match = re.search(rf'{key}\s*=\s*"(.*?)"', body)
        return match.group(1) if match else ""

    def _load(self) -> None:
        try:
            text = self.path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read awards.cfg at %s: %s", self.path, exc)
            return

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

    def vpath(self, stem: str) -> str:
        return f"nsdata/assets/locale/{stem}.locale={self.lang}.json"

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
