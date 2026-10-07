from contextlib import nullcontext
from types import SimpleNamespace

from korea_service_record import progress
from korea_service_record.career.aggregator import CareerAggregator


class _Database:
    rows = [
        {"id": 1, "state": 0, "country": 601, "rankId": 1},   # active
        {"id": 2, "state": 2, "country": 601, "rankId": 1},   # killed
        {"id": 3, "state": 3, "country": 601, "rankId": 1},   # missing
        {"id": 4, "state": 4, "country": 601, "rankId": 7},   # in hospital, top rank
    ]

    def career(self):
        return {}

    def squadron(self):
        return {}

    def pilots(self):
        return self.rows


def test_every_pilot_but_the_killed_and_missing_gets_his_next_promotion(monkeypatch):
    agg = object.__new__(CareerAggregator)
    agg._career_files = lambda: {"career": SimpleNamespace(path="career.db")}
    agg._open = lambda _meta: nullcontext(_Database())
    monkeypatch.setattr(progress, "pilot_variables",
                        lambda pilot, career, squad: {"rankid": pilot["rankId"]})
    agg._next_promotion = lambda values, country: (
        None if values["rankid"] >= 7 else {"rank": "Captain", "ready": False, "bars": []})

    result = agg.squadron_promotions("career")

    assert set(result["pilots"]) == {"1", "4"}
    assert result["pilots"]["1"]["rank"] == "Captain"
    assert result["pilots"]["4"] is None          # no promotion left: "highest rank"
    assert agg.squadron_promotions("missing") is None
