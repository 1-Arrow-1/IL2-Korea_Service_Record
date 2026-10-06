from contextlib import nullcontext
from types import SimpleNamespace

from korea_service_record import custombio
from korea_service_record.career.aggregator import (
    CareerAggregator,
    _biography_paragraphs,
)


def test_biography_markup_becomes_safe_plain_paragraphs():
    raw = (
        "<p>$[name] was born in Baton Rouge &amp; enlisted.</p>\r\n"
        "<p>He served with <em>distinction</em>.</p>"
    )
    assert _biography_paragraphs(raw) == [
        "$[name] was born in Baton Rouge & enlisted.",
        "He served with distinction.",
    ]


def test_plain_custom_biography_uses_blank_lines_as_paragraphs():
    assert _biography_paragraphs("First paragraph.\n\nSecond paragraph.") == [
        "First paragraph.",
        "Second paragraph.",
    ]


class _Resolver:
    def __init__(self):
        self.path = ""

    def read_text(self, path):
        self.path = path
        return (
            "<p>$[name] was born on $[birthDate].</p>"
            "<p>$[firstName] entered service as a $[startRank].</p>"
        )


class _Locale:
    def rank_name(self, country, rank_id):
        assert (country, rank_id) == (601, 1)
        return "First Lieutenant"


class _Database:
    pilot_row = {
        "id": 7,
        "name": "Alex",
        "lastName": "Bleiholder",
        "country": 601,
        "rankId": 4,
        "description": (
            "biographyId=601003&birthDate=1920%2e02%2e23"
        ),
    }

    def player(self):
        return self.pilot_row

    def pilot(self, pilot_id):
        return self.pilot_row if pilot_id == 7 else None

    def sorties(self, pilot_id):
        assert pilot_id == 7
        return [{"rankId": 1}]


def _aggregator(tmp_path, monkeypatch):
    # Own-biography records live beside the asset cache; keep them out of
    # the real %LOCALAPPDATA%.
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "assets"))
    agg = object.__new__(CareerAggregator)
    agg.lang = "eng"
    agg.locale = _Locale()
    agg.resolver = _Resolver()
    agg._career_files = lambda: {
        "career": SimpleNamespace(path=str(tmp_path / "career.db"))
    }
    agg._open = lambda _meta: nullcontext(_Database())
    return agg


def test_biography_reads_selected_game_template_and_starting_rank(tmp_path, monkeypatch):
    agg = _aggregator(tmp_path, monkeypatch)

    result = agg.biography("career", 7)

    assert agg.resolver.path.endswith(
        "bio.id=601003.locale=eng.txt"
    )
    assert result == {
        "career_id": "career",
        "biography_id": "601003",
        "custom": False,
        "source_language": "eng",
        "paragraphs": [
            "$[name] was born on $[birthDate].",
            "$[firstName] entered service as a $[startRank].",
        ],
        "pilot": {
            "id": 7,
            "name": "Alex Bleiholder",
            "first_name": "Alex",
            "last_name": "Bleiholder",
            "birth_date": "1920.02.23",
            "starting_rank": "First Lieutenant",
        },
    }


def test_own_biography_replaces_the_game_text_for_its_pilot_only(tmp_path, monkeypatch):
    agg = _aggregator(tmp_path, monkeypatch)
    custombio.save(tmp_path / "career.db", 7, 601,
                   "$[name] wrote this.\r\n\r\nSecond   line\nwraps.", None)

    result = agg.biography("career", 7)

    assert result["custom"] is True
    assert result["biography_id"] == "601003"          # the game's choice stays
    assert result["paragraphs"] == ["$[name] wrote this.", "Second line wraps."]

    custombio.save(tmp_path / "career.db", 8, 601, "A successor's text.", None)
    assert agg.biography("career", 7)["custom"] is False
