"""
KoreaCareerDatabase: read-only SQLite access layer for IL-2 Korea career files.

Design decisions:
- Read-only connection via URI mode:  file:<path>?mode=ro
  Prevents any accidental writes to the live game database. The game keeps the
  file open while running, so every query must tolerate transient lock errors.
- Lazy connection: sqlite3 handle created on first query call, cached thereafter.
- sqlite3.Row factory: all rows returned with named column access (row["column"]).
- No ORM. Plain parameterised statements only.

Difference from IL-2 Great Battles
---------------------------------
Great Battles keeps every career in a single ``cp.db`` and needs a chain
resolver to stitch theatres together. Korea writes **one database per career**
into ``<game>/data/Career/``, named ``"<First> <Last>, <Squadron>.db"``. Each
file is self-contained: one row in ``career``, one squadron, one roster. So
career discovery is a directory listing, not a graph walk.

Schema (confirmed against a live 1951 F-51D career)
---------------------------------------------------
career    id, personageId, playerId, tvd, currentDate, squadronId, startDate, ...
squadron  id, awardPoints, efficiency, score, sorties, killStats, operations, ...
pilot     id, name, lastName, country, rankId, persLevel, leadLevel, sorties,
          goodSorties, flightTime, killStats, state, health, careerStartDate,
          squadronId, slot, isPlayer, wounded, pcp, ...
award     id, type, category, pilotId, pilotRank, isPending, cost,
          earnedDate, receivedDate, isDeleted
sortie    id, missionId, pilotId, planeId, rankId, isPlayer, score, status,
          health, planeStatus, killStats, flightTime, date
mission   id, missionNum, date, startTime, endTime, operationId, estDuration
event     id, date, type, pilotId, rankId, missionId, ipar1..4, tpar1..4
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Career file discovery
# ---------------------------------------------------------------------------

class CareerFile:
    """
    One ``.db`` in ``<game>/data/Career/``.

    The filename carries the pilot and squadron, but it is only a hint: the
    player may have been renamed or transferred. Authoritative values come from
    the ``career`` and ``pilot`` tables, so ``pilot_name``/``squadron_name`` here
    are used for sorting and for a cheap listing that avoids opening every file.
    """

    # "Alexander Zink, 39th FIS USAF.db"
    _NAME_RE = re.compile(r'^(?P<pilot>.+?),\s*(?P<squadron>.+)$')

    def __init__(self, path: Path):
        self.path = path
        stem = path.stem
        match = self._NAME_RE.match(stem)
        if match:
            self.pilot_name = match.group("pilot").strip()
            self.squadron_name = match.group("squadron").strip()
        else:
            self.pilot_name = stem
            self.squadron_name = ""

    def __repr__(self) -> str:
        return f"<CareerFile {self.pilot_name!r} / {self.squadron_name!r}>"


def find_careers(game_dir: Path) -> List[CareerFile]:
    """
    List every career database under ``<game_dir>/data/Career``.

    Returns an empty list when the folder is missing rather than raising, so a
    wrong game path surfaces as "no careers found" in the UI instead of a crash.
    """
    career_dir = Path(game_dir) / "data" / "Career"
    if not career_dir.is_dir():
        logger.warning("Career directory not found: %s", career_dir)
        return []
    careers = [CareerFile(p) for p in sorted(career_dir.glob("*.db"))]
    logger.info("Found %d career database(s) in %s", len(careers), career_dir)
    return careers


# ---------------------------------------------------------------------------
# Read-only database wrapper
# ---------------------------------------------------------------------------

class KoreaCareerDatabase:
    """Read-only accessor for a single Korea career database."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None

    # -- connection ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            # check_same_thread=False: the Flask dev server and the frozen
            # waitress build both serve requests from a worker thread pool.
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            logger.debug("Opened read-only connection: %s", self.path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "KoreaCareerDatabase":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- query helpers ------------------------------------------------------

    def query(self, sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
        """
        Run a SELECT and return all rows.

        Returns [] on sqlite3.Error rather than raising: the game holds the file
        open while running and a query can transiently fail. Callers render an
        empty view and the next poll succeeds.
        """
        try:
            return self._connect().execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Query failed on %s: %s", self.path.name, exc)
            return []

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- domain accessors ---------------------------------------------------

    def career(self) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM career LIMIT 1")

    def squadron(self) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM squadron WHERE isDeleted=0 LIMIT 1")

    def pilots(self, include_deleted: bool = False) -> List[sqlite3.Row]:
        sql = "SELECT * FROM pilot"
        if not include_deleted:
            sql += " WHERE isDeleted=0"
        return self.query(sql + " ORDER BY slot, id")

    def player(self) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM pilot WHERE isPlayer=1 AND isDeleted=0")

    def pilot(self, pilot_id: int) -> Optional[sqlite3.Row]:
        return self.query_one("SELECT * FROM pilot WHERE id=?", (pilot_id,))

    def awards(self, pilot_id: Optional[int] = None,
               include_removed: bool = False) -> List[sqlite3.Row]:
        """
        Award rows.

        ``isDeleted=1`` means the award was retired by a higher cluster via
        ``AwardRemove`` — normal bookkeeping, not a deletion, so it is excluded
        by default but available for a full service history.
        """
        sql = "SELECT * FROM award WHERE 1=1"
        params: List[Any] = []
        if pilot_id is not None:
            sql += " AND pilotId=?"
            params.append(pilot_id)
        if not include_removed:
            sql += " AND isDeleted=0"
        return self.query(sql + " ORDER BY id", params)

    def sorties(self, pilot_id: Optional[int] = None) -> List[sqlite3.Row]:
        sql = "SELECT * FROM sortie WHERE isDeleted=0"
        params: List[Any] = []
        if pilot_id is not None:
            sql += " AND pilotId=?"
            params.append(pilot_id)
        return self.query(sql + " ORDER BY id", params)

    def missions(self) -> List[sqlite3.Row]:
        return self.query("SELECT * FROM mission WHERE isDeleted=0 ORDER BY id")

    def events(self, pilot_id: Optional[int] = None,
               types: Optional[Iterable[int]] = None) -> List[sqlite3.Row]:
        sql = "SELECT * FROM event WHERE isDeleted=0"
        params: List[Any] = []
        if pilot_id is not None:
            sql += " AND pilotId=?"
            params.append(pilot_id)
        types = list(types) if types is not None else None
        if types:
            sql += " AND type IN (%s)" % ",".join("?" * len(types))
            params.extend(types)
        return self.query(sql + " ORDER BY id", params)

    def table_names(self) -> List[str]:
        return [r[0] for r in self.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
