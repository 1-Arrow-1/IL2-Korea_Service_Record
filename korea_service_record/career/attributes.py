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
nibble first, in panel order (top to bottom).

Open question
-------------
Rivera's middle and high persLevel nibbles are both 4, so his row cannot
distinguish DISCIPLINE from COURAGE. Jesse Funston (pilot 8) breaks the tie:
persLevel 1075 = 0x433 -> 3, 3, 4, so whichever of his DISCIPLINE/COURAGE bars
reads 5 identifies the high nibble. Until that is checked in game, the ordering
below is the best-supported guess and is flagged by ``ORDER_VERIFIED``.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Panel order, top to bottom, matching low nibble -> high nibble.
ATTRIBUTE_ORDER: List[str] = ["skills", "discipline", "courage"]

# Flip to True once Funston's panel has confirmed discipline vs courage.
ORDER_VERIFIED = False

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

    def as_dict(self) -> Dict[str, Dict[str, int]]:
        return {
            "levels": dict(self.levels),
            "points": dict(self.points),
            "order_verified": ORDER_VERIFIED,
        }

    def __repr__(self) -> str:
        return ("<PilotAttributes skills={skills} discipline={discipline} "
                "courage={courage}>").format(**self.levels)
