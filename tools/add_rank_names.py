"""
Name the flag-officer ranks in every language, for every ladder that has them.

    python tools/add_rank_names.py
    python tools/add_rank_names.py --dry-run

Without these the game draws its own missing-key marker — ``RANK6016!LOCALIZE!``
— which is how the new ranks were confirmed to work in the first place.

**Each language file has its own convention per country, and they disagree,
so the table below follows the file rather than any one rule.** Read from the
stock ranks.locale files:

    lang   501 USSR            502 PRC              503 DPRK
    eng    English             pinyin (Shàngxiào)   McCune-Reischauer (Sangjwa)
    ger    German              German (!)           German (!)
    fra    French              pinyin               McCune-Reischauer
    spa    transliterated      pinyin               McCune-Reischauer
           Russian (Polkovnik)
    rus    Russian             phonetic Russian     phonetic Russian
                               (Шенгсяо)            (Сангжва)
    chs    Chinese             Chinese              Chinese equivalent (上校)

German flattens all three communist ladders to Bundeswehr titles. That leaves
no word for a senior colonel, a rank Germany never had — and none can be built
the usual way, because "Ober-" is how German says "senior" (Oberleutnant) and
Oberst already is that prefix, from "der Oberste". "Stabsoberst" follows the
Bundeswehr's other construction for one grade above a rank (Stabshauptmann,
Stabsfeldwebel); an invention, but an idiomatic one, chosen by the user, a
native speaker, over "Oberst 1. Klasse" and over leaving it as Daxiao. The
Russian renderings of the pinyin and Korean are best-effort in the stock
file's own loose style.

The insert is textual, immediately after the ``rank<country>5`` line, so the
rest of the file survives byte-for-byte — same 2-space indent, same CRLF,
same key order.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402

LOCALE = "nsdata/assets/locale"

# country -> lang -> (rank 6, rank 7)
NAMES = {
    # Colonel -> Major General -> Lieutenant General
    "501": {
        "eng": ("Major General", "Lieutenant General"),
        "ger": ("Generalmajor", "Generalleutnant"),
        "fra": ("Général-major", "Général-lieutenant"),
        "spa": ("General-mayor", "General-leytenant"),
        "rus": ("Генерал-майор", "Генерал-лейтенант"),
        "chs": ("少将", "中将"),
    },
    # Shàngxiào -> Dàxiào (senior colonel) -> Shàojiàng (major general)
    "502": {
        "eng": ("Dàxiào", "Shàojiàng"),
        "ger": ("Stabsoberst", "Generalmajor"),
        "fra": ("Dàxiào", "Shàojiàng"),
        "spa": ("Dàxiào", "Shàojiàng"),
        "rus": ("Дасяо", "Шаоцзян"),
        "chs": ("大校", "少将"),
    },
    # Sangjwa -> Taejwa (senior colonel) -> Sojang (major general)
    "503": {
        "eng": ("Taejwa", "Sojang"),
        "ger": ("Stabsoberst", "Generalmajor"),
        "fra": ("Taejwa", "Sojang"),
        "spa": ("Taejwa", "Sojang"),
        "rus": ("Тэжва", "Сожанг"),
        "chs": ("大校", "少将"),
    },
    # Colonel -> Brigadier General -> Major General
    "601": {
        "eng": ("Brigadier General", "Major General"),
        "ger": ("Brigadegeneral", "Generalmajor"),
        "fra": ("Général de brigade", "Général de division"),
        "spa": ("Brigadier General", "Major General"),     # stock spa is English for 601
        "rus": ("Бригадный генерал", "Генерал-майор"),
        "chs": ("准将", "少将"),
    },
    # Captain -> Rear Admiral (lower half) -> Rear Admiral. The stock file
    # gives each navy its own titles (Korvettenkapitän, Capitaine de corvette),
    # so the flag ranks do too: Flottillenadmiral/Konteradmiral, Contre-amiral/
    # Vice-amiral. Russian has no lower-half term and uses the one-star
    # Коммодор below Контр-адмирал.
    "602": {
        "eng": ("Rear Admiral (lower half)", "Rear Admiral"),
        "ger": ("Flottillenadmiral", "Konteradmiral"),
        "fra": ("Contre-amiral", "Vice-amiral"),
        "spa": ("Rear Admiral (lower half)", "Rear Admiral"),   # stock spa is English for 602
        "rus": ("Коммодор", "Контр-адмирал"),
        "chs": ("准将", "少将"),
    },
    # Colonel -> Brigadier General -> Major General
    "603": {
        "eng": ("Brigadier General", "Major General"),
        "ger": ("Brigadegeneral", "Generalmajor"),
        "fra": ("Général de brigade", "Général de division"),
        "spa": ("Brigadier General", "Major General"),     # stock spa is English for 603
        "rus": ("Бригадный генерал", "Генерал-майор"),
        "chs": ("准将", "少将"),
    },
}
LANGS = ("eng", "ger", "fra", "spa", "rus", "chs")

# Corrections to stock strings, applied to the same shipped files. The stock
# German Navy ladder is right for four rungs and then collapses: Commander
# became "Kommandant" (a billet, not a rank) and Captain became "Hauptmann"
# (an Army captain). The naval grades are Fregattenkapitän and Kapitän zur See.
# Caught by the user, a native speaker, 2026-09-11.
CORRECTIONS = {
    "ger": {
        "rank6024": "Fregattenkapitän",
        "rank6025": "Kapitän zur See",
    },
}


def correct(text: str, lang: str) -> str:
    for key, value in CORRECTIONS.get(lang, {}).items():
        text = set_value(text, key, value)
    return text


def set_value(text: str, key: str, value: str) -> str:
    """Replace the value on an existing key's line, touching nothing else."""
    pattern = re.compile(rf'^([ \t]*"{key}"\s*:\s*)"[^"]*"', re.M)
    if not pattern.search(text):
        raise SystemExit(f"cannot find {key}")
    return pattern.sub(lambda m: m.group(1) + json.dumps(value, ensure_ascii=False),
                       text, count=1)


def patch(text: str, country: str, lang: str) -> str:
    if f'"rank{country}6"' in text:
        # Already added — but bring the values into line with the table, so a
        # renamed rank propagates instead of the first spelling sticking.
        for n, value in zip((6, 7), NAMES[country][lang]):
            text = set_value(text, f"rank{country}{n}", value)
        return text
    # Stop at the key's own comma, not end-of-line: these files are CRLF, and
    # anchoring on $ would either leave the \r unconsumed or splice a bare \n
    # into a CRLF file.
    anchor = re.search(rf'^([ \t]*)"rank{country}5"\s*:\s*"[^"]*"(,?)', text, re.M)
    if not anchor:
        raise SystemExit(f"{lang}: cannot find the rank{country}5 line")
    indent, comma = anchor.group(1), anchor.group(2)
    newline = "\r\n" if "\r\n" in text else "\n"
    six, seven = NAMES[country][lang]
    head = text[:anchor.end()]
    if not comma:
        head += ","
    added = (f'{newline}{indent}"rank{country}6": {json.dumps(six, ensure_ascii=False)},'
             f'{newline}{indent}"rank{country}7": {json.dumps(seven, ensure_ascii=False)}'
             f'{"," if comma else ""}')
    return head + added + text[anchor.end():]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    res = AssetResolver(game)
    out_dir = game / "data" / Path(LOCALE)

    for lang in LANGS:
        vpath = f"{LOCALE}/ranks.locale={lang}.json"
        text = res.read_text(vpath)
        if text is None:
            print(f"  {lang}: source not found, skipped")
            continue
        original = text
        added = []
        for country in NAMES:
            patched = patch(text, country, lang)
            if patched != text:
                added.append(country)
                text = patched
        text = correct(text, lang)
        if text == original:
            print(f"  {lang}: complete already")
            continue
        data = json.loads(text)                  # refuse to write invalid JSON
        before = json.loads(original)
        for country in NAMES:
            six, seven = NAMES[country][lang]
            assert data[f"rank{country}6"] == six and data[f"rank{country}7"] == seven
        for key, value in CORRECTIONS.get(lang, {}).items():
            assert data[key] == value

        # Report by diff rather than by intent, so a value the table renamed
        # shows up the same way as a key it added.
        new = [k for k in data if k not in before]
        changed = [k for k in data if k in before and before[k] != data[k]]
        print(f"  {lang}: +{len(new)} new, {len(changed)} changed  ({len(data)} keys)")
        for key in new:
            print(f"        {key}: {data[key]}")
        for key in changed:
            print(f"        {key}: {before[key]!r} -> {data[key]!r}")
        if not args.dry_run and text != original:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"ranks.locale={lang}.json").write_bytes(text.encode("utf-8"))

    print("\n  --dry-run: nothing written" if args.dry_run
          else f"\n  written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
