"""
The squadron's operations tally.

``squadron.operations`` is an ``&``-separated ``operationId=state`` map, the
same shape as ``killStats``. The ids index ``scg/2/operations.cfg``, where every
historical operation is defined twice - an odd id for the Western Bloc and the
even id after it for the Eastern, each listing its own countries. Only an
operation that has *ended* is recorded; one still running is simply absent.

The state is the same value the type-33 end event carries in ``ipar2``, which
matched on all 24 concluded operations across the two careers this was derived
from, and the game has a string for each:

    1  carEventOperationSuccess  "$[name] has ended successfully"
    2  carEventOperationFailure  "$[name] has ended unsuccessfully"
    3  carEventOperationMissed   "$[name] has ended"

``awards.cfg`` documents what the totals mean, in its own words:

    OpTotal   - the number of operations the regiment took part in. For the
                regiment, operations in which not a single sortie was flown
                are counted too.
    OpSuccess - the number of successful ones.

So an operation the squadron never flew still counts against its total, which
is why a career can show three failures with no sorties in them.

**Hidden operations are excluded.** Ids 691-697 are ``hidden=1`` blocks: the
seven Korean Service Medal campaign phases (First UN Counteroffensive, CCF
Spring Offensive, and so on), which ``awards.cfg`` counts to grant campaign
stars. They have no begin or end event, no success to speak of, and exist only
for countries 601/602/603 - so an eastern career never has one. Counting them
would report nine operations where the game reports eight.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SUCCESS, FAILURE, NEUTRAL = 1, 2, 3

# scg/2/operations.cfg, the blocks marked hidden=1.
HIDDEN = range(691, 698)


class Operations:
    """Parsed view of one ``squadron.operations`` string."""

    def __init__(self, raw: Optional[str]):
        self.raw = raw or ""
        self.states: Dict[int, int] = {}
        for pair in self.raw.split("&"):
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            try:
                operation_id, state = int(key), int(value)
            except ValueError:
                logger.debug("Non-integer operations pair: %s=%s", key, value)
                continue
            if operation_id in HIDDEN:
                continue
            self.states[operation_id] = state

    @property
    def total(self) -> int:
        """Operations concluded, flown or not. The game's ``OpTotal``."""
        return len(self.states)

    @property
    def successful(self) -> int:
        """Those that ended successfully. The game's ``OpSuccess``."""
        return sum(1 for s in self.states.values() if s == SUCCESS)

    def as_dict(self) -> Dict[str, int]:
        return {"total": self.total, "successful": self.successful}
