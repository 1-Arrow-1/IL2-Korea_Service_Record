import json

from korea_service_record import custombio, wwii_awards


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "assets"))
    return tmp_path / "Alex Bleiholder, 12th FBS USAF.db"


def test_record_round_trips_and_belongs_to_one_pilot(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    path = custombio.save(career, 20, 601, "  First.\r\n\r\nSecond.  ", [601076])

    assert path.parent == tmp_path / "custom-biographies"
    own = custombio.load(career, 20)
    assert own["text"] == "First.\n\nSecond."
    assert own["wwii_awards"] == [601076]
    assert custombio.load(career, 21) is None

    custombio.clear(career)
    assert custombio.load(career, 20) is None


def test_none_keeps_the_game_text_and_the_inferred_medals(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    custombio.save(career, 20, 601, None, None)
    own = custombio.load(career, 20)
    assert own["text"] is None and own["wwii_awards"] is None

    custombio.save(career, 20, 601, "   ", [])
    own = custombio.load(career, 20)
    # A blank text is no text; an empty medal list is a choice: none.
    assert own["text"] is None and own["wwii_awards"] == []


def test_text_length_is_capped(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    try:
        custombio.save(career, 20, 601, "x" * (custombio.MAX_LENGTH + 1), None)
    except ValueError:
        pass
    else:
        raise AssertionError("an over-long biography was saved")


def test_a_damaged_record_is_ignored(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    path = custombio.state_path(career)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert custombio.load(career, 20) is None
    path.write_text(json.dumps({"pilot_id": 20, "text": 5, "wwii_awards": "x"}),
                    encoding="utf-8")
    assert custombio.load(career, 20) == {
        "pilot_id": 20, "country": None, "text": None,
        "wwii_awards": None, "updated": None}


def test_game_markup_becomes_editable_text_and_back():
    raw = "<p>$[name] was born.</p>\r\n <p>He &amp; his <em>wingman</em>.</p>"
    text = custombio.editable(raw)
    assert text == "$[name] was born.\n\nHe & his wingman."
    assert custombio.paragraphs(text) == ["$[name] was born.", "He & his wingman."]


def test_unknown_variables_are_reported_once_each():
    assert custombio.unknown_variables(
        "$[name] $[Name] $[nombre] $[Name] $[startRank]") == ["$[Name]", "$[nombre]"]


def test_chosen_medals_are_cleaned_per_nation():
    # one grade per family, in wearing order, only this nation's
    assert wwii_awards.chosen([601076, 601066, 601065, 501053, "x"], 601) == (601066, 601076)
    assert wwii_awards.chosen([501054, 501050], 501) == (501050, 501054)
    assert wwii_awards.chosen([601076], 502) == ()


def test_record_stores_only_valid_medals(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    custombio.save(career, 20, 501, None, [501053, 601076])
    assert custombio.load(career, 20)["wwii_awards"] == [501053]


INFO = {
    "601006": {"skill": 0, "discipline": 2, "courage": 2},
    "602006": {"copy": "601006"},
    "601999": {"skill": "x"},
}


def test_biography_points_follow_copy_entries():
    assert custombio.biography_points(INFO, "601006") == {"skill": 0, "courage": 2, "discipline": 2}
    assert custombio.biography_points(INFO, "602006") == {"skill": 0, "courage": 2, "discipline": 2}
    assert custombio.biography_points(INFO, "601901") is None
    assert custombio.biography_points(INFO, "601999") is None


def test_lead_level_unpacks_skill_courage_discipline():
    # Alex Bleiholder: 0x221 = skill 1 (earned), courage 2, discipline 2
    assert custombio.boosters(0x221) == {"skill": 1, "courage": 2, "discipline": 2}
    # Rivera, an AI pilot with a large skill booster
    assert custombio.boosters(0x22D) == {"skill": 13, "courage": 2, "discipline": 2}


def test_everything_is_shared_out_within_what_the_game_could_produce():
    # Alex: 3/1/1 (skill/courage/discipline) = biography 4 + one promotion point
    current = custombio.boosters(0x113)
    assert current == {"skill": 3, "courage": 1, "discipline": 1}
    assert custombio.booster_cap(4, current) == 4          # 3 + 1 promotion
    custombio.check_allocation({"skill": 2, "courage": 2, "discipline": 1}, 5, 4)
    assert custombio.repack(0x113, {"skill": 2, "courage": 2, "discipline": 1}) == 0x122
    # bits above the three boosters are left alone
    assert custombio.repack(0x5113, {"skill": 2, "courage": 2, "discipline": 1}) == 0x5122
    # never below what the pilot already has on one attribute
    assert custombio.booster_cap(4, {"skill": 4, "courage": 0, "discipline": 0}) == 4
    # and never above what a leadLevel nibble holds
    assert custombio.booster_cap(4, {"skill": 13, "courage": 2, "discipline": 2}) == 15


def test_allocation_must_share_out_the_total_within_the_cap():
    custombio.check_allocation({"skill": 2, "courage": 2, "discipline": 0}, 4, 3)
    for bad in ({"skill": 4, "courage": 0, "discipline": 0},
                {"skill": 1, "courage": 1, "discipline": 1},
                {"skill": 3, "courage": 2}):
        try:
            custombio.check_allocation(bad, 4, 3)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
