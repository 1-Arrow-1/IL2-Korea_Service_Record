"""World War II service awards inferred from the selectable biography.

These are prior-service decorations.  They are not rows in the Korea career
database and must not be mixed into the Korean War award timeline.  The
tracker adds them only to what the pilot wears on the service coat, full-dress
coat and shadowbox.

Campaign credits are necessarily an inference: the biographies name theatres
and operations, but do not identify the pilot's official unit campaign-credit
orders.  The table deliberately follows only the operations stated in the
biography audit recorded in ``docs/HANDOFF.md``.
"""

import urllib.parse
from typing import Dict, Optional, Tuple


AMERICAN_DEFENSE = 601064
ASIATIC_PACIFIC = (601065, 601066, 601067, 601068)       # plain, 1-3 stars
EAME = tuple(range(601069, 601076))                       # plain, 1-6 stars
WWII_VICTORY = 601076

DEFENSE_LENINGRAD = 501050
DEFENSE_MOSCOW = 501051
DEFENSE_STALINGRAD = 501052
VICTORY_GERMANY = 501053
VICTORY_JAPAN = 501054


# One row per selectable US biography.  A number is the inferred campaign
# credit count and therefore selects that many bronze-star equivalents.  The
# American Defense medal is limited to biographies which explicitly put the
# pilot in US service before 7 December 1941.  Its foreign-service clasp is a
# different full-medal device and is not inferred from the generic star art.
_AMERICAN_DEFENSE = {"601003", "601005", "601008", "601010", "601013"}
_ASIATIC_CREDITS: Dict[str, int] = {
    "601003": 1,    # Pearl Harbor
    "601005": 1,    # Pearl Harbor
    "601007": 1,    # B-29 missions against Japan
    "601008": 3,    # India/Burma operations named in the biography
    "601012": 3,    # South Pacific, Philippines, Okinawa
    "601013": 1,    # Pearl Harbor
}
_EAME_CREDITS: Dict[str, int] = {
    "601001": 1,
    "601002": 1,
    "601003": 3,
    "601004": 1,
    "601005": 1,
    "601007": 1,
    "601008": 6,
    "601009": 6,
    "601010": 3,
    "601011": 3,
    "601013": 3,
}
_WWII_VICTORY = {f"601{i:03d}" for i in range(1, 14)}

# The Soviet biography text supports these awards directly.  Moscow is kept
# as an available family because its artwork was supplied, but no selectable
# biography says that its pilot served in the defense of Moscow.  Birthplace
# and a post-war posting near Moscow are not award eligibility.
_DEFENSE_LENINGRAD = {"501002", "501005", "501009"}
_DEFENSE_MOSCOW = set()
_DEFENSE_STALINGRAD = {"501011"}
_VICTORY_GERMANY = {f"501{i:03d}" for i in range(1, 14)}
_VICTORY_JAPAN = {
    "501001", "501002", "501004", "501005", "501006", "501007",
    "501009", "501010", "501011", "501012", "501014",
}


_FAMILY = {
    AMERICAN_DEFENSE: "american_defense",
    **{award_id: "asiatic_pacific" for award_id in ASIATIC_PACIFIC},
    **{award_id: "eame" for award_id in EAME},
    WWII_VICTORY: "wwii_victory",
    DEFENSE_LENINGRAD: "defense_leningrad",
    DEFENSE_MOSCOW: "defense_moscow",
    DEFENSE_STALINGRAD: "defense_stalingrad",
    VICTORY_GERMANY: "victory_germany",
    VICTORY_JAPAN: "victory_japan",
}

_NAMES = {
    "eng": {
        "american_defense": "American Defense Service Medal",
        "asiatic_pacific": "Asiatic-Pacific Campaign Medal",
        "eame": "European-African-Middle Eastern Campaign Medal",
        "wwii_victory": "World War II Victory Medal",
        "defense_leningrad": "Medal for the Defense of Leningrad",
        "defense_moscow": "Medal for the Defense of Moscow",
        "defense_stalingrad": "Medal for the Defense of Stalingrad",
        "victory_germany": "Medal for Victory over Germany in the Great Patriotic War 1941–1945",
        "victory_japan": "Medal for Victory over Japan",
    },
    "ger": {
        "american_defense": "Amerikanische Verteidigungsdienstmedaille",
        "asiatic_pacific": "Asiatisch-Pazifische Feldzugsmedaille",
        "eame": "Europa-Afrika-Nahost-Feldzugsmedaille",
        "wwii_victory": "Siegesmedaille des Zweiten Weltkriegs",
        "defense_leningrad": "Medaille „Für die Verteidigung Leningrads“",
        "defense_moscow": "Medaille „Für die Verteidigung Moskaus“",
        "defense_stalingrad": "Medaille „Für die Verteidigung Stalingrads“",
        "victory_germany": "Medaille „Sieg über Deutschland im Großen Vaterländischen Krieg 1941–1945“",
        "victory_japan": "Medaille „Sieg über Japan“",
    },
    "spa": {
        "american_defense": "Medalla del Servicio de Defensa Estadounidense",
        "asiatic_pacific": "Medalla de la Campaña de Asia-Pacífico",
        "eame": "Medalla de la Campaña de Europa-África-Oriente Medio",
        "wwii_victory": "Medalla de la Victoria de la Segunda Guerra Mundial",
        "defense_leningrad": "Medalla por la Defensa de Leningrado",
        "defense_moscow": "Medalla por la Defensa de Moscú",
        "defense_stalingrad": "Medalla por la Defensa de Stalingrado",
        "victory_germany": "Medalla por la Victoria sobre Alemania en la Gran Guerra Patria de 1941–1945",
        "victory_japan": "Medalla por la Victoria sobre Japón",
    },
    "fra": {
        "american_defense": "Médaille du service de défense américain",
        "asiatic_pacific": "Médaille de la campagne d’Asie-Pacifique",
        "eame": "Médaille de la campagne Europe-Afrique-Moyen-Orient",
        "wwii_victory": "Médaille de la victoire de la Seconde Guerre mondiale",
        "defense_leningrad": "Médaille pour la défense de Léningrad",
        "defense_moscow": "Médaille pour la défense de Moscou",
        "defense_stalingrad": "Médaille pour la défense de Stalingrad",
        "victory_germany": "Médaille de la victoire sur l’Allemagne dans la Grande Guerre patriotique de 1941–1945",
        "victory_japan": "Médaille de la victoire sur le Japon",
    },
    "rus": {
        "american_defense": "Медаль «За службу в обороне Америки»",
        "asiatic_pacific": "Медаль «За Азиатско-Тихоокеанскую кампанию»",
        "eame": "Медаль «За Европейско-Африканско-Ближневосточную кампанию»",
        "wwii_victory": "Медаль Победы во Второй мировой войне",
        "defense_leningrad": "Медаль «За оборону Ленинграда»",
        "defense_moscow": "Медаль «За оборону Москвы»",
        "defense_stalingrad": "Медаль «За оборону Сталинграда»",
        "victory_germany": "Медаль «За победу над Германией в Великой Отечественной войне 1941–1945 гг.»",
        "victory_japan": "Медаль «За победу над Японией»",
    },
    "chs": {
        "american_defense": "美国防御服役奖章",
        "asiatic_pacific": "亚太战役奖章",
        "eame": "欧洲-非洲-中东战役奖章",
        "wwii_victory": "第二次世界大战胜利奖章",
        "defense_leningrad": "列宁格勒保卫奖章",
        "defense_moscow": "莫斯科保卫奖章",
        "defense_stalingrad": "斯大林格勒保卫奖章",
        "victory_germany": "伟大卫国战争中战胜德国奖章",
        "victory_japan": "战胜日本奖章",
    },
}


def name(award_id: int, lang: str = "eng") -> Optional[str]:
    """Localized family name for a synthetic award id, if it is one."""
    family = _FAMILY.get(award_id)
    if family is None:
        return None
    return (_NAMES.get(lang) or _NAMES["eng"])[family]


def for_biography(biography_id: str, country: int = 601) -> Tuple[int, ...]:
    """Prior-service award ids worn by one selectable biography."""
    bio = str(biography_id or "")
    if country == 501:
        out = []
        if bio in _DEFENSE_LENINGRAD:
            out.append(DEFENSE_LENINGRAD)
        if bio in _DEFENSE_MOSCOW:
            out.append(DEFENSE_MOSCOW)
        if bio in _DEFENSE_STALINGRAD:
            out.append(DEFENSE_STALINGRAD)
        if bio in _VICTORY_GERMANY:
            out.append(VICTORY_GERMANY)
        if bio in _VICTORY_JAPAN:
            out.append(VICTORY_JAPAN)
        return tuple(out)
    if country != 601 or bio not in _WWII_VICTORY:
        return ()
    out = []
    if bio in _AMERICAN_DEFENSE:
        out.append(AMERICAN_DEFENSE)
    if bio in _ASIATIC_CREDITS:
        out.append(ASIATIC_PACIFIC[_ASIATIC_CREDITS[bio]])
    if bio in _EAME_CREDITS:
        out.append(EAME[_EAME_CREDITS[bio]])
    out.append(WWII_VICTORY)
    return tuple(out)


def for_career_description(description: str, country: int = 601) -> Tuple[int, ...]:
    """Prior-service awards for an existing career's ``pilot.description``.

    The game persists the selected biography in that field when it creates a
    career.  Deriving the awards every time the record is read means careers
    which predate this feature receive their WWII medals immediately, without
    synthetic award rows being written into the game's Korean-war history.
    """
    fields = {}
    for pair in urllib.parse.unquote(description or "").split("&"):
        key, _, value = pair.partition("=")
        if key:
            fields[key] = value
    return for_biography(fields.get("biographyId", ""), country)
