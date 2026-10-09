import io
import json
import re
from pathlib import Path

from PIL import Image

from korea_service_record import dprk_file as df

LANGS = ("en", "de", "es", "fr", "ru", "zh")


def test_names_read_in_korean_as_the_north_reads_them():
    table = df._readings()
    assert table, "korean_readings.json is missing - run tools/make_korean_data.py"
    assert "".join(table[c] for c in "许一成") == "허일성"
    # the North keeps the initial ㄹ and ㄴ: 李 리, not 이
    if "李" in table:
        assert table["李"] == "리"


def test_numerals_and_dates_of_the_period():
    assert df.year_hanja(1951) == "一九五一"
    assert df.num_hanja(11) == "十一" and df.num_hanja(20) == "二十"
    assert df.date_hanja("1950.06.30") == "一九五〇년六월三十일"
    assert df.date_hangul("1951.04.02") == "1951년 4월 2일"


def test_units_ranks_and_booklets():
    assert df.unit(503058)["full"] == "조선인민군 공군 제58전투비행련대"
    assert df.unit(503057)["kind"] == "attack"
    assert df.rank(3) == "소좌"
    assert df.BOOKLET[503007] == ("flag", 1) and df.BOOKLET[503003] == ("soldier", 2)
    assert set(df.PROFILES) == {f"5030{n:02d}" for n in range(1, 15)}


def test_tooltips_exist_in_six_languages():
    files = {lang: json.loads((df.TIPS / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGS}
    keys = set(files["en"])
    for lang, d in files.items():
        assert set(d) == keys, lang
        for k, v in d.items():
            assert set(re.findall(r"\{\w+\}", v)) == set(re.findall(r"\{\w+\}", files["en"][k])), (lang, k)
    source = Path(df.__file__).read_text(encoding="utf-8")
    used = {k for k in re.findall(r'(?:_t|tip)\(lang, "(\w+)"', source) if not k.endswith("_")}
    used |= {p[1] for p in df.POSTS} | set(df.PAGE_KO)
    used |= {f"book_cover_{k}" for k in df.ORDERS} | {f"order_{k}" for k in df.ORDERS}
    used |= {"decree_flag", "decree_soldier_modelled", "decree_freedom_modelled", "unit_fighter", "unit_attack"}
    assert used <= keys, used - keys


class _NoNames:
    def read_text(self, path):
        return None


def test_the_booklets_and_the_hero_certificate():
    basics = {"first_name": "Il-seong", "last_name": "Her", "country": 503, "rank_id": 4, "unit_code": 503058,
              "bio_id": "503002", "birth_date": "1924.04.15",
              "awards": [{"type": 503003, "earned": "1951.04.23", "received": "1951.04.23", "name": "x"},
                         {"type": 503004, "earned": "1951.05.21", "received": "1951.05.21", "name": "x"},
                         {"type": 503007, "earned": "1951.06.11", "received": "1951.06.11", "name": "x"},
                         {"type": 503007, "earned": "1951.07.09", "received": "1951.07.09", "name": "x"}]}
    doc = df.assemble(basics, {}, {}, {}, "en", _NoNames())
    books = {b["key"]: b for b in doc["books"]}
    assert [e["cls"] for e in books["soldier"]["entries"]] == [2, 1]
    assert len(books["flag"]["entries"]) == 1             # a second Gold Star is not a second order
    assert [h["n"] for h in doc["heroes"]] == [1, 2]
    for data, size in ((df.render_name(doc), df.size_of(df.BOOK_NAME)),
                       (df.render_awards(doc, "soldier"), df.size_of(df.BOOK_AWARDS)),
                       (df.render_hero_certificate(doc, 2), (1000, 1400))):
        assert Image.open(io.BytesIO(data)).size == tuple(size)


def test_every_north_korean_biography_has_a_korean_version():
    import re
    for n in range(1, 15):
        bio_id = f"5030{n:02d}"
        paragraphs = df.korean_biography(bio_id)
        assert paragraphs, bio_id
        text = " ".join(paragraphs)
        assert not re.search(r"[A-Za-z]{3,}", re.sub(r"\$\[[^\]]*\]", "", text)), bio_id
        assert set(re.findall(r"\$\[(\w+)\]", text)) <= {"name", "firstName", "lastName", "birthDate", "startRank"}
