from korea_service_record import stockhistory


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "assets"))
    return tmp_path / "career.db"


def reading(date, fuel, ordnance, equipment, d_fuel, d_ord, d_eq, last):
    return {"date": date, "last_mission": last,
            "stock": {"fuel": fuel, "ordnance": ordnance, "equipment": equipment},
            "delivered": {"fuel": d_fuel, "ordnance": d_ord, "equipment": d_eq}}


MISSIONS = [{"id": 1, "date": "1951.07.01"}, {"id": 2, "date": "1951.07.01"},
            {"id": 3, "date": "1951.07.03"}, {"id": 4, "date": "1951.07.05"}]


def test_consumption_is_deliveries_minus_the_change_in_stock(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    stockhistory.record(career, reading("1951.07.01", 1000, 100, 50, 0, 0, 0, 0))
    stockhistory.record(career, reading("1951.07.01", 1000, 100, 50, 0, 0, 0, 0))   # nothing new
    stockhistory.record(career, reading("1951.07.02", 700, 80, 48, 0, 0, 0, 2))
    # a delivery of 500 fuel arrived, and two more flying days were flown
    readings = stockhistory.record(career, reading("1951.07.05", 900, 60, 47, 500, 0, 0, 4))
    assert len(readings) == 3

    m = stockhistory.measured(readings, MISSIONS)
    assert m["flying_days"] == 3
    assert m["used"] == {"fuel": 300 + 300, "ordnance": 40, "equipment": 3}


def test_a_career_going_backwards_restarts_the_history(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    stockhistory.record(career, reading("1951.07.05", 900, 60, 47, 500, 0, 0, 4))
    readings = stockhistory.record(career, reading("1951.07.02", 700, 80, 48, 0, 0, 0, 2))
    assert len(readings) == 1
    assert stockhistory.measured(readings, MISSIONS) is None


def test_an_edited_stock_is_left_out(tmp_path, monkeypatch):
    career = _isolate(tmp_path, monkeypatch)
    stockhistory.record(career, reading("1951.07.01", 1000, 100, 50, 0, 0, 0, 0))
    # fuel went up with nothing delivered: someone edited the career
    readings = stockhistory.record(career, reading("1951.07.02", 5000, 80, 48, 0, 0, 0, 2))
    assert stockhistory.measured(readings, MISSIONS) is None
