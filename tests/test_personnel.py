from contextlib import nullcontext

import pytest

from korea_service_record.app import create_app


class _Agg:
    """Just enough of the aggregator for the personnel endpoints."""

    def __init__(self, country=601):
        self.country = country

    def career_detail(self, career_id, pilot_id):
        if career_id != "career":
            return None
        return {
            "player": {"id": 20, "name": "Alex Bleiholder", "country": self.country,
                       "rank": "Lieutenant Colonel", "state": "active"},
            "squadron": "12th FBS USAF", "start_date": "1951.04.02", "current_date": "1951.07.10",
            "promotions": [{"date": "1951.06.20", "rank": "Lieutenant Colonel", "rank_id": 4, "pending": False},
                           {"date": "1951.07.20", "rank": "Colonel", "rank_id": 5, "pending": True}],
            "awards": [
                {"type": 601007, "name": "Silver OLC", "earned": "1951.04.17", "pending": False,
                 "history": [{"type": 601002, "earned": "1951.04.02", "name": "Air Medal"},
                             {"type": 601003, "earned": "1951.04.07", "name": "Bronze OLC"}]},
                {"type": 601039, "name": "UN Service Medal", "earned": "1951.05.06", "pending": False},
                {"type": 601018, "name": "Silver Star", "earned": "1951.07.09", "pending": True},
            ],
        }

    def biography(self, career_id, pilot_id):
        return None

    def award_name(self, award_id):
        return str(award_id)

    def citation(self, career_id, pilot_id, award_id, earned):
        return {"paragraphs": [f"Cited for {award_id}."]}


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    agg = _Agg()
    app.config["AGGREGATORS"] = {lang: agg for lang in ("en", "de", "es", "fr", "ru", "zh")}
    app.config["TESTING"] = True
    yield app.test_client(), agg


def test_one_entry_per_ladder_with_its_earlier_rungs(client):
    c, _ = client
    d = c.get("/api/personnel/career/20").get_json()
    assert [g["type"] for g in d["decorations"]] == [601007, 601039]     # pending left out
    assert [e["type"] for e in d["decorations"][0]["earlier"]] == [601002, 601003]
    assert d["decorations"][0]["earlier"][0]["citation"] == "Cited for 601002."
    assert d["grants_total"] == 4
    assert [p["rank_id"] for p in d["promotions"]] == [4]          # pending left out


def test_the_us_file_rejects_non_us_pilots(client):
    c, agg = client
    agg.country = 501
    assert c.get("/api/personnel/career/20").status_code == 404
    assert c.get("/api/promotion-certificate/career/20/4").status_code == 404


@pytest.mark.parametrize("country", [602, 603])
def test_navy_and_marine_files_use_the_us_document_path(client, country):
    c, agg = client
    agg.country = country
    assert c.get("/api/personnel/career/20").status_code == 200
    certificate = c.get("/api/promotion-certificate/career/20/4")
    assert certificate.status_code == 200
    assert certificate.mimetype == "image/jpeg"


def test_a_promotion_certificate_is_a_picture(client):
    c, _ = client
    r = c.get("/api/promotion-certificate/career/20/4")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert c.get("/api/promotion-certificate/career/20/5").status_code == 404     # pending
    assert c.get("/personnel").status_code == 200
