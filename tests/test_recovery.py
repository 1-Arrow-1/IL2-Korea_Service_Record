"""
recovery: rebuilding the sortie rows of a mission that lost them, the napalm
offset adjustment, and restore().

The lost mission (id 3): the human (pilot 1, slot 0) dropped napalm and the
debrief books MilitaryFacility/Building=90 for one destroyed box; his AI
wingman (pilot 2) shot down nothing. Pilot and squadron totals were updated
by the game as usual, so the 90 sits in the totals but in no sortie row.
"""

import pytest

from korea_service_record import napalmfix, recovery

HUMAN = "a1b2c3d4-1111-4222-8333-944445555666"
AI2 = "00000000-0000-0000-0000-200000000000"
PLAYERS = ("personageId,pointsSumByMission,killBuilding,killMilitaryFacility,killRaildoad,"
           "assistCount,friendlyKillCount,totalFlightTime,ejectStatus,planeStatus")


def _result(rows, extra=""):
    return f"missionDuration=3600&players={PLAYERS}|" + "|".join(rows) + extra


LOST_RESULT = _result([f"{HUMAN},18,90,90,0,1,0,3540,0,0",
                       f"{AI2},2,0,0,0,0,0,3600,0,0"])
PILOTS_LIST = ("ammoCost,fuel,fuelCost,guns,payloadId,pilotId,planeId"
               "|10,0.5,20,x,3,1,201|10,0.5,20,x,1,2,202")


@pytest.fixture
def lost_career(career):
    c = career
    c.squadron("Building=92&MilitaryFacility=92")
    c.pilot(1, "Building=92&MilitaryFacility=92", score=40, pcp=60.0, is_player=1, rank=3)
    c.pilot(2, "", score=2, pcp=2.0, rank=1)
    # Mission 1: a normal one with rows.
    c.mission(1, start="1951.05.01 08:00:00", end="1951.05.01 09:00:00")
    c.sortie(1, 1, "Building=2&MilitaryFacility=2", sid=1, date="1951.05.01 08:00:00")
    c.kills(1, 1, "Mil_boxes_02", "Mil_tent_01")
    # Mission 3: lost its rows.
    c.mission(3, start="1951.05.03 08:00:00", end="1951.05.03 09:00:00",
              result=LOST_RESULT, pilots_list=PILOTS_LIST)
    c.kills(3, 1, "Mil_boxes_02")
    # Promoted once since (type 19, ipar3=1): rank on the day was 2.
    c.run("INSERT INTO event (date, type, pilotId, missionId, ipar3) "
          "VALUES ('1951.05.10 12:00:00', 19, 1, 0, 1)")
    # The pilot's flags on that mission (type 35).
    c.run("INSERT INTO event (date, type, pilotId, missionId, ipar1) "
          "VALUES ('1951.05.03 09:00:00', 35, 1, 3, 7)")
    return c


def _name(c):
    return c.path.stem


# -- detection and rebuild ----------------------------------------------------

def test_only_the_mission_without_rows_is_lost(lost_career):
    assert list(recovery.plan(lost_career.path)) == [3]


def test_rebuilt_rows(lost_career):
    rows = recovery.plan(lost_career.path)[3]
    human, wingman = rows
    assert human["pilotId"] == 1 and human["planeId"] == 201 and human["isPlayer"] == 1
    assert human["killStats"] == "Building=90&MilitaryFacility=90"      # zeros dropped
    assert human["score"] == 18 and human["assistCount"] == 1 and human["flightTime"] == 3540
    assert human["rankId"] == 2
    assert human["eventFlags"] == 7
    assert human["date"] == "1951.05.03 08:00:00"
    assert (human["status"], human["health"], human["planeStatus"], human["planeHealth"]) == (0, 100, 0, 100)
    assert wingman["pilotId"] == 2 and wingman["isPlayer"] == 0 and wingman["killStats"] == ""
    assert wingman["rankId"] == 1


def test_kill_keys_keep_the_raildoad_typo():
    assert recovery._kills({"killRaildoad": "2", "killTrainVagon": "2", "killAircraft": "0"}) \
        == "Raildoad=2&TrainVagon=2"


def test_killed_pilot_and_lost_plane(lost_career):
    lost_career.run("INSERT INTO event (date, type, pilotId, missionId, ipar2) "
                    "VALUES ('1951.05.03 08:40:00', 3, 1, 3, 0)")
    lost_career.run("INSERT INTO event (date, type, pilotId, missionId, ipar2) "
                    "VALUES ('1951.05.03 08:40:00', 2, 1, 3, 0)")
    human = recovery.plan(lost_career.path)[3][0]
    assert (human["status"], human["health"], human["planeStatus"], human["planeHealth"]) == (2, 0, 3, 0)


def test_mission_that_lost_only_some_rows_is_not_detected(lost_career):
    """By design (finding L2): any row at all means the mission is not lost."""
    lost_career.sortie(3, 2, "", sid=50, date="1951.05.03 08:00:00")
    assert recovery.plan(lost_career.path) == {}


def test_missing_pilot_row_gets_rank_zero(lost_career):
    lost_career.run("DELETE FROM pilot WHERE id = 2")
    wingman = recovery.plan(lost_career.path)[3][1]
    assert wingman["pilotId"] == 2 and wingman["rankId"] == 0


# -- apply ------------------------------------------------------------------------

def test_apply_inserts_the_rows_and_records_them(lost_career, tmp_path):
    result = recovery.auto_sync(lost_career.path)
    assert result == {"missions": 1, "sorties": 2}
    rows = lost_career.all("SELECT * FROM sortie WHERE missionId = 3 ORDER BY id")
    assert [r["pilotId"] for r in rows] == [1, 2]
    assert rows[0]["killStats"] == "Building=90&MilitaryFacility=90"
    assert rows[0]["isDeleted"] == 0 and rows[0]["insDate"]
    record = recovery.load(_name(lost_career))
    assert record["auto"] is True
    assert record["missions"]["3"]["sorties"] == [r["id"] for r in rows]
    assert record["missions"]["3"]["kills"] == {"1": "Building=90&MilitaryFacility=90", "2": ""}
    assert len(list((tmp_path / "backups").glob("*.career-backup"))) == 1
    # Nothing left to do on the next read.
    assert recovery.auto_sync(lost_career.path) is None


def test_apply_lowers_the_napalm_offsets_by_the_restored_kills(lost_career, game_dir):
    c = lost_career
    # A napalm record exists from before: offsets taken while the 90 was in
    # the totals but in no row.
    napalmfix.save(_name(c), {**napalmfix._empty(_name(c)), "auto": True,
                              "pilots": {"1": {"Building": 90, "MilitaryFacility": 90}},
                              "gaps": {"1": 20.0},
                              "squadron": {"Building": 90, "MilitaryFacility": 90}})
    recovery.auto_sync(c.path)
    napalm = napalmfix.load(_name(c))
    assert napalm["pilots"]["1"] == {"Building": 0, "MilitaryFacility": 0}
    assert napalm["squadron"] == {"Building": 0, "MilitaryFacility": 0}

    # The napalm run then corrects the restored row like any other.
    napalmfix.auto_sync(c.path, game_dir)
    restored = c.all("SELECT id, killStats FROM sortie WHERE missionId = 3 AND pilotId = 1")[0]
    assert restored["killStats"] == "Building=1&MilitaryFacility=1"
    assert c.pilot_row(1)[0] == "Building=3&MilitaryFacility=3"
    assert c.squadron_kills() == "Building=3&MilitaryFacility=3"


def test_recovery_then_first_napalm_run_without_a_record(lost_career, game_dir):
    """No napalm record yet: the napalm run takes its offsets after the rows
    are back, so they come out at zero."""
    c = lost_career
    recovery.auto_sync(c.path)
    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[0] == "Building=3&MilitaryFacility=3"
    assert napalmfix.load(_name(c))["pilots"]["1"] == {"Building": 0, "MilitaryFacility": 0}


def test_recovery_with_a_locked_file_writes_nothing(lost_career):
    import sqlite3
    holder = sqlite3.connect(lost_career.path)
    holder.execute("BEGIN IMMEDIATE")
    try:
        assert recovery.auto_sync(lost_career.path) is None
    finally:
        holder.rollback()
        holder.close()
    assert lost_career.all("SELECT id FROM sortie WHERE missionId = 3") == []
    assert recovery.load(_name(lost_career)) is None


# -- restore ----------------------------------------------------------------------

def test_restore_deletes_the_rows_and_puts_the_offsets_back(lost_career, game_dir):
    c = lost_career
    napalmfix.save(_name(c), {**napalmfix._empty(_name(c)), "auto": True,
                              "pilots": {"1": {"Building": 90, "MilitaryFacility": 90}},
                              "gaps": {"1": 20.0},
                              "squadron": {"Building": 90, "MilitaryFacility": 90}})
    recovery.auto_sync(c.path)
    napalmfix.auto_sync(c.path, game_dir)
    restored_ids = recovery.load(_name(c))["missions"]["3"]["sorties"]
    assert any(str(i) in napalmfix.load(_name(c))["sorties"] for i in restored_ids)

    assert recovery.restore(c.path) == 2
    assert c.all("SELECT id FROM sortie WHERE missionId = 3") == []
    napalm = napalmfix.load(_name(c))
    assert napalm["pilots"]["1"] == {"Building": 90, "MilitaryFacility": 90}
    assert napalm["squadron"] == {"Building": 90, "MilitaryFacility": 90}
    assert not any(str(i) in napalm["sorties"] for i in restored_ids)
    record = recovery.load(_name(c))
    assert record["auto"] is False and record["missions"] == {}
    # The automatic run stays off: the mission is lost again, and left so.
    assert recovery.auto_sync(c.path) is None
    # And the napalm run puts the totals back on the old footing.
    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[0] == "Building=92&MilitaryFacility=92"


def test_restore_without_a_record(lost_career):
    assert recovery.restore(lost_career.path) == 0


# -- known gaps (findings) ------------------------------------------------------

def test_mission_rebuilding_to_nothing_is_not_retried_forever(career, tmp_path):
    career.pilot(1, "", is_player=1)
    # A debrief with a players header but no rows: rebuild() returns [].
    career.mission(5, result="missionDuration=10&players=" + PLAYERS, pilots_list=PILOTS_LIST)
    for _ in range(3):
        recovery.auto_sync(career.path)
    assert len(list((tmp_path / "backups").glob("*.career-backup"))) <= 1


def test_backup_put_back_switches_recovery_off_and_returns_the_offsets(lost_career):
    c = lost_career
    napalmfix.save(_name(c), {**napalmfix._empty(_name(c)), "auto": True,
                              "pilots": {"1": {"Building": 90, "MilitaryFacility": 90}},
                              "gaps": {"1": 20.0},
                              "squadron": {"Building": 90, "MilitaryFacility": 90}})
    before = c.path.read_bytes()
    recovery.auto_sync(c.path)
    assert c.all("SELECT id FROM sortie WHERE missionId = 3") != []
    # The player puts the pre-recovery file back.
    c.path.write_bytes(before)
    assert recovery.auto_sync(c.path) is None
    assert c.all("SELECT id FROM sortie WHERE missionId = 3") == []     # not redone
    assert recovery.load(_name(c))["auto"] is False
    napalm = napalmfix.load(_name(c))
    assert napalm["pilots"]["1"] == {"Building": 90, "MilitaryFacility": 90}
    assert napalm["squadron"] == {"Building": 90, "MilitaryFacility": 90}
