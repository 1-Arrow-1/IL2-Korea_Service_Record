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
