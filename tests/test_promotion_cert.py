import pytest

from korea_service_record import promotion_cert as pc


def test_written_numbers():
    assert [pc.ordinal(n) for n in (1, 3, 12, 20, 23, 31, 75)] == [
        "first", "third", "twelfth", "twentieth", "twenty-third", "thirty-first", "seventy-fifth"]
    assert pc.words(51) == "fifty-one" and pc.words(50) == "fifty"


def test_the_year_of_independence_turns_over_on_the_fourth_of_july():
    assert pc.independence_year(1951, 7, 3) == 175
    assert pc.independence_year(1951, 7, 4) == 176


def test_fields_of_a_commission():
    f = pc.fields_for("Alex Bleiholder", "Lieutenant Colonel", (1951, 6, 20), (1951, 6, 23))
    assert f == {
        "name": "Alex Bleiholder",
        "rank": "Lieutenant Colonel, United States Air Force",
        "rank_day": "twentieth", "rank_month": "June", "rank_year": "fifty-one",
        "done_day": "twenty-third", "done_month": "June", "done_year": "fifty-one",
        "independence": "seventy-fifth",
    }


def test_navy_and_marine_commissions_name_the_correct_service():
    navy = pc.fields_for(
        "Edward Meyer", "Lieutenant Commander", (1951, 6, 20),
        (1951, 6, 23), country=602)
    marine = pc.fields_for(
        "John Smith", "Major", (1951, 6, 20),
        (1951, 6, 23), country=603)
    assert navy["rank"] == "Lieutenant Commander"
    assert marine["rank"] == "Major"


def test_signed_a_few_days_later_and_always_the_same_day():
    signed = pc.signing_date("Alex Bleiholder", (1951, 6, 20))
    assert signed == pc.signing_date("Alex Bleiholder", (1951, 6, 20))
    assert (1951, 6, 23) <= signed <= (1951, 7, 2)


def test_signers_are_the_men_in_office_that_day():
    assert pc.signers((1951, 6, 23)) == ("edwards", "finletter")
    assert pc.signers((1951, 11, 6)) == ("kuter", "finletter")
    assert pc.signers((1953, 3, 1)) == ("kuter", "talbott")
    assert pc.signers((1951, 6, 23), 602) == (None, "matthews")
    assert pc.signers((1952, 1, 1), 603) == (None, "kimball")


def test_a_certificate_renders():
    data = pc.render("Alex Bleiholder", "Brigadier General", (1952, 10, 3))
    assert data[:2] == b"\xff\xd8" and len(data) > 100_000


@pytest.mark.parametrize("country", [602, 603])
def test_navy_and_marine_certificates_render(country):
    data = pc.render(
        "Edward Meyer", "Lieutenant Commander", (1952, 1, 3), country=country)
    assert data[:2] == b"\xff\xd8" and len(data) > 100_000


def test_without_the_owners_font_the_bundled_open_font_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("WINDIR", str(tmp_path))
    path, size, subs = pc.font_choice()
    assert path == pc.FALLBACK_FONT and path.is_file() and size == 27
    assert subs == {"-": "\u2013"}
    assert pc.render("Alex Bleiholder", "Lieutenant Colonel", (1951, 6, 20))[:2] == b"\xff\xd8"


def test_the_owners_font_is_never_in_the_repository():
    folder = pc.STATIC / "certificates"
    assert not list(folder.glob("*BeneScriptine*"))
    assert (folder / "UnifrakturMaguntia-OFL.txt").is_file()


def test_navy_flight_codes_follow_the_classification_system():
    from korea_service_record.career.aggregator import MISSION_SYMBOL, NAVY_FLIGHT_CODE, navy_flight_code
    assert navy_flight_code(1201, 0.0) == "1T1"          # pre-assigned strike, day visual
    assert navy_flight_code(1101, 0.8) == "3X7"          # scramble, night visual
    assert navy_flight_code(1304, 0.0) == "1T2"          # close support, targets given airborne
    assert not [k for k in MISSION_SYMBOL if k not in NAVY_FLIGHT_CODE]
