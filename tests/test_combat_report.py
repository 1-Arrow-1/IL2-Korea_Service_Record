import struct

from korea_service_record.career.aggregator import CareerAggregator
from korea_service_record.flightlog import read_log


_HEADER = struct.Struct("<LBH")


def _string(value):
    raw = value.encode("ascii")
    return struct.pack("<L", len(raw)) + raw


def _record(tick, atype, payload):
    return _HEADER.pack(tick, atype, len(payload)) + payload + b"\n"


def _player_payload():
    return (
        struct.pack("<iiiiii", 100, 101, 1880, 0, 2, 6)
        + bytes(12)
        + _string("")
        + _string("")
        + _string("Test Pilot")
        + _string("P-51D-30NA")
        + _string("usa")
        + bytes(12)
        + struct.pack("<ii", 0, 1)
    )


def _object_payload(oid, kind, name=""):
    return struct.pack("<i", oid) + _string(kind) + _string("usa") + _string(name)


def _hit_payload(weapon, attacker, target):
    return _string(weapon) + struct.pack("<ii", attacker, target)


def _sample_log(path):
    records = [
        _record(0, 0, struct.pack("<LLLLLL", 1951, 6, 1, 8, 0, 0)),
        _record(10, 10, _player_payload()),
        _record(20, 12, _object_payload(200, "KS-12", "")),
        _record(5000, 1, _hit_payload("BULLET_12-7_USA_API", 100, 200)),
        _record(5500, 1, _hit_payload("NapalmBullet", 100, 200)),
        _record(5520, 1, _hit_payload("explosion", 100, 200)),
        _record(6000, 1, _hit_payload("RKT_HVAR5_HIT", 100, 200)),
        _record(7000, 1, _hit_payload("BULLET_12-7_USA_API", 999, 200)),
        _record(9000, 4, struct.pack("<iiiiii", 100, 101, 1264, 0, 0, 0)),
    ]
    path.write_bytes(b"".join(records))
    return read_log(path)


def test_binary_log_reads_ammunition_and_only_useful_player_impacts(tmp_path):
    flight = _sample_log(tmp_path / "mission.mlg")

    assert flight is not None
    assert flight.ammo_start == (1880, 0, 2, 6)
    assert flight.ammo_end == (1264, 0, 0, 0)
    assert [(hit.weapon, hit.target) for hit in flight.weapon_hits] == [
        ("BULLET_12-7_USA_API", "KS-12"),
        ("RKT_HVAR5_HIT", "KS-12"),
    ]
    assert len(flight.blast_effects) == 1
    assert flight.blast_effects[0]._asdict() == {
        "start_s": 110.0, "end_s": 110.4, "contacts": 2, "napalm": True}


class _Objects:
    def describe(self, internal):
        return {"named": bool(internal), "name": "85-mm KS-12 anti-aircraft gun"}


def test_gunnery_report_uses_start_end_counters_and_groups_impacts(tmp_path):
    flight = _sample_log(tmp_path / "mission.mlg")
    aggregator = object.__new__(CareerAggregator)
    aggregator.objects = _Objects()

    kills = [
        {"id": 1, "date": "1951.06.01 08:01:50", "tpar1": "KS-12"},
        # The canonical event id is counted once even if a caller repeats it.
        {"id": 1, "date": "1951.06.01 08:01:50", "tpar1": "KS-12"},
        {"id": 2, "date": "1951.06.01 08:01:51", "tpar1": "US6"},
    ]
    report = aggregator._gunnery(flight, "08:00", kills, corrected_targets=2)

    assert report["complete"] is True
    assert (report["gun_loaded"], report["gun_returned"], report["gun_fired"]) == (1880, 1264, 616)
    assert (report["gun_hits"], report["gun_rate"]) == (1, 0.2)
    assert (report["bombs_expended"], report["rockets_expended"], report["rocket_impacts"]) == (2, 6, 1)
    assert (report["bomb_hits"], report["bomb_targets"], report["bomb_rate"]) == (1, 2, 50.0)
    assert report["bomb_attacks"] == [{"time": "08:01:50", "targets": 2}]
    assert report["passes"] == [{
        "hits": 1,
        "targets": ["85-mm KS-12 anti-aircraft gun"],
        "time": "08:01:40",
    }]
    assert report["targets"] == [{"name": "85-mm KS-12 anti-aircraft gun", "hits": 2}]

    corrected = aggregator._gunnery(flight, "08:00", kills, corrected_targets=1)
    assert (corrected["bomb_hits"], corrected["bomb_targets"]) == (1, 1)
