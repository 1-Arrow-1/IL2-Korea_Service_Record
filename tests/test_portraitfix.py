"""portraitfix: no avatarPath the game cannot hold (16-byte strcpy_s, 1.004b)."""
import sqlite3

from korea_service_record import portraitfix


def _career(path, avatar):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE pilot (id INTEGER PRIMARY KEY, avatarPath TEXT)")
    con.executemany("INSERT INTO pilot VALUES (?, ?)", [(1, "usa50e/8"), (20, avatar)])
    con.commit()
    con.close()


def _path(db, pid):
    con = sqlite3.connect(db)
    v = con.execute("SELECT avatarPath FROM pilot WHERE id=?", (pid,)).fetchone()[0]
    con.close()
    return v


def test_short_path_fits_the_game_buffer(tmp_path):
    p = portraitfix.short_avatar_path(tmp_path / "x.db", 20)
    assert p.startswith("cp/") and len(p) <= portraitfix.MAX_AVATAR_PATH


def test_long_custom_path_is_moved_with_its_portrait(tmp_path):
    db, game = tmp_path / "Pilot, 12th FBS.db", tmp_path / "game"
    old = "custom/ce037aaa5cebbef6-20"
    _career(db, old)
    src = portraitfix.photo_file(game, old)
    src.parent.mkdir(parents=True)
    src.write_bytes(b"DDS portrait")
    done = portraitfix.repair(db, game)
    new = _path(db, 20)
    assert done == [{"pilot": 20, "from": old, "to": new}]
    assert len(new) <= portraitfix.MAX_AVATAR_PATH
    assert portraitfix.photo_file(game, new).read_bytes() == b"DDS portrait"
    assert _path(db, 1) == "usa50e/8"
    assert portraitfix.repair(db, game) is None          # nothing left to do


def test_unknown_long_path_is_left_alone(tmp_path):
    db = tmp_path / "c.db"
    _career(db, "somethingelse/0123456789")
    assert portraitfix.repair(db, tmp_path / "game") is None
    assert _path(db, 20) == "somethingelse/0123456789"


def test_clean_career_is_not_touched(tmp_path):
    db = tmp_path / "c.db"
    _career(db, "usa50h/1")
    before = db.read_bytes()
    assert portraitfix.repair(db, tmp_path / "game") is None
    assert db.read_bytes() == before
    assert not list((tmp_path / "backups").glob("*"))

def test_a_custom_portrait_is_never_an_original():
    from korea_service_record.portraitfix import is_custom
    assert is_custom("custom/ce037aaa5cebbef6-20") and is_custom("cp/bbd9de0c48")
    assert not is_custom("usa50h/1") and not is_custom("")
