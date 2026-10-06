from contextlib import nullcontext
from types import SimpleNamespace

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


def test_biography_reads_selected_game_template_and_starting_rank():
    agg = object.__new__(CareerAggregator)
    agg.lang = "eng"
    agg.locale = _Locale()
    agg.resolver = _Resolver()
    agg._career_files = lambda: {
        "career": SimpleNamespace(path="career.db")
    }
    agg._open = lambda _meta: nullcontext(_Database())

    result = agg.biography("career", 7)

    assert agg.resolver.path.endswith(
        "bio.id=601003.locale=eng.txt"
    )
    assert result == {
        "career_id": "career",
        "biography_id": "601003",
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
