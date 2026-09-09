"""
Decoder for the packed pilot attribute columns ``persLevel`` and ``leadLevel``.

The "Award and Promotion" screen shows three bars per pilot — SKILLS,
DISCIPLINE, COURAGE — each with a value and a small purple "up" number. None of
that is stored in named columns. Both triples are nibble-packed into single
integers on ``pilot``.

Confirmed against Manuel Rivera (pilot 17), whose panel reads
SKILLS 4 / DISCIPLINE 5 / COURAGE 5 with up-numbers 13 / 2 / 2::

    persLevel = 1091 = 0x443  -> nibbles low->high 3, 4, 4  -> displayed 4, 5, 5
    leadLevel =  557 = 0x22d  -> nibbles low->high 13, 2, 2 -> up-numbers 13, 2, 2

So ``persLevel`` holds the attribute levels **zero-based** and the UI renders
level + 1, while ``leadLevel`` holds the up-numbers verbatim. Both read low
nibble first.

The packing order is NOT the panel's display order. Rivera cannot distinguish
them because his two upper nibbles are equal; Jesse Funston (pilot 8) settles
it::

    persLevel = 1075 = 0x433  -> nibbles low->high 3, 3, 4
    panel: SKILLS 4, DISCIPLINE 5, COURAGE 4
    leadLevel =    1 = 0x001  -> nibbles low->high 1, 0, 0
    panel up-numbers: SKILLS 1, DISCIPLINE 0, COURAGE 0

The high nibble is 4 and the only bar reading 5 is DISCIPLINE, so the packed
order is **skills, courage, discipline** while the panel lists skills,
discipline, courage. Rivera re-checks consistently under this order, and so
does the player, whose leadLevel 0x220 yields up-numbers 0 / 2 / 2 in panel
order.

The commander has boosters, not levels
--------------------------------------
The player's ``persLevel`` is 0, and the game does not draw him any bars. His
card lists **SKILLS BOOSTER / DISCIPLINE BOOSTER / COURAGE BOOSTER** with just
the ``leadLevel`` values and no levels at all — the human at the controls
supplies the flying, so the engine simulates leadership instead. Rendering his
zero nibbles as "1 / 1 / 1" is wrong; ``has_levels`` is False for him.

Every AI pilot has a non-zero ``persLevel``, including untested replacements
(pilot 45 = 0x011 -> skills 2, courage 2, discipline 1).

Verified against five pilots' panels::

    pilot  4 MacMurphy  persLevel 0x243 -> 4 / 3 / 5   leadLevel 0x101 -> 1 / 1 / 0
    pilot  8 Funston    persLevel 0x433 -> 4 / 5 / 4   leadLevel 0x001 -> 1 / 0 / 0
    pilot 11 Hoffhines  persLevel 0x322 -> 3 / 4 / 3   leadLevel 0x110 -> 0 / 1 / 1
    pilot 17 Rivera     persLevel 0x443 -> 4 / 5 / 5   leadLevel 0x22d -> 13 / 2 / 2
    pilot 20 Zink       persLevel 0x000 -> commander   leadLevel 0x220 -> 0 / 2 / 2

(shown in panel order: skills, discipline, courage)

What the ``leadLevel`` numbers actually do is still open. On the commander they
are labelled boosters, so they presumably feed the squadron; on an AI pilot
they are not simply a copy of the commander's, since MacMurphy carries a skills
1 where the commander's skills booster is 0.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Packed order, low nibble -> high nibble. Confirmed by pilot 8 (see docstring).
# Note this differs from the panel's display order (skills, discipline, courage).
ATTRIBUTE_ORDER: List[str] = ["skills", "courage", "discipline"]

# Display order used by the game's own panels, top to bottom.
DISPLAY_ORDER: List[str] = ["skills", "discipline", "courage"]

ORDER_VERIFIED = True

# The UI renders persLevel nibble + 1.
DISPLAY_OFFSET = 1

NIBBLE_COUNT = 3


def _nibbles(value: Optional[int], count: int = NIBBLE_COUNT) -> List[int]:
    """Split an int into `count` 4-bit fields, low nibble first."""
    if not value or value < 0:
        return [0] * count
    return [(value >> (4 * i)) & 0xF for i in range(count)]


class PilotAttributes:
    """Decoded SKILLS / DISCIPLINE / COURAGE for one pilot."""

    def __init__(self, pers_level: Optional[int], lead_level: Optional[int] = None):
        self.pers_level = pers_level or 0
        self.lead_level = lead_level or 0

        raw_levels = _nibbles(self.pers_level)
        raw_points = _nibbles(self.lead_level)

        self.levels: Dict[str, int] = {
            name: raw_levels[i] + DISPLAY_OFFSET
            for i, name in enumerate(ATTRIBUTE_ORDER)
        }
        self.raw_levels: Dict[str, int] = {
            name: raw_levels[i] for i, name in enumerate(ATTRIBUTE_ORDER)
        }
        self.points: Dict[str, int] = {
            name: raw_points[i] for i, name in enumerate(ATTRIBUTE_ORDER)
        }

    @property
    def skills(self) -> int:
        return self.levels["skills"]

    @property
    def discipline(self) -> int:
        return self.levels["discipline"]

    @property
    def courage(self) -> int:
        return self.levels["courage"]

    @property
    def has_levels(self) -> bool:
        """
        False for the squadron commander, who has boosters instead of skill.

        A zero ``persLevel`` is the engine's way of saying "not simulated", not
        a pilot with minimum ability — the game draws no bars for him at all.
        """
        return self.pers_level != 0

    def display_rows(self) -> List[Dict[str, int]]:
        """
        Rows in the game's panel order, for a UI that mirrors it.

        ``level`` is None for the commander so a caller cannot accidentally
        render a bar for someone who has none.
        """
        return [{"name": name,
                 "level": self.levels[name] if self.has_levels else None,
                 "points": self.points[name]}
                for name in DISPLAY_ORDER]

    def as_dict(self) -> Dict[str, Dict[str, int]]:
        return {
            "levels": dict(self.levels),
            "points": dict(self.points),
            "order_verified": ORDER_VERIFIED,
        }

    def __repr__(self) -> str:
        return ("<PilotAttributes skills={skills} discipline={discipline} "
                "courage={courage}>").format(**self.levels)
