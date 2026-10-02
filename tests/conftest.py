"""
Synthetic career files for the 2.2.0 kill-fix and recovery tests.

Nothing here needs the game. A career is a small SQLite file with only the
columns killfix, napalmfix, recovery and KoreaCareerDatabase query; the
game's statobjects.json and statreporting.json are replaced by a few lines
written as loose files under a fake game folder, which AssetResolver reads
before it ever looks for an archive.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from korea_service_record import corrections
from korea_service_record.career.killfix import KillCategories

from napalm_scenario import P1_TOTAL, P2_TOTAL, S2_RAW, S3_RAW, SQ_TOTAL

# A cut-down statobjects.json: category -> {"objects": [...]}, keys as the
# game writes them (with the "kill" prefix).
STAT_OBJECTS = {
    "killMilitaryFacility": {"objects": ["Mil_boxes_02", "Mil_tent_01"]},
    "killStaticPlane": {"objects": ["Static_plane_La11"]},
    "killLightFlak": {"objects": ["61K"]},
    "killTruck": {"objects": ["GAZ-AA"]},
    "killTrainLocomotive": {"objects": ["E_loco"]},
    "killLightFighter": {"objects": ["mig15bis"]},
}

# A cut-down statreporting.json: only "internal" is read.
STAT_REPORTING = {
    "internal": {
        "killAircraft": ["killStaticPlane", "killLightFighter"],
        "killMateriel": ["killLightFlak", "killTruck"],
        "killBuilding": ["killMilitaryFacility"],
        "killRailroad": ["killTrainLocomotive"],
    }
}

SCHEMA = """
CREATE TABLE career   (id INTEGER PRIMARY KEY, playerId INTEGER, startDate TEXT, currentDate TEXT);
CREATE TABLE squadron (id INTEGER PRIMARY KEY, killStats TEXT, flightTime INTEGER DEFAULT 0,
                       isDeleted INTEGER DEFAULT 0);
CREATE TABLE pilot    (id INTEGER PRIMARY KEY, name TEXT, lastName TEXT, isPlayer INTEGER DEFAULT 0,
                       killStats TEXT, pcp REAL, score INTEGER, rankId INTEGER DEFAULT 1,
                       flightTime INTEGER DEFAULT 0, slot INTEGER DEFAULT 0, state INTEGER DEFAULT 0,
                       isDeleted INTEGER DEFAULT 0);
CREATE TABLE mission  (id INTEGER PRIMARY KEY, date TEXT, startTime TEXT, endTime TEXT,
                       result TEXT DEFAULT '', pilotsList TEXT DEFAULT '', isDeleted INTEGER DEFAULT 0);
CREATE TABLE sortie   (id INTEGER PRIMARY KEY, missionId INTEGER, pilotId INTEGER, planeId INTEGER,
                       rankId INTEGER, isPlayer INTEGER DEFAULT 0, score INTEGER DEFAULT 0,
                       status INTEGER DEFAULT 0, health INTEGER DEFAULT 100,
                       planeStatus INTEGER DEFAULT 0, planeHealth INTEGER DEFAULT 100,
                       killStats TEXT, assistCount INTEGER DEFAULT 0, fkill INTEGER DEFAULT 0,
                       flightTime INTEGER DEFAULT 0, date TEXT, insDate TEXT,
                       isDeleted INTEGER DEFAULT 0, eventFlags INTEGER DEFAULT 0,
                       returnTime INTEGER DEFAULT 0);
CREATE TABLE event    (id INTEGER PRIMARY KEY, date TEXT, type INTEGER, pilotId INTEGER,
                       rankId INTEGER, missionId INTEGER, planeId INTEGER,
                       ipar1 INTEGER, ipar2 INTEGER, ipar3 INTEGER,
                       tpar1 TEXT, isDeleted INTEGER DEFAULT 0);
"""


@pytest.fixture
def table() -> KillCategories:
    """The category table built the way from_resolver builds it."""
    return KillCategories.from_resolver(_FakeResolver())


class _FakeResolver:
    def read_text(self, vpath):
        if vpath.endswith("statobjects.json"):
            return json.dumps(STAT_OBJECTS)
        if vpath.endswith("statreporting.json"):
            return json.dumps(STAT_REPORTING)
        return None


@pytest.fixture
def game_dir(tmp_path, monkeypatch) -> Path:
    """A game folder holding only the two world-object tables, loose."""
    root = tmp_path / "game"
    folder = root / "data" / "nsdata" / "assets" / "worldobjects"
    folder.mkdir(parents=True)
    (folder / "statobjects.json").write_text(json.dumps(STAT_OBJECTS), encoding="utf-8")
    (folder / "statreporting.json").write_text(json.dumps(STAT_REPORTING), encoding="utf-8")
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "cache" / "assets"))
    return root


@pytest.fixture(autouse=True)
def tracker_folders(tmp_path, monkeypatch):
    """Records and backups go to tmp, never to the real LOCALAPPDATA."""
    monkeypatch.setattr(corrections, "FOLDER", tmp_path / "corrections")
    monkeypatch.setattr(corrections, "BACKUPS", tmp_path / "backups")
    return tmp_path


class Career:
    """A synthetic career file and helpers to fill and read it."""

    def __init__(self, path: Path):
        self.path = path
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        con.commit()
        con.close()

    def run(self, sql, params=()):
        con = sqlite3.connect(self.path)
        try:
            cur = con.execute(sql, params)
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def one(self, sql, params=()):
        con = sqlite3.connect(self.path)
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()

    def all(self, sql, params=()):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    # -- filling -------------------------------------------------------------

    def squadron(self, kills, sid=1):
        self.run("INSERT INTO squadron (id, killStats) VALUES (?, ?)", (sid, kills))

    def pilot(self, pid, kills, score=0, pcp=0.0, is_player=0, name="Pilot", rank=1):
        self.run("INSERT INTO pilot (id, name, lastName, isPlayer, killStats, pcp, score, rankId) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (pid, name, str(pid), is_player, kills, pcp, score, rank))

    def mission(self, mid, start="1951.05.01 08:00:00", end="1951.05.01 09:00:00",
                result="", pilots_list=""):
        self.run("INSERT INTO mission (id, date, startTime, endTime, result, pilotsList) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (mid, start[:10], start, end, result, pilots_list))

    def sortie(self, mission_id, pilot_id, kills, date=None, sid=None):
        return self.run("INSERT INTO sortie (id, missionId, pilotId, planeId, rankId, killStats, date) "
                        "VALUES (?, ?, ?, ?, 1, ?, ?)",
                        (sid, mission_id, pilot_id, 100 + pilot_id, kills,
                         date or f"1951.05.{mission_id:02d} 08:00:00"))

    def kills(self, mission_id, pilot_id, *names):
        for name in names:
            self.run("INSERT INTO event (date, type, pilotId, missionId, tpar1) VALUES (?, 0, ?, ?, ?)",
                     (f"1951.05.{mission_id:02d} 08:30:00", pilot_id, mission_id, name))

    # -- reading -------------------------------------------------------------

    def sortie_kills(self, sid):
        return self.one("SELECT killStats FROM sortie WHERE id = ?", (sid,))[0]

    def pilot_row(self, pid):
        return self.one("SELECT killStats, pcp, score FROM pilot WHERE id = ?", (pid,))

    def squadron_kills(self):
        return self.one("SELECT killStats FROM squadron LIMIT 1")[0]


@pytest.fixture
def career(tmp_path) -> Career:
    return Career(tmp_path / "Test Pilot, 12th FBS.db")


@pytest.fixture
def napalm_career(career):
    """The napalm scenario described in test_napalmfix.py."""
    c = career
    c.squadron(SQ_TOTAL)
    c.pilot(1, P1_TOTAL, score=100, pcp=150.0, is_player=1)
    c.pilot(2, P2_TOTAL, score=30, pcp=30.0)
    c.mission(1)
    c.mission(2)
    c.sortie(1, 1, "Aircraft=2&LightFighter=2", sid=1)
    c.kills(1, 1, "mig15bis", "mig15bis")
    c.sortie(2, 1, S2_RAW, sid=2)
    c.kills(2, 1, "Mil_boxes_02", "Mil_tent_01", "Static_plane_La11")
    c.sortie(2, 2, S3_RAW, sid=3)
    c.kills(2, 2, "Mil_boxes_02")
    return c
