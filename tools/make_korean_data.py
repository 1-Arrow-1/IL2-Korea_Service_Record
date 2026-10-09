"""
Build what the North Korean personnel file needs and cannot take from the
game, which has no Korean language:

    python tools/make_korean_data.py <dir with NanumMyeongjo-Regular.ttf,
                                      NanumPenScript-Regular.ttf, OFL.txt>

1. korea_service_record/locales/dprk/korean_readings.json - the Korean reading of every
   Chinese character in the game's name table. The game writes North Korean
   names in Chinese characters in its Chinese locale (许一成); their Korean
   readings give the name in Hangul (허일성). The readings are the raw ones,
   without the South's initial-sound rule (李 리, 良 량), which is how the
   North writes them. From the `hanja` package's table (WTFPL; pip install
   hanja), traditional forms looked up through OpenCC.

2. Two Korean faces cut to the 2,350 Hangul syllables of KS X 1001, the
   characters the documents print, and ASCII:
       static/images/certificates/KoreaRecordPrint.ttf   from Nanum Myeongjo
       static/images/certificates/KoreaRecordHand.ttf    from Nanum Pen Script
   Both are SIL OFL 1.1 with "Nanum" as a Reserved Font Name, so the cut
   versions carry their own name; the licence goes beside them.

Re-run after a game update adds names.
"""

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.gamedata import loads_lenient      # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402

CERTS = REPO / "korea_service_record" / "static" / "images" / "certificates"
READINGS = REPO / "korea_service_record" / "locales" / "dprk" / "korean_readings.json"


def readings(res: AssetResolver) -> dict:
    from hanja.table import hanja_table
    from opencc import OpenCC
    cc = OpenCC("s2t")
    names = loads_lenient(res.read_text("nsdata/assets/locale/characternames.locale=chs.json") or "{}")
    out = {}
    for word in names.values():
        for ch in word:
            if ch in out:
                continue
            for form in (ch, cc.convert(ch)):
                if form in hanja_table:
                    out[ch] = hanja_table[form]
                    break
    return out


def ksx1001() -> str:
    """The 2,350 Hangul syllables of KS X 1001 (EUC-KR B0A1-C8FE)."""
    out = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                out.append(bytes([lead, trail]).decode("euc-kr"))
            except UnicodeDecodeError:
                pass
    return "".join(out)


def cut(src: Path, dst: Path, text: str, family: str) -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    font = subset.load_font(str(src), options)
    sub = subset.Subsetter(options)
    sub.populate(text=text)
    sub.subset(font)
    # A modified version may not use the Reserved Font Name.
    for rec in font["name"].names:
        if rec.nameID in (1, 3, 4, 6, 16, 21):
            value = family if rec.nameID in (1, 16, 21) else (
                family.replace(" ", "") + "-Regular" if rec.nameID == 6 else
                f"{family} Regular" if rec.nameID == 4 else f"{family};subset")
            rec.string = value
    subset.save_font(font, str(dst), options)
    print(f"  {dst.name}: {dst.stat().st_size // 1024} KB")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    table = readings(AssetResolver(game))
    READINGS.write_text(json.dumps(table, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"  {len(table)} readings -> {READINGS.name}")
    from korea_service_record import dprk_file
    fixed = Path(dprk_file.__file__).read_text(encoding="utf-8")
    text = ksx1001() + "".join(set(table.values())) + fixed + "".join(chr(c) for c in range(0x20, 0x7F))
    text += "一二三四五六七八九十〇年月日級『』「」、·…"
    cut(src / "NanumMyeongjo-Regular.ttf", CERTS / "KoreaRecordPrint.ttf", text, "Korea Record Print")
    cut(src / "NanumPenScript-Regular.ttf", CERTS / "KoreaRecordHand.ttf", text, "Korea Record Hand")
    shutil.copyfile(src / "OFL.txt", CERTS / "KoreaRecord-OFL.txt")
    # The two later orders' booklet covers, titled in the cover's gold. Set in
    # Malgun Gothic, which is on every Windows system; only the finished
    # pictures are shipped, never the face.
    for key in ("soldier", "freedom"):
        out = CERTS / f"dprk_order_book_cover_{key}.jpg"
        dprk_file.cover_with_title(dprk_file.ORDERS[key]["title"]).save(out, quality=92)
        print(f"  {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
