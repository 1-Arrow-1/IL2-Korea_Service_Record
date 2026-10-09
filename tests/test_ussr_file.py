import io
import json
import re
from pathlib import Path

from PIL import Image

from korea_service_record import russian as ru
from korea_service_record import ussr_file as uf

LANGS = ("en", "de", "es", "fr", "ru", "zh")


def test_names_decline():
    assert ru.full_name("Дунаев", "Святослав", "Игоревич", "gen") == "Дунаева Святослава Игоревича"
    assert ru.full_name("Дунаев", "Святослав", "Игоревич", "dat") == "Дунаеву Святославу Игоревичу"
    assert ru.full_name("Луковский", "Никита", "Андреевич", "dat") == "Луковскому Никите Андреевичу"
    assert ru.full_name("Ермаков", "Фома", "Ильич", "gen") == "Ермакова Фомы Ильича"
    assert ru.surname("Кабиски", "dat") == "Кабиски"           # does not decline
    assert ru.first_name("Виталий", "dat") == "Виталию" and ru.first_name("Игорь", "gen") == "Игоря"


def test_plural_after_a_number():
    forms = ("вылет", "вылета", "вылетов")
    assert [ru.plural(n, *forms) for n in (1, 3, 5, 11, 21, 22, 112)] == [
        "вылет", "вылета", "вылетов", "вылетов", "вылет", "вылета", "вылетов"]


def test_officials_by_date():
    assert uf.presidium("1952.12.31")[1] == "А. Горкин"
    assert uf.presidium("1953.03.15")[0] == "К. Ворошилов"
    assert uf.corps_commander("1951.09.17")[0].endswith("И. Белов")
    assert uf.corps_commander("1951.09.18")[0].endswith("Г. Лобов")
    assert uf.corps_commander("1952.08.26")[0].endswith("С. Слюсарев")
    assert uf.promotion_order(2, "1951.06.01")["key"] == "order_af"
    assert uf.promotion_order(3, "1953.03.20")["key"] == "order_defence"


def test_order_numbers_rise_with_the_date_and_stay_put():
    early = int(uf.order_number("red_star", "1950.12.01", "x"))
    late = int(uf.order_number("red_star", "1953.06.01", "x"))
    assert 2_830_000 <= early < late <= 3_250_000
    assert uf.order_number("red_star", "1951.05.01", "x") == uf.order_number("red_star", "1951.05.01", "x")
    assert uf.order_number(None, "1951.05.01") == "б/н"


def test_units_and_patronymics():
    assert uf.unit(501176)["short"] == "176 гв. иап, 324 иад"
    assert uf.unit(501351)["short"] == "351 ониап"
    assert uf.patronymic("501003", "x") == "Игоревич"
    assert uf.patronymic("501005", "Ivan Petrov") in uf.COMMON_PATRONYMICS


def test_tooltips_exist_in_six_languages():
    files = {lang: json.loads((uf.TIPS / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGS}
    keys = set(files["en"])
    for lang, d in files.items():
        assert set(d) == keys, lang
        for k, v in d.items():
            assert set(re.findall(r"\{\w+\}", v)) == set(re.findall(r"\{\w+\}", files["en"][k])), (lang, k)
    source = Path(uf.__file__).read_text(encoding="utf-8")
    used = {k for k in re.findall(r'(?:_t|tip)\(lang, "(\w+)"', source) if not k.endswith("_")}
    used |= {p[3] for p in uf.POSTS} | {f"att_{k}_{i}" for k in ("skill", "courage", "discipline") for i in range(4)}
    used |= {"order_af", "order_war", "order_defence", "order_council"} | set(uf.PAGE_RU)
    assert used <= keys, used - keys


class _NoNames:
    def read_text(self, path):
        return None


def _basics():
    return {"first_name": "Svyatoslav", "last_name": "Dunaev", "country": 501, "rank_id": 4, "lead_level": 0x232,
            "unit_code": 501176, "bio_id": "501003", "birth_date": "1922.03.14",
            "awards": [{"type": 501004, "earned": "1951.04.02", "received": "1951.04.02", "rank_id": 3, "name": "x"},
                       {"type": 501006, "earned": "1951.04.23", "received": "1951.04.23", "rank_id": 3, "name": "x"},
                       {"type": 501022, "earned": "1951.07.09", "received": "1951.07.09", "rank_id": 4, "name": "x"}]}


def test_the_file_and_its_documents():
    detail = {"start_date": "1951.04.02", "current_date": "1951.07.10",
              "promotions": [{"rank_id": 4, "date": "1951.06.20", "rank": "Подполковник"}],
              "player": {"sorties": 21, "flight_hours": 18.5, "airborne": 22, "ground_targets": 3}}
    doc = uf.assemble(_basics(), detail, detail, {}, "en", _NoNames(), (2, 3, 2))
    assert [e["number"] for e in doc["book"]["entries"]][0] == "б/н"
    assert doc["extracts"][0]["text"].startswith("Присвоить воинское звание «подполковник» майору")
    assert "21 боевой вылет" in doc["attestation"]["lines"][-1]["ru"]
    assert doc["attestation"]["conclusion"]["ru"].endswith("на должность командира полка.")
    assert doc["hero"]["chairman"] == "Н. Шверник"
    for data, path in ((uf.render_name(doc), uf.BOOK_NAME), (uf.render_awards(doc), uf.BOOK_AWARDS),
                       (uf.render_hero(doc), uf.HERO_TEMPLATE)):
        assert Image.open(io.BytesIO(data)).size == uf.size_of(path)
