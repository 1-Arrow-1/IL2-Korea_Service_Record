"""killfix: the category table, reductions() and subtract()."""

from collections import Counter

import pytest

from korea_service_record.career.killfix import KillCategories, reductions, subtract


# -- the table ----------------------------------------------------------------

def test_table_maps_objects_to_bare_leaf_keys(table):
    assert table.category("Mil_boxes_02") == "MilitaryFacility"
    assert table.category("static_plane_la11") == "StaticPlane"     # case-insensitive
    assert table.rollup_of["MilitaryFacility"] == "Building"
    assert table.rollup_of["StaticPlane"] == "Aircraft"
    assert table.rollup_of["TrainLocomotive"] == "Railroad"


@pytest.mark.parametrize("name", ["61K-onTruck-attach", "61K-attach", "61K_npc"])
def test_table_strips_decorations(table, name):
    assert table.category(name) == "LightFlak"


@pytest.mark.parametrize("name", ["", None, "Windsock", "61K-something"])
def test_table_unknown_names(table, name):
    assert table.category(name) is None


def test_table_none_without_game_files():
    class Empty:
        def read_text(self, vpath):
            return None
    assert KillCategories.from_resolver(Empty()) is None


def test_table_none_when_statobjects_is_empty():
    class Blank:
        def read_text(self, vpath):
            return "{}"
    assert KillCategories.from_resolver(Blank()) is None


# -- reductions ---------------------------------------------------------------

def test_clean_sortie_is_not_reduced(table):
    raw = "Building=2&MilitaryFacility=2&Aircraft=1&StaticPlane=1"
    names = ["Mil_boxes_02", "Mil_tent_01", "Static_plane_La11"]
    assert reductions(raw, names, table) == Counter()


def test_inflated_sortie_is_cut_to_the_kill_rows(table):
    # Two parts destroyed, each re-killed by the fire: 90 booked per part.
    raw = "Aircraft=45&Building=135&MilitaryFacility=135&StaticPlane=45"
    names = ["Mil_boxes_02", "Mil_tent_01", "Static_plane_La11"]
    cut = reductions(raw, names, table)
    assert cut == Counter({"MilitaryFacility": 133, "Building": 133,
                           "StaticPlane": 44, "Aircraft": 44})
    assert subtract(raw, cut) == "Aircraft=1&Building=2&MilitaryFacility=2&StaticPlane=1"


def test_truck_mounted_gun_keeps_the_stored_value(table):
    # The gun on the truck has its own kill row, but the game counts it with
    # the truck: rebuilt LightFlak=1 against stored 0, Truck 1 against 1.
    raw = "Materiel=1&Truck=1"
    names = ["GAZ-AA", "61K-onTruck-attach"]
    assert reductions(raw, names, table) == Counter()


def test_rebuilt_more_than_stored_is_never_an_increase(table):
    raw = "LightFlak=1&Materiel=1"
    names = ["61K", "61K-onTruck-attach"]                # rebuilds LightFlak=2
    cut = reductions(raw, names, table)
    assert cut == Counter()
    assert subtract(raw, cut) == raw


def test_unknown_name_gives_one_of_slack_in_every_category(table):
    raw = "Building=5&MilitaryFacility=5&LightFlak=2&Materiel=2"
    names = ["Mil_boxes_02", "", "61K"]                   # one blank name
    cut = reductions(raw, names, table)
    # MilitaryFacility: 5 - (1 + 1 slack) = 3; LightFlak: 2 - (1 + 1) = 0.
    assert cut == Counter({"MilitaryFacility": 3, "Building": 3})


def test_sortie_without_kill_rows_is_left_alone(table):
    assert reductions("Building=90&MilitaryFacility=90", [], table) == Counter()


@pytest.mark.parametrize("raw", [None, "", "&", "garbage", "MilitaryFacility=",
                                 "MilitaryFacility=abc", "MilitaryFacility=1.5", "=3"])
def test_empty_or_malformed_killstats(table, raw):
    assert reductions(raw, ["Mil_boxes_02"], table) == Counter()


def test_rollups_and_unknown_keys_are_never_cut_on_their_own(table):
    # Building and Raildoad/Railroad are rollups; Ships is no leaf of the table.
    raw = "Building=50&Raildoad=9&Railroad=9&Ships=4"
    assert reductions(raw, ["Mil_boxes_02"], table) == Counter()


def test_rail_leaf_cut_is_charged_to_the_railroad_rollup(table):
    raw = "Raildoad=3&Railroad=2&TrainLocomotive=5"
    cut = reductions(raw, ["E_loco"], table)
    assert cut == Counter({"TrainLocomotive": 4, "Railroad": 4})
    # The cut is spent across both spellings, first one first.
    assert subtract(raw, cut) == "Raildoad=0&Railroad=1&TrainLocomotive=1"


def test_duplicate_leaf_key_is_reduced_twice(table):
    """Pins current behaviour (finding L4): a leaf key that appears twice is
    compared against the same rebuilt count both times."""
    raw = "MilitaryFacility=3&MilitaryFacility=3&Building=6"
    cut = reductions(raw, ["Mil_boxes_02"], table)
    assert cut["MilitaryFacility"] == 4


# -- subtract -----------------------------------------------------------------

def test_subtract_keeps_keys_order_and_untouched_pairs():
    raw = "Aircraft=3&Building=10&junk&MilitaryFacility=10&StaticPlane=3"
    out = subtract(raw, Counter({"Building": 4, "MilitaryFacility": 4}))
    assert out == "Aircraft=3&Building=6&junk&MilitaryFacility=6&StaticPlane=3"


def test_subtract_never_goes_below_zero():
    assert subtract("Building=2&MilitaryFacility=2",
                    Counter({"Building": 5, "MilitaryFacility": 5})) == "Building=0&MilitaryFacility=0"


def test_subtract_leaves_non_integers_alone():
    assert subtract("Building=x&MilitaryFacility=3",
                    Counter({"Building": 1, "MilitaryFacility": 1})) == "Building=x&MilitaryFacility=2"


@pytest.mark.parametrize("raw", [None, ""])
def test_subtract_on_nothing(raw):
    assert subtract(raw, Counter({"Building": 1})) == raw


def test_subtract_with_no_cut_returns_the_same_string():
    raw = "Building=2&MilitaryFacility=2"
    assert subtract(raw, Counter()) is raw
    assert subtract(raw, None) is raw


def test_reshaped_tables_turn_the_correction_off(tmp_path, monkeypatch):
    """L5: a game update reshaping either file must not crash the tracker."""
    from korea_service_record.assets import AssetResolver
    folder = tmp_path / "g" / "data" / "nsdata" / "assets" / "worldobjects"
    folder.mkdir(parents=True)
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "cache"))
    (folder / "statobjects.json").write_text('{"killX": {"objects": ["a"]}}', encoding="utf-8")
    for bad in ('[1, 2]', '{"internal": [1, 2]}', '{"internal": {"killBuilding": "abc"}}'):
        (folder / "statreporting.json").write_text(bad, encoding="utf-8")
        table = KillCategories.from_resolver(AssetResolver(tmp_path / "g"))
        assert table is None or isinstance(table.rollup_of, dict)
