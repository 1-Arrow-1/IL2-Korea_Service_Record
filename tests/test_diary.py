from korea_service_record.diary import DiaryBuilder


class _Locale:
    def rank_name(self, country, rank_id):
        assert country == 601
        assert rank_id == 4
        return "Lieutenant Colonel"


class _Aggregator:
    locale = _Locale()

    def award_name(self, _award_id):
        raise AssertionError("promotion must use the destination rank name")


class _Database:
    def pilots(self, _include_all):
        return [{"id": 7, "name": "Test", "lastName": "Pilot"}]

    def player(self):
        return {"id": 7, "country": 601}


def _promotion(event_id, action, rank_id):
    return {
        "id": event_id,
        "type": 19,
        "date": "1951.04.01 12:00:00",
        "pilotId": 7,
        "missionId": -1,
        "ipar1": 1,
        "ipar2": 601983,
        "ipar3": action,
        "rankId": rank_id,
    }


def test_presented_promotion_uses_new_localized_rank_name():
    diary = DiaryBuilder(_Aggregator(), _Database())
    notes, _tally = diary._notes([
        _promotion(1, 0, 3),
        _promotion(2, 1, 4),
    ])

    assert notes == [{
        "key": "diary.own_promoted",
        "label": "You were promoted to Lieutenant Colonel",
        "rank": "Lieutenant Colonel",
    }]


def test_unapplied_promotion_uses_rank_after_granted_rows_old_rank():
    diary = DiaryBuilder(_Aggregator(), _Database())
    notes, _tally = diary._notes([_promotion(1, 0, 3)])

    assert notes == [{
        "key": "diary.own_promotion_granted",
        "label": "You earned promotion to Lieutenant Colonel",
        "rank": "Lieutenant Colonel",
    }]
