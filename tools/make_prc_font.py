"""
Cut LXGW WenKai TC down to what the Chinese personnel file can write.

    python tools/make_prc_font.py <LXGWWenKaiTC-Regular.ttf>

The full face is 15 MB. The documents only ever hold the game's personal
names (characternames), its map places (the overlay's cities and airfields),
its aircraft designations (statnames), the fixed form
text in prc_file.py and numerals - all in traditional characters - so the
subset holds exactly those, plus ASCII for aircraft designations. Written to
static/images/certificates/LXGWWenKaiTC-PRC.ttf beside its licence (SIL OFL
1.1; the font has no Reserved Font Name, so a subset may keep it).

Re-run after a game update adds names or places.
"""

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fontTools import subset                                   # noqa: E402

from korea_service_record import hanzi, prc_file               # noqa: E402
from korea_service_record.assets import AssetResolver          # noqa: E402
from korea_service_record.gamedata import loads_lenient        # noqa: E402
from korea_service_record.geo import TILES                     # noqa: E402
from korea_service_record.locate import find_game_dir          # noqa: E402


def game_text(res: AssetResolver) -> str:
    out = []
    names = loads_lenient(res.read_text("nsdata/assets/locale/characternames.locale=chs.json") or "{}")
    out += [hanzi.name_to_trad(v) for v in names.values()]
    # The deed names the nearest town from the map overlay's own name
    # files, and the aircraft by the game's Chinese designations (雅克-9P).
    for path in (f"{TILES}/cities.locale=chs.json", f"{TILES}/airfields.locale=chs.json",
                 "nsdata/assets/locale/cities.locale=chs.json", "nsdata/assets/locale/airfields.locale=chs.json",
                 "nsdata/assets/worldobjects/statnames.locale=chs.json"):
        places = loads_lenient(res.read_text(path) or "{}")
        out += [hanzi.to_trad(v) for v in places.values() if isinstance(v, str)]
    return "".join(out)


def fixed_text() -> str:
    source = Path(prc_file.__file__).read_text(encoding="utf-8")
    return source + hanzi.DIGITS + "十百年月日歲壹貳參肆伍陸柒捌玖拾" + "。，、；：（）×·—"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    text = game_text(AssetResolver(game)) + fixed_text()
    chars = {c for c in text if ord(c) > 0x2E7F}
    chars |= {chr(c) for c in range(0x20, 0x7F)}
    out = prc_file.HAND_FONT
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    font = subset.load_font(str(src), options)
    sub = subset.Subsetter(options)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    subset.save_font(font, str(out), options)
    # What the face really holds (not what was asked for: it has no Hangul),
    # so prc_file.writable() can tell without fontTools at runtime.
    from fontTools.ttLib import TTFont
    held = sorted(chr(c) for c in TTFont(str(out)).getBestCmap())
    prc_file.HAND_CHARS.write_text("".join(held), encoding="utf-8")
    licence = src.with_name("OFL.txt")
    if licence.is_file():
        shutil.copyfile(licence, out.with_name("LXGWWenKaiTC-OFL.txt"))
    print(f"  {len(chars)} characters -> {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
