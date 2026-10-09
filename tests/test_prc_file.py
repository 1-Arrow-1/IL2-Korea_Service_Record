import io
import json
import re
from pathlib import Path

from PIL import Image

from korea_service_record import hanzi
from korea_service_record import prc_file as pf

LANGS = ("en", "de", "es", "fr", "ru", "zh")


def test_numbers_and_dates_as_written():
    assert [hanzi.number(n) for n in (3, 10, 12, 20, 41)] == ["三", "十", "十二", "二十", "四十一"]
    assert hanzi.year(1951) == "一九五一"
    assert hanzi.date("1951.11.09") == "一九五一年十一月九日"
    assert hanzi.date("1951.06.15", day=False) == "一九五一年六月"


def test_tooltip_dates_are_in_the_readers_language():
    assert pf.long_date("de", "1913.05.13") == "13. Mai 1913"
    assert pf.long_date("en", "1913.05.13") == "13 May 1913"


def test_names_keep_their_surnames():
    # The phrase converter would make 涂 into 塗 and 于 into 於.
    assert hanzi.name_to_trad("林涂") == "林涂"
    assert hanzi.name_to_trad("于俊峰") == "于俊峰"
    assert hanzi.name_to_trad("赵方") == "趙方"


def test_units_posts_and_approvers():
    assert pf.unit(502012)[0] == "空軍第四師第十二團"
    assert pf.post(0)[0] == "飛行員" and pf.post(3)[0] == "副大隊長" and pf.post(99)[0] == "副師長"
    assert pf.approver("third", 502012)[0] == "空軍第四師第十二團"
    assert pf.approver("second", 502012)[0] == "空軍第四師"
    assert pf.approver("first", 502012)[0] == "中國人民志願軍空軍"
    assert pf.approver("special", 502012)[0] == "中國人民解放軍空軍司令部"


def test_every_chinese_biography_has_a_profile():
    assert set(pf.PROFILES) == {f"5020{n:02d}" for n in range(1, 15)}
    for row in pf.PROFILES.values():
        assert row[4] in pf.FAMILY_ZH and row[5] in pf.STATUS_ZH


def test_tooltips_exist_in_six_languages():
    files = {lang: json.loads((pf.TIPS / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGS}
    keys = set(files["en"])
    for lang, d in files.items():
        assert set(d) == keys, lang
        for k, v in d.items():
            assert set(re.findall(r"\{\w+\}", v)) == set(re.findall(r"\{\w+\}", files["en"][k])), (lang, k)
    source = Path(pf.__file__).read_text(encoding="utf-8")
    # "grade_" + grade and the like are prefixes; their keys are listed below
    used = {k for k in re.findall(r'(?:_t|tip)\(lang, "(\w+)"', source) if not k.endswith("_")}
    used |= {"grade_" + g for g in pf.GRADE_ZH} | {"class_" + c for c in pf.HEROES.values()}
    used |= {k for _, k in pf.POSTS} | {"family_" + k for k in pf.FAMILY_ZH} | {"status_" + k for k in pf.STATUS_ZH}
    used |= set(pf.PAGE_ZH)
    assert used <= keys, used - keys


def _entry(award, earned, kills=None, kind=None):
    return {"type": award, "kind": kind or pf.kind_of(award), "earned": earned, "received": earned,
            "rank_id": 3, "rank_name": "Shaoxiao", "name": str(award), "kills": kills or {},
            "place": "安东", "hits": 0, "outcome": "ok", "flown": bool(kills)}


class _NoNames:
    def read_text(self, path):
        return None


def test_the_hero_title_goes_on_the_form_of_its_day():
    facts = {"name": "Lixin Song", "first_name": "Lixin", "last_name": "Song", "rank_id": 3, "unit_code": 502012,
             "bio_id": "502008", "birth_date": "1913.05.13",
             "entries": [_entry(502005, "1951.04.02", {"F-86A-5": 2}),
                         _entry(502015, "1951.05.21", {"F-86A-5": 4}),
                         _entry(502016, "1951.06.11", {"F-86A-5": 4}),
                         _entry(502021, "1951.06.11")]}
    doc = pf.assemble(facts, facts, "en", _NoNames())
    assert [f["n"] for f in doc["forms"]] == [1, 2, 3]
    assert doc["forms"][0]["deed"] == "一九五一年四月二日於安東上空與敵機空戰，擊落敵F-86型機二架。"
    assert doc["forms"][2]["deed"].endswith("同時被授予二等戰鬥英雄稱號。")
    assert "Combat Hero, Second Class" in doc["forms"][2]["tips"]["deed"]
    # Air Force headquarters certifies the highest First Class merit only
    assert [(c["type"], c["grade"]) for c in doc["certs"]] == [(502016, "first")]
    assert doc["profile"]["county"] == "武漢" and doc["profile"]["age"] == "三十七歲"
    assert [h["cls"] for h in doc["heroes"]] == ["second"]


def test_the_documents_render():
    facts = {"name": "Lixin Song", "first_name": "Lixin", "last_name": "Song", "rank_id": 3, "unit_code": 502012,
             "bio_id": "502008", "birth_date": "1913.05.13",
             "entries": [_entry(502005, "1951.04.02", {"F-86A-5": 2}), _entry(502006, "1951.04.09"),
                         _entry(502018, "1951.06.11", {"F-86A-5": 6})]}
    doc = pf.assemble(facts, facts, "en", _NoNames())
    for data, size in ((pf.render_spread(doc["profile"], doc["forms"][0]), (1536, 1024)),
                       (pf.render_form(doc["forms"][1]), (768, 1024)),
                       (pf.render_cert(doc["certs"][0]), pf.size_of(pf.AWARD_TEMPLATE))):
        assert Image.open(io.BytesIO(data)).size == tuple(size)
