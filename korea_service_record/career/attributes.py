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

The player character
--------------------
The player's ``persLevel`` is 0, which decodes to the minimum 1 / 1 / 1. That
looks wrong but is probably correct: the human at the controls supplies the
skill, so the engine has no reason to simulate the player's. Every AI pilot
checked has a non-zero ``persLevel``, including brand-new replacements
(pilot 45 = 0x011 -> skills 2, courage 2, discipline 1). Treat a zero
``persLevel`` as "not simulated" rather than as missing data.
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

    def display_rows(self) -> List[Dict[str, int]]:
        """Rows in the game's panel order, for a UI that mirrors it."""
        return [{"name": name,
                 "level": self.levels[name],
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
