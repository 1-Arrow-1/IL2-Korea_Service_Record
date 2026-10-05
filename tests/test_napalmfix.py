"""
napalmfix: plan, apply, auto_sync, restore - on a synthetic career.

The scenario (``napalm_career``):

* pilot 1, the player: sortie 1 clean (two MiGs), sortie 2 a napalm drop on
  an airfield that destroyed two tents/boxes and one parked La-11 but booked
  180 and 45. His stored total also carries Building/MilitaryFacility=2 from
  a sortie that has no row (the offset). score 100, pcp 150.
* pilot 2, AI: sortie 3 destroyed one box and booked 90. score 30, pcp 30.
* the squadron total is the sum plus 3 more of each building key (offset).

Hand-computed targets, from the points formula (Materiel+StaticPlane per 15,
Building per 5, airborne per 1):

* pilot 1 points: original 2 + (45//15) + (180//5) = 41; corrected 2.
  excess 39, pcp 100 + 50 - 39 = 111.
* pilot 2 points: original 90//5 = 18; corrected 0. pcp 30 + 0 - 18 = 12.
"""

import sqlite3
import threading

import pytest

from korea_service_record import napalmfix

from napalm_scenario import (P1_FIXED, P1_TOTAL, P2_FIXED, P2_TOTAL, S2_FIXED, S2_RAW,
                            S3_FIXED, S3_RAW, SQ_FIXED, SQ_TOTAL)


def _name(c):
    return c.path.stem


def _backups(tmp_path):
    return sorted((tmp_path / "backups").glob("*.career-backup")) if (tmp_path / "backups").is_dir() else []


# -- points ---------------------------------------------------------------------

def test_points_formula_carries_the_pots_across_sorties():
    # 10 + 10 vehicles: nothing on the first sortie, one point on the second.
    assert napalmfix.points(["Materiel=10"]) == 0
    assert napalmfix.points(["Materiel=10", "Materiel=10"]) == 1
    assert napalmfix.points(["Building=4", "Building=1"]) == 1
    assert napalmfix.points(["Ships=2"]) == 2
    assert napalmfix.points(["Aircraft=3&StaticPlane=1"]) == 2       # airborne only
    assert napalmfix.points(["StaticPlane=15"]) == 1                # parked count as vehicles


def test_points_reads_railroad_but_not_the_raildoad_typo():
    assert napalmfix.points(["Railroad=5"]) == 1
    assert napalmfix.points(["Raildoad=5"]) == 0


def test_points_on_empty_and_malformed():
    assert napalmfix.points([None, "", "garbage", "Building=x"]) == 0


def test_render_keeps_template_order_and_adds_new_keys_sorted():
    out = napalmfix._render("B=1&A=2&junk", {"A": 5, "B": 0, "Z": 1, "C": 3, "N": 0})
    assert out == "B=0&A=5&C=3&Z=1"


def test_render_clamps_negative_values_to_zero():
    assert napalmfix._render("A=1", {"A": -4}) == "A=0"


# -- a clean career ---------------------------------------------------------------

def test_clean_career_is_never_written_and_gets_no_record(career, game_dir, tmp_path):
    career.squadron("Aircraft=2&LightFighter=2")
    career.pilot(1, "Aircraft=2&LightFighter=2", score=2, pcp=2.0)
    career.mission(1)
    career.sortie(1, 1, "Aircraft=2&LightFighter=2", sid=1)
    career.kills(1, 1, "mig15bis", "mig15bis")
    before = career.path.read_bytes()
    assert napalmfix.auto_sync(career.path, game_dir) is None
    assert career.path.read_bytes() == before
    assert not napalmfix.path_for(_name(career)).exists()
    assert _backups(tmp_path) == []


def test_no_game_tables_means_no_correction(napalm_career, tmp_path):
    empty_game = tmp_path / "nogame"
    empty_game.mkdir()
    assert napalmfix.auto_sync(napalm_career.path, empty_game) is None
    assert napalm_career.sortie_kills(2) == S2_RAW


# -- apply ------------------------------------------------------------------------

def test_plan_reads_only(napalm_career, game_dir):
    before = napalm_career.path.read_bytes()
    p = napalmfix.plan(napalm_career.path, game_dir, napalmfix._empty("x"))
    assert napalm_career.path.read_bytes() == before
    assert {s["id"] for s in p["sorties"]} == {2, 3}
    assert napalmfix._pending(p)


def test_apply_writes_sorties_totals_and_pcp(napalm_career, game_dir, tmp_path):
    c = napalm_career
    counts = napalmfix.auto_sync(c.path, game_dir)
    assert counts == {"sorties": 2, "pilots": 2, "squadron": 1}

    assert c.sortie_kills(1) == "Aircraft=2&LightFighter=2"
    assert c.sortie_kills(2) == S2_FIXED
    assert c.sortie_kills(3) == S3_FIXED
    assert c.pilot_row(1) == (P1_FIXED, 111.0, 100)                 # score stays the game's
    assert c.pilot_row(2) == (P2_FIXED, 12.0, 30)
    assert c.squadron_kills() == SQ_FIXED

    record = napalmfix.load(_name(c))
    assert record["auto"] is True
    assert record["sorties"] == {"2": S2_RAW, "3": S3_RAW}
    assert record["pilots"]["1"]["Building"] == 2 and record["pilots"]["1"]["Aircraft"] == 0
    assert record["gaps"] == {"1": 50.0, "2": 0.0}
    assert record["pcp_state"] == {
        "1": {"score": 100.0, "pcp": 111.0, "excess": 39},
        "2": {"score": 30.0, "pcp": 12.0, "excess": 18},
    }
    assert record["squadron"]["MilitaryFacility"] == 5     # 3 + pilot 1's 2
    assert len(_backups(tmp_path)) == 1


def test_second_run_changes_nothing(napalm_career, game_dir, tmp_path):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    after_first = c.path.read_bytes()
    record_first = napalmfix.path_for(_name(c)).read_text(encoding="utf-8")

    assert napalmfix.auto_sync(c.path, game_dir) is None
    assert c.path.read_bytes() == after_first
    assert napalmfix.path_for(_name(c)).read_text(encoding="utf-8") == record_first
    assert len(_backups(tmp_path)) == 1


def test_manual_pcp_change_becomes_the_new_checkpoint(napalm_career, game_dir, tmp_path):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.run("UPDATE pilot SET pcp = 200 WHERE id = 1")

    # No new sortie or score: this is an independent edit, not another
    # napalm correction. It is recorded without touching or backing up the DB.
    assert napalmfix.auto_sync(c.path, game_dir) is None
    assert c.pilot_row(1)[1] == 200.0
    assert napalmfix.load(_name(c))["pcp_state"]["1"] == {
        "score": 100.0, "pcp": 200.0, "excess": 39,
    }
    assert len(_backups(tmp_path)) == 1


def test_manual_checkpoint_survives_game_raw_writeback(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.run("UPDATE pilot SET pcp = 200 WHERE id = 1")
    napalmfix.auto_sync(c.path, game_dir)

    # An ordinary mission follows while the game still holds its raw lifetime
    # PCP. The raw 151 must not erase the accepted +89 manual adjustment.
    c.mission(3)
    c.sortie(3, 1, "Aircraft=1&LightFighter=1", sid=4)
    c.kills(3, 1, "mig15bis")
    c.run("UPDATE pilot SET killStats = ?, score = 101, pcp = 151 WHERE id = 1",
          ("Aircraft=48&Building=182&LightFighter=3&MilitaryFacility=182&StaticPlane=45",))

    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[1:] == (201.0, 101)


def test_new_napalm_delta_is_applied_to_manual_checkpoint(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.run("UPDATE pilot SET pcp = 200 WHERE id = 1")
    napalmfix.auto_sync(c.path, game_dir)

    # The game gives 18 raw building points on a new inflated sortie. The
    # incremental correction removes those 18 from 218 and returns to the
    # accepted manual baseline, rather than rebuilding from score + old gap.
    c.mission(3)
    c.sortie(3, 1, S3_RAW, sid=4)
    c.kills(3, 1, "Mil_boxes_02")
    c.run("UPDATE pilot SET score = 118, pcp = 218 WHERE id = 1")

    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[1:] == (200.0, 118)
    assert napalmfix.load(_name(c))["pcp_state"]["1"]["excess"] == 57


def test_later_clean_sortie_can_release_a_carried_point(career, game_dir):
    c = career
    c.squadron("Building=5&MilitaryFacility=5")
    c.pilot(1, "Building=5&MilitaryFacility=5", score=1, pcp=1.0, is_player=1)
    c.mission(1)
    c.sortie(1, 1, "Building=5&MilitaryFacility=5", sid=1)
    c.kills(1, 1, "Mil_boxes_02")
    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[1] == 0.0

    # Four honest kills complete the corrected 1+4 group of five. Raw and
    # corrected cumulative point totals are now both one, so excess falls
    # from one to zero even though this sortie itself is clean.
    c.mission(2)
    c.sortie(2, 1, "Building=4&MilitaryFacility=4", sid=2)
    c.kills(2, 1, *("Mil_boxes_02",) * 4)
    c.run("UPDATE pilot SET killStats = 'Building=5&MilitaryFacility=5' WHERE id = 1")
    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[1:] == (1.0, 1)
    assert napalmfix.load(_name(c))["pcp_state"]["1"]["excess"] == 0


def test_format_one_record_migrates_without_losing_manual_pcp(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    record = napalmfix.load(_name(c))
    record["format"] = 1
    record.pop("pcp_state")
    napalmfix.save(_name(c), record)
    c.run("UPDATE pilot SET pcp = 200 WHERE id = 1")

    assert napalmfix.auto_sync(c.path, game_dir) is None
    migrated = napalmfix.load(_name(c))
    assert migrated["format"] == 2
    assert migrated["pcp_state"]["1"]["pcp"] == 200.0
    assert c.pilot_row(1)[1] == 200.0


def test_game_writing_its_own_values_back_is_corrected_again(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    # The game writes its in-memory (inflated) totals back over the file. It
    # never rewrites an old sortie row: on the 12th FBS career, after 84
    # corrected sorties, a new mission and a day rollover, the next run had
    # only the 4 new sorties to write (2026-10-02).
    c.run("UPDATE pilot SET killStats = ?, pcp = 150 WHERE id = 1", (P1_TOTAL,))
    c.run("UPDATE squadron SET killStats = ?", (SQ_TOTAL,))

    assert napalmfix.auto_sync(c.path, game_dir) is not None
    assert c.sortie_kills(2) == S2_FIXED
    assert c.pilot_row(1) == (P1_FIXED, 111.0, 100)
    assert c.squadron_kills() == SQ_FIXED


def test_new_mission_after_correction_lands_on_the_corrected_totals(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    # Next mission: one MiG. The game adds it to its own (inflated) memory
    # copy of the totals, and the points to score and pcp alike.
    c.mission(3)
    c.sortie(3, 1, "Aircraft=1&LightFighter=1", sid=4)
    c.kills(3, 1, "mig15bis")
    c.run("UPDATE pilot SET killStats = ?, score = 101, pcp = 151 WHERE id = 1",
          ("Aircraft=48&Building=182&LightFighter=3&MilitaryFacility=182&StaticPlane=45",))

    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1) == ("Aircraft=4&Building=4&LightFighter=3&MilitaryFacility=4&StaticPlane=1",
                              112.0, 101)


def test_new_napalm_sortie_for_a_pilot_already_in_the_record(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.mission(3)
    c.sortie(3, 2, S3_RAW, sid=4)
    c.kills(3, 2, "Mil_tent_01")
    c.run("UPDATE pilot SET killStats = ? WHERE id = 2",
          ("Building=91&MilitaryFacility=91",))     # the file's 1 + the game's 90
    napalmfix.auto_sync(c.path, game_dir)
    assert c.sortie_kills(4) == S3_FIXED
    assert c.pilot_row(2)[0] == "Building=2&MilitaryFacility=2"
    assert napalmfix.load(_name(c))["sorties"]["4"] == S3_RAW


# -- edge cases: missing rows -------------------------------------------------

def test_missing_squadron_row(career, game_dir):
    career.pilot(2, P2_TOTAL, score=30, pcp=30.0)
    career.mission(2)
    career.sortie(2, 2, S3_RAW, sid=3)
    career.kills(2, 2, "Mil_boxes_02")
    counts = napalmfix.auto_sync(career.path, game_dir)
    assert counts == {"sorties": 1, "pilots": 1, "squadron": 0}
    assert napalmfix.load(_name(career))["squadron"] is None


def test_sortie_of_a_pilot_without_a_row(career, game_dir):
    """A sortie whose pilot row is gone: the sortie and the squadron are
    corrected, the missing pilot is skipped and gets no offset."""
    career.squadron(S3_RAW)
    career.mission(2)
    career.sortie(2, 9, S3_RAW, sid=3)
    career.kills(2, 9, "Mil_boxes_02")
    counts = napalmfix.auto_sync(career.path, game_dir)
    assert counts == {"sorties": 1, "pilots": 0, "squadron": 1}
    assert career.squadron_kills() == S3_FIXED
    assert "9" not in napalmfix.load(_name(career))["pilots"]


def test_deleted_sortie_takes_its_whole_count_off_the_totals(napalm_career, game_dir):
    """Pins current behaviour (open question Q3): a corrected sortie later
    marked isDeleted drops out of 'offset + sum of sorties', so the pilot
    total loses its corrected kills too, not only the inflation. A pilot
    left with no live sortie at all is not rewritten."""
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.run("UPDATE sortie SET isDeleted = 1 WHERE id IN (2, 3)")
    napalmfix.auto_sync(c.path, game_dir)
    assert c.pilot_row(1)[0] == "Aircraft=2&Building=2&LightFighter=2&MilitaryFacility=2&StaticPlane=0"
    assert c.pilot_row(2)[0] == P2_FIXED


# -- the file in use ------------------------------------------------------------

def _hold(path, mode, started, release):
    con = sqlite3.connect(path, timeout=0)
    con.execute(f"BEGIN {mode}")
    con.execute("UPDATE squadron SET flightTime = flightTime")
    started.set()
    release.wait(10)
    con.rollback()
    con.close()


@pytest.fixture
def held(napalm_career):
    """Hold a write lock on the career file from another thread."""
    threads = []

    def hold(mode):
        started, release = threading.Event(), threading.Event()
        t = threading.Thread(target=_hold, args=(napalm_career.path, mode, started, release))
        t.start()
        started.wait(5)
        threads.append((t, release))
    yield hold
    for t, release in threads:
        release.set()
        t.join()


def test_exclusive_lock_reads_nothing_and_writes_nothing(napalm_career, game_dir, held, tmp_path):
    held("EXCLUSIVE")
    assert napalmfix.auto_sync(napalm_career.path, game_dir) is None
    assert _backups(tmp_path) == []
    assert not napalmfix.path_for(_name(napalm_career)).exists()


def test_write_lock_leaves_the_file_alone(napalm_career, game_dir, held):
    held("IMMEDIATE")
    before_rows = napalm_career.all("SELECT id, killStats FROM sortie ORDER BY id")
    assert napalmfix.auto_sync(napalm_career.path, game_dir) is None
    assert napalm_career.all("SELECT id, killStats FROM sortie ORDER BY id") == before_rows
    assert not napalmfix.path_for(_name(napalm_career)).exists()


def test_failed_attempt_on_a_locked_file_takes_no_backup(napalm_career, game_dir, held, tmp_path):
    held("IMMEDIATE")
    napalmfix.auto_sync(napalm_career.path, game_dir)
    napalmfix.auto_sync(napalm_career.path, game_dir)
    assert _backups(tmp_path) == []


# -- restore --------------------------------------------------------------------

def test_restore_puts_the_game_values_back_and_stops_the_run(napalm_career, game_dir, tmp_path):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    counts = napalmfix.restore(c.path)
    assert counts == {"sorties": 2, "pilots": 2, "squadron": 1}
    assert c.sortie_kills(2) == S2_RAW
    assert c.sortie_kills(3) == S3_RAW
    assert c.pilot_row(1) == (P1_TOTAL, 150.0, 100)
    assert c.pilot_row(2) == (P2_TOTAL, 30.0, 30)
    assert c.squadron_kills() == SQ_TOTAL
    assert napalmfix.load(_name(c))["auto"] is False
    # The automatic run stays off.
    assert napalmfix.auto_sync(c.path, game_dir) is None
    assert c.sortie_kills(2) == S2_RAW


def test_restore_twice_is_harmless(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    napalmfix.restore(c.path)
    snapshot = c.path.read_bytes()
    napalmfix.restore(c.path)
    assert c.pilot_row(1) == (P1_TOTAL, 150.0, 100)
    assert c.squadron_kills() == SQ_TOTAL
    assert len(c.path.read_bytes()) == len(snapshot)


def test_restore_without_a_record_does_nothing(napalm_career):
    assert napalmfix.restore(napalm_career.path) == {"sorties": 0, "pilots": 0, "squadron": 0}


def test_restore_after_the_game_added_a_mission(napalm_career, game_dir):
    """Totals come back as the game would have them: original + new."""
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.mission(3)
    c.sortie(3, 1, "Aircraft=1&LightFighter=1", sid=4)
    c.kills(3, 1, "mig15bis")
    c.run("UPDATE pilot SET score = 101, pcp = 112 WHERE id = 1")
    napalmfix.restore(c.path)
    assert c.pilot_row(1) == ("Aircraft=48&Building=182&LightFighter=3&MilitaryFacility=182&StaticPlane=45",
                              151.0, 101)


def test_restore_preserves_a_manual_pcp_adjustment(napalm_career, game_dir):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    c.run("UPDATE pilot SET pcp = 200 WHERE id = 1")
    napalmfix.auto_sync(c.path, game_dir)

    napalmfix.restore(c.path)
    assert c.pilot_row(1)[1] == 239.0       # manual 200 + the 39 returned raw points


def test_restore_rolls_back_entirely_when_the_file_is_locked(napalm_career, game_dir, held):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    held("IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError):
        napalmfix.restore(c.path)
    assert c.sortie_kills(2) == S2_FIXED
    assert napalmfix.load(_name(c))["auto"] is True


def test_originals_survive_a_failed_record_save(napalm_career, game_dir, monkeypatch):
    c = napalm_career
    real_save = napalmfix.save

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(napalmfix, "save", boom)
    with pytest.raises(OSError):
        napalmfix.auto_sync(c.path, game_dir)
    # Only save goes back: undo() would also lift the tmp record folder.
    monkeypatch.setattr(napalmfix, "save", real_save)
    # The file was corrected, but no record of the original values exists.
    napalmfix.restore(c.path)
    assert c.sortie_kills(2) == S2_RAW


def test_restore_sticks_even_if_the_record_save_fails(napalm_career, game_dir, monkeypatch):
    c = napalm_career
    napalmfix.auto_sync(c.path, game_dir)
    real_save = napalmfix.save

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(napalmfix, "save", boom)
    with pytest.raises(OSError):
        napalmfix.restore(c.path)
    monkeypatch.setattr(napalmfix, "save", real_save)
    # The record is saved before the commit, so a failed save aborts the
    # whole restore: the file keeps the corrected values, the record keeps
    # auto on, and nothing is half undone. The player can simply retry.
    assert c.sortie_kills(2) == S2_FIXED
    assert napalmfix.load(_name(c))["auto"] is True
    napalmfix.restore(c.path)
    assert c.sortie_kills(2) == S2_RAW


def test_unreadable_record_is_treated_as_none(napalm_career, game_dir, tmp_path):
    p = napalmfix.path_for(_name(napalm_career))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert napalmfix.load(_name(napalm_career)) is None
    assert napalmfix.restore(napalm_career.path) == {"sorties": 0, "pilots": 0, "squadron": 0}


# -- H1: a backup put back over the career file ------------------------------------

def test_backup_put_back_switches_the_correction_off(napalm_career, game_dir):
    c = napalm_career
    raw_before = c.path.read_bytes()
    napalmfix.auto_sync(c.path, game_dir)
    assert c.sortie_kills(2) == S2_FIXED
    # The player copies the pre-correction file back, as the forum post says.
    c.path.write_bytes(raw_before)
    assert napalmfix.auto_sync(c.path, game_dir) is None
    assert c.sortie_kills(2) == S2_RAW               # left as the player put it
    assert napalmfix.load(_name(c))["auto"] is False
    assert napalmfix.auto_sync(c.path, game_dir) is None
    assert c.sortie_kills(2) == S2_RAW
