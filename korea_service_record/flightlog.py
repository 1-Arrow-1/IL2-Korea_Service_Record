"""
Reads ``data/FlightLogs/*.mlg`` for the parts of a sortie the career DB omits.

The career database records that a sortie happened, how long it lasted and what
died. It does not record when the wheels left the ground, when they touched
down, or whether the pilot walked away. The binary mission log has all three.

Format
------
Identical to IL-2 Great Battles at **log version 18** (Great Battles is 17), so
the community ``mlg2txt`` decoder reads Korea's logs after relaxing one version
assert — which is how the layouts below were confirmed rather than guessed.

A file is a flat sequence of records::

    7-byte header   <LBH>  tick (50 Hz), AType, payload size
    payload         `size` bytes
    b"\\n"

Only five record types are decoded; the rest are skipped by seeking past their
payload. That matters: a 1.4 MB log holds ~40,000 records and about a dozen are
relevant, so a full parse would cost 40,000 string formats for nothing.

    0   MissionStart    game date and time — how a log is matched to a sortie
    5   TakeOff         PID, position
    6   Landing         PID, position
    10  PlayerPlane     PLID, PID, ..., TYPE, ..., ISPL (1 = the human)
    18  BotEjectLeave   BOTID — the pilot got out

``AType:4`` (PlayerMissionEnd) also exists but fires whenever the player leaves,
including a clean exit after landing, so it says nothing on its own.
"""

import logging
import re
import struct
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

TICKS_PER_SECOND = 50.0
HEADER = struct.Struct("<LBH")

WANTED = {0, 2, 5, 6, 10, 12, 18}

# A burst is a run of damage records with no longer pause than this between
# them. Cannon fire arrives as several records in the same tenth of a second
# and a sortie's worth of them, listed one by one, says nothing a reader can
# use; the two passes a Mustang actually took were 505 seconds apart.
BURST_GAP_S = 15.0


class DamageBurst(NamedTuple):
    """One pass, however many records the log split it into."""
    at_s: float                     # when the burst ended
    hits: int
    amount: float                   # inflicted in this burst, 0..1
    total: float                    # of the aircraft lost by the end of it
    attacker: str                   # "" when the log never named it


class SortieLog(NamedTuple):
    path: Path
    date: str                       # "1951.06.01"
    time: str                       # "06:25"
    takeoff_s: Optional[float]
    landing_s: Optional[float]
    ejected: bool
    plane: str
    damage: List["DamageBurst"] = []

    @property
    def outcome(self) -> str:
        if self.ejected:
            return "bailed out"
        if self.landing_s is not None:
            return "landed"
        return "did not return"

    @property
    def airborne_s(self) -> Optional[float]:
        if self.takeoff_s is None or self.landing_s is None:
            return None
        return max(0.0, self.landing_s - self.takeoff_s)


class _Reader:
    """Pull typed fields out of one record payload."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def int32(self) -> int:
        value = struct.unpack_from("<l", self.data, self.pos)[0]
        self.pos += 4
        return value

    def uint32(self) -> int:
        value = struct.unpack_from("<L", self.data, self.pos)[0]
        self.pos += 4
        return value

    def string(self) -> str:
        length = self.uint32()
        text = self.data[self.pos:self.pos + length].decode("ascii", "replace")
        self.pos += length
        return text

    def skip(self, count: int) -> None:
        self.pos += count


def _records(path: Path) -> Iterator[Tuple[int, int, bytes]]:
    """Yield (tick, atype, payload) for records worth decoding."""
    try:
        with open(path, "rb") as handle:
            while True:
                head = handle.read(7)
                if len(head) < 7:
                    return
                tick, atype, size = HEADER.unpack(head)
                if atype in WANTED:
                    payload = handle.read(size)
                    yield tick, atype, payload
                else:
                    handle.seek(size, 1)
                handle.seek(1, 1)          # trailing newline
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)


def read_log(path: Path) -> Optional[SortieLog]:
    """Summarise one mission log, or None if it has no player and no header."""
    date = time = plane = ""
    player_plid: Optional[int] = None
    player_bot: Optional[int] = None
    takeoff = landing = None
    ejected = False
    # AType 2 is [float amount][attacker][target][x][y][z]. Collected for
    # everyone because the player's own object id is not known until the
    # AType 10 that names him, which need not come first.
    harm: List[Tuple[int, float, int, int]] = []
    named: Dict[int, str] = {}

    for tick, atype, payload in _records(path):
        try:
            if atype == 0 and not date:
                r = _Reader(payload)
                y, m, d = r.uint32(), r.uint32(), r.uint32()
                hh, mm, _ss = r.uint32(), r.uint32(), r.uint32()
                date, time = f"{y:04d}.{m:02d}.{d:02d}", f"{hh:02d}:{mm:02d}"
            elif atype == 10 and player_plid is None:
                r = _Reader(payload)
                plid, pid = r.int32(), r.int32()
                r.skip(16)                      # bul, sh, bomb, rct
                r.skip(12)                      # position
                r.string()                      # ids
                r.string()                      # login
                r.string()                      # name
                ptype = r.string()
                r.string()                      # country
                r.skip(12)                      # form, field, inair
                r.int32()                       # parent
                if r.int32() == 1:              # ispl — the human
                    player_plid, player_bot, plane = plid, pid, ptype
            elif atype in (5, 6) and player_plid is not None:
                if _Reader(payload).int32() == player_plid:
                    seconds = tick / TICKS_PER_SECOND
                    if atype == 5 and takeoff is None:
                        takeoff = seconds
                    elif atype == 6:
                        landing = seconds
            elif atype == 2 and len(payload) >= 12:
                amount, attacker, target = struct.unpack_from("<fII", payload, 0)
                harm.append((tick, amount, attacker, target))
            elif atype == 12 and len(payload) > 12:
                r = _Reader(payload)
                oid = r.int32()
                r.string()                      # type
                r.string()                      # country
                who = r.string()
                if who:
                    named[oid] = who
            elif atype == 18 and player_bot is not None:
                if _Reader(payload).int32() == player_bot:
                    ejected = True
        except (struct.error, IndexError):
            continue                            # a short record is not fatal

    if not date:
        return None
    return SortieLog(path, date, time, takeoff, landing, ejected, plane,
                     _bursts(harm, player_plid, named))


def _bursts(harm, target_id: Optional[int],
            named: Dict[int, str]) -> List[DamageBurst]:
    """
    Group the damage done to one aircraft into the passes that caused it.

    The running total is what the reader wants — "half the aircraft gone by
    the second pass" — rather than each record's own fraction, and it is
    checkable: the total after the last burst equals the figure mission.result
    stores for that pilot. Verified at 0.5398 on the sortie that brought the
    Mustang home on 1951.06.01.
    """
    if target_id is None:
        return []
    mine = sorted((t, a, who) for t, a, who, tgt in harm if tgt == target_id)
    out: List[DamageBurst] = []
    total = 0.0
    for tick, amount, attacker in mine:
        seconds = tick / TICKS_PER_SECOND
        total += amount
        if out and seconds - out[-1].at_s <= BURST_GAP_S:
            last = out[-1]
            out[-1] = DamageBurst(seconds, last.hits + 1,
                                  last.amount + amount, total,
                                  last.attacker or named.get(attacker, ""))
        else:
            out.append(DamageBurst(seconds, 1, amount, total,
                                   named.get(attacker, "")))
    return out


class FlightLogIndex:
    """
    Matches career sorties to mission logs by in-game date and start time.

    ``AType:0`` carries the same date and time the ``sortie`` row does, so the
    join needs no filename guesswork. Results are held for the process because
    a folder of 90 logs takes a couple of seconds to scan.
    """

    def __init__(self, game_dir: Path):
        self.folder = Path(game_dir) / "data" / "FlightLogs"
        self._logs: Optional[Dict[str, SortieLog]] = None

    @staticmethod
    def key(date: str, time: str) -> str:
        """Normalise '1951.06.01' + '06:25:00' to a comparable key."""
        try:
            y, m, d = (int(n) for n in re.split(r"[.\-]", date.strip())[:3])
            hh, mm = (int(n) for n in time.strip().split(":")[:2])
            return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}"
        except (ValueError, IndexError):
            return ""

    def logs(self) -> Dict[str, SortieLog]:
        if self._logs is not None:
            return self._logs
        found: Dict[str, SortieLog] = {}
        if self.folder.is_dir():
            for path in sorted(self.folder.glob("*.mlg")):
                log = read_log(path)
                if log is None:
                    continue
                key = self.key(log.date, log.time)
                # Several logs can share a start time when a mission is flown
                # more than once; the newest file is the one that counts.
                if key and (key not in found
                            or path.stat().st_mtime > found[key].path.stat().st_mtime):
                    found[key] = log
            logger.info("Flight logs: %d usable of %d files",
                        len(found), len(list(self.folder.glob("*.mlg"))))
        self._logs = found
        return found

    def for_sortie(self, date: str, time: str) -> Optional[SortieLog]:
        return self.logs().get(self.key(date, time))
