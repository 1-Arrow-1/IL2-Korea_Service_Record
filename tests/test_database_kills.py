"""KoreaCareerDatabase with the napalm correction applied on read."""

from korea_service_record import napalmfix, progress
from korea_service_record.career.database import KoreaCareerDatabase

from napalm_scenario import (P1_FIXED, P1_TOTAL, P2_FIXED, S2_FIXED, S2_RAW, S3_FIXED,
                             SQ_FIXED, SQ_TOTAL)


def _db(career, table):
    db = KoreaCareerDatabase(career.path)
    db.set_kill_categories(table)
    return db


def test_rows_come_back_corrected_with_the_raw_value_kept(napalm_career, table):
    with _db(napalm_career, table) as db:
        sorties = {s["id"]: s for s in db.sorties()}
        assert sorties[1]["killStats"] == "Aircraft=2&LightFighter=2"
        assert "_killStats_raw" not in sorties[1]
        assert sorties[2]["killStats"] == S2_FIXED
        assert sorties[2]["_killStats_raw"] == S2_RAW
        assert sorties[3]["killStats"] == S3_FIXED

        assert db.pilot(1)["killStats"] == P1_FIXED
        assert db.pilot(1)["_killStats_raw"] == P1_TOTAL
        assert db.pilot(2)["killStats"] == P2_FIXED
        squadron = db.squadron()
        assert squadron["killStats"] == SQ_FIXED
        assert squadron["_killStats_raw"] == SQ_TOTAL


def test_kill_stats_helper_for_callers_with_their_own_sql(napalm_career, table):
    with _db(napalm_career, table) as db:
        assert db.kill_stats(2, S2_RAW) == S2_FIXED
        assert db.kill_stats(1, "Aircraft=2&LightFighter=2") == "Aircraft=2&LightFighter=2"
        assert db.kill_stats(999, "Building=3") == "Building=3"


def test_without_a_table_rows_are_untouched(napalm_career):
    with KoreaCareerDatabase(napalm_career.path) as db:
        assert db.kill_stats(2, S2_RAW) == S2_RAW
        assert {s["id"]: s["killStats"] for s in db.sorties()}[2] == S2_RAW
        assert db.pilot(1)["killStats"] == P1_TOTAL


def test_no_second_cut_once_the_file_is_corrected(napalm_career, table, game_dir):
    napalmfix.auto_sync(napalm_career.path, game_dir)
    with _db(napalm_career, table) as db:
        s2 = {s["id"]: s for s in db.sorties()}[2]
        assert s2["killStats"] == S2_FIXED
        assert "_killStats_raw" not in s2
        assert db.pilot(1)["killStats"] == P1_FIXED
        assert db.squadron()["killStats"] == SQ_FIXED


def test_award_progress_reads_the_raw_counter(napalm_career, table):
    with _db(napalm_career, table) as db:
        pilot, squadron = db.pilot(1), db.squadron()
    extra = {"country": 101, "sorties": 0, "goodSorties": 0, "efficiency": 0}
    pv = progress.pilot_variables({**extra, **pilot}, None)
    sv = progress.squadron_variables({**extra, **squadron}, None, 101)
    # BldObj counts the Building rollup: the game's 182, not the real 4.
    assert pv["bldobj"] == 182
    assert sv["bldobj"] == 275


def test_kill_rows_unreadable_means_no_cut(napalm_career, table):
    """query() returns [] on an error, so a missing event table gives the
    stored values, never a wrong cut."""
    napalm_career.run("DROP TABLE event")
    with _db(napalm_career, table) as db:
        assert {s["id"]: s["killStats"] for s in db.sorties()}[2] == S2_RAW
