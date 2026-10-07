from korea_service_record.career.aggregator import CareerAggregator


class _Database:
    """Two flying days in a ten-day career; one planned mission not yet flown."""

    def query(self, sql, *args):
        if "FROM mission" in sql:
            return [
                {"id": 1, "date": "1951.07.01", "assignedFuel": 4000, "assignedAmmo": 300},
                {"id": 2, "date": "1951.07.01", "assignedFuel": 2000, "assignedAmmo": 100},
                {"id": 3, "date": "1951.07.05", "assignedFuel": 2000, "assignedAmmo": 200},
            ]
        if "FROM event WHERE type=18" in sql:
            # repairs started: 44 % airworthy (3 units), 95 % (1 unit)
            return [{"date": "1951.07.01 09:00:00", "ipar2": 44},
                    {"date": "1951.07.05 10:00:00", "ipar2": 95}]
        if "FROM event" in sql:
            return [{"date": "1951.07.01 07:00:00", "ipar1": 7},
                    {"date": "1951.07.05 08:00:00", "ipar1": 5}]
        if "FROM supply" in sql:
            return [{"type": 3, "quantity": 40000, "cost": 10},
                    {"type": 4, "quantity": 2000, "cost": 10},
                    {"type": 5, "quantity": 100, "cost": 10},
                    {"type": 9, "quantity": 1, "cost": 1}]          # unknown kind: ignored
        if "FROM pilot" in sql:
            return [{"n": 1}]
        raise AssertionError(sql)


def test_consumption_per_flying_day_and_forecast():
    agg = object.__new__(CareerAggregator)
    s = agg._logistics(_Database(), {"currentDate": "1951.07.10"},
                       {"fuelQty": 30000, "ammoQty": 1000, "partsQty": 50}, written_off=2)

    assert (s["span_days"], s["flying_days"], s["flying_rate"]) == (10, 2, 0.2)
    pd = s["per_flying_day"]
    assert pd["fuel"]["mean"] == 4000 and pd["ordnance"]["mean"] == 300
    assert pd["missions"]["mean"] == 1.5 and pd["requests"]["mean"] == 6

    week = s["horizons"][0]                      # 7 days at 20 % = 1.4 flying days
    assert week["days"] == 7 and week["flying_days"] == 1.4
    assert week["fuel"] == 5600 and week["fuel_left"] == 30000 - 5600
    assert week["fuel_low"] <= week["fuel"] <= week["fuel_high"]
    # 30000 L at 4000 per flying day and one flying day in five
    assert s["lasts"]["fuel"] == 38
    assert s["delivered"]["fuel"]["per_point"] == 4000
    assert set(s["delivered"]) == {"fuel", "ordnance", "equipment"}
    # equipment estimated from the repairs: 3 + 1 units over two flying days
    assert pd["equipment"]["mean"] == 2
    assert s["source"] == {"fuel": "booked", "ordnance": "booked", "equipment": "estimated"}
    assert s["losses_per_month"] == {"aircraft": 6.0, "pilots": 3.0}


def test_no_flown_mission_gives_no_statistics():
    class Empty(_Database):
        def query(self, sql, *args):
            return [] if "FROM mission" in sql else super().query(sql)
    agg = object.__new__(CareerAggregator)
    assert agg._logistics(Empty(), {"currentDate": "1951.07.10"}, {}, 0) is None
