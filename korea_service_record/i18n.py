"""
Supported languages, and where the chosen one is remembered.

Two code systems meet here and they are not the same:

* the **game** names its locale files with three-letter codes — ``eng``,
  ``ger``, ``fra``, ``spa``, ``rus``, ``chs`` — and those are what
  ``LocaleStrings`` and ``WorldObjectIndex`` are asked for;
* the **tracker's own** UI strings live in ``locales/<code>.json`` under short
  codes, matching the Great Battles tracker so the two projects can share
  translation work.

Keeping one table for both, rather than a mapping in each module, is what stops
a medal appearing in German next to an English column heading.

The game data half of this already worked before any of it was written:
awards, ranks, mission types and world-object names all come from per-language
files the game ships, and both indexes cache per language. Only the tracker's
own labels needed extracting.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

DEFAULT = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"


class Language(NamedTuple):
    code: str        # the tracker's own code, and the locale file name
    il2: str         # what the game calls it
    name: str        # endonym: shown in the picker in its own language


# Ordered as the picker shows them: English first, then alphabetically by
# endonym. These are exactly the six the game ships and the user asked for.
LANGUAGES: List[Language] = [
    Language("en", "eng", "English"),
    Language("de", "ger", "Deutsch"),
    Language("es", "spa", "Español"),
    Language("fr", "fra", "Français"),
    Language("ru", "rus", "Русский"),
    Language("zh", "chs", "中文"),
]

BY_CODE: Dict[str, Language] = {lang.code: lang for lang in LANGUAGES}
BY_IL2: Dict[str, Language] = {lang.il2: lang for lang in LANGUAGES}


def normalise(code: Optional[str]) -> str:
    """
    Accept anything reasonable and return a supported code.

    Takes the tracker's own codes, the game's three-letter ones, and the
    regional forms a browser sends (``de-DE``, ``zh-Hans``), because the same
    setting is read from a saved file, a query string and Accept-Language.
    """
    if not code:
        return DEFAULT
    text = str(code).strip().lower().replace("_", "-")
    if text in BY_CODE:
        return text
    if text in BY_IL2:
        return BY_IL2[text].code
    head = text.split("-", 1)[0]
    if head in BY_CODE:
        return head
    if head == "zh":                      # zh-Hans, zh-CN, zh-TW
        return "zh"
    return DEFAULT


def game_code(code: Optional[str]) -> str:
    """The three-letter code the game's own locale files use."""
    return BY_CODE.get(normalise(code), BY_CODE[DEFAULT]).il2


def ui_strings(code: Optional[str]) -> Dict[str, object]:
    """
    Load the tracker's own strings for one language.

    Missing or broken files are not fatal: the front end falls back key by key
    to English, so a half-finished translation degrades to English for the
    strings it lacks rather than blanking the page.
    """
    path = LOCALES_DIR / f"{normalise(code)}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("No UI strings for %s (%s)", code, path)
    except (OSError, ValueError) as exc:
        logger.error("Cannot read UI strings %s: %s", path, exc)
    return {}


def available() -> List[Dict[str, str]]:
    """The picker's contents: every language that actually has a file."""
    out = []
    for lang in LANGUAGES:
        if (LOCALES_DIR / f"{lang.code}.json").is_file():
            out.append({"code": lang.code, "il2": lang.il2, "name": lang.name})
    return out


# ---------------------------------------------------------------------------
# The game's own words, wherever it has them
# ---------------------------------------------------------------------------
#
# Most of what this tracker shows is its own invention — the three-column
# service record is not a game screen — but a good deal of the vocabulary is
# not: the game already names courage, discipline, flight hours and awards, in
# all six languages, and its wording is what the player sees in the career
# screens next door. Using ours instead would be both redundant and subtly
# wrong: "Fertigkeit" against the game's "Fähigkeiten" reads as a different
# concept even when it is the same number.
#
# So the shipped locale files are the base, and every entry below is replaced
# at serve time by the game's own string for the requested language. A key with
# no game equivalent, and any language where the lookup misses, simply keeps
# what we wrote.
GAME_STRINGS = {
    # nsdata/assets/locale/career.locale=<lang>.json
    "pilot.skills": "carPilotCharacteristics_Skill",
    "pilot.discipline": "carPilotCharacteristics_Discipline",
    "pilot.courage": "carPilotCharacteristics_Courage",
    "pilot.air_victories": "carDossier_FB_AirVictories",
    "pilot.born": "carCreateCharacterBithday",
    "pilot.squadron": "carSquadrons",
    "pilot.squadron_efficiency": "carDossier_Efficiency_Header",
    "roster.skill": "carPilotCharacteristics_Skill",
    "roster.discipline": "carPilotCharacteristics_Discipline",
    "roster.courage": "carPilotCharacteristics_Courage",
    "roster.air_victories": "carDossier_FB_AirVictories",
    "roster.flight_hours": "carDossier_Stats_FlightHours",
    "roster.awards": "carDossier_Category_Awards",
    "awards.awards": "carDossier_Category_Awards",
    "progression.awards": "carDossier_Category_Awards",
    "landing.awards": "carDossier_Category_Awards",
    "record.award_points": "carAwards_AwardPoints",
    "missions.completed": "carSquadDetails_CompletedMissions",
    "missions.lost": "carSummaryStat_PlanesLost",
    "missions.damaged": "carAutoMissionDamaged_Header",
    "incidences.plane_lost": "carSummaryStat_PlanesLost",
    "incidences.pilot_kia": "carCharacterDetails_KIA",
    "state.kia": "carCharacterDetails_KIA",
    # Assembling "<attribute> booster" from two strings works in English and
    # falls apart elsewhere — German compounds it into one word. The game
    # ships each phrase whole, so use those.
    "pilot.skills_booster": "carPilotCharacteristics_SkillBooster",
    "pilot.discipline_booster": "carPilotCharacteristics_DisciplineBooster",
    "pilot.courage_booster": "carPilotCharacteristics_CourageBooster",
}

GAME_LOCALE_FILE = "nsdata/assets/locale/career.locale={lang}.json"


def _assign(bundle, dotted, value):
    section, _, key = dotted.partition(".")
    if key:
        bundle.setdefault(section, {})[key] = value


def apply_game_strings(bundle, code, read_text, parse):
    """
    Overlay the game's own vocabulary onto our strings, in place.

    ``read_text`` and ``parse`` are passed in rather than imported so this
    module stays free of the asset layer — it is also what lets the caller
    supply whichever language's archive it already has open.
    """
    try:
        raw = read_text(GAME_LOCALE_FILE.format(lang=game_code(code)))
        game = parse(raw or "{}") if raw else {}
    except Exception as exc:                      # a missing archive is not fatal
        logger.warning("No game locale for %s: %s", code, exc)
        return bundle
    replaced = 0
    for dotted, game_key in GAME_STRINGS.items():
        value = game.get(game_key)
        if isinstance(value, str) and value.strip():
            _assign(bundle, dotted, value.strip())
            replaced += 1
    logger.debug("%s: %d strings taken from the game", code, replaced)
    return bundle
