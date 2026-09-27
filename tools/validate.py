"""
Validate the data layer against a live IL-2 Korea career.

There is no UI yet, so this is how the parsing is checked: every derived value
is printed next to the raw column it came from, and the assertions at the end
encode facts confirmed against the game's own screens.

    python tools/validate.py "E:/SteamLibrary/steamapps/common/IL2Series"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from korea_service_record.career.attributes import PilotAttributes
from korea_service_record.career.database import KoreaCareerDatabase, find_careers
from korea_service_record.career.events import (award_action, award_source,
                                                describe, is_award_event)
from korea_service_record.career.killstats import KillStats
from korea_service_record.career.missionresult import MissionResult
from korea_service_record import corrections
import korea_service_record
from korea_service_record.assets import AssetResolver
from korea_service_record.career.aggregator import CareerAggregator

# The blob counts aircraft by class; killStats counts them as one number.
_AIR_COLUMNS = [
    "killLightFighter", "killMediumFighter", "killHeavyFighter", "killJetFighter",
    "killLightBomber", "killMediumBomber", "killHeavyBomber",
    "killLightAttackPlane", "killMediumAttackPlane", "killHeavyAttackPlane",
    "killLightRecon", "killMediumRecon", "killHeavyRecon",
    "killLightTransport", "killMediumTransport", "killHeavyTransport",
    "killAirship", "killLightAerostat", "killMediumAerostat",
]


def _blob_air(slot):
    return sum(int(slot.get(c, "0") or 0) for c in _AIR_COLUMNS)
from korea_service_record.gamedata import (AwardsConfig, LocaleStrings,
                                           DEFAULT_TVD, resolve_game_dir)

FAILURES = []
SKIPPED = []

# The career these facts were read off in game. Anything checked against a
# pilot by id belongs to that file and nothing else: ids are reused, so on a
# different career "pilot 17" is a different man and the check would fail on
# a parser that is working perfectly. Those checks now skip out loud instead.
FIXTURE_CAREER = "Manuel Rivera's career (deleted 2026-09)"


def check(label, actual, expected):
    ok = actual == expected
    print(f"   [{'ok ' if ok else 'FAIL'}] {label}: {actual!r}"
          + ("" if ok else f"  (expected {expected!r})"))
    if not ok:
        FAILURES.append(label)


def skip(label, why):
    print(f"   [skip] {label}: {why}")
    SKIPPED.append(label)


def main(game_arg):
    game_dir = resolve_game_dir(Path(game_arg))
    if game_dir is None:
        print(f"Not an IL-2 install: {game_arg}")
        return 2
    print(f"game dir: {game_dir}\n")

    careers = find_careers(game_dir)
    print(f"=== careers found: {len(careers)} ===")
    for c in careers:
        print(f"   {c.pilot_name}  |  {c.squadron_name}  |  {c.path.name}")
    if not careers:
        return 1

    cfg_path = game_dir / "data" / "scg" / str(DEFAULT_TVD) / "awards.cfg"
    resolver = AssetResolver(game_dir)
    awards_cfg = AwardsConfig(cfg_path, resolver=resolver)
    # A stock installation has no loose awards.cfg — the game keeps it inside
    # Missions.gtp. Reading the direct path alone returned nothing there, so
    # every award definition was empty on any machine without the mod.
    from_archive = AwardsConfig(game_dir / "nope.cfg", resolver=resolver)
    check("awards.cfg loads without a loose copy",
          len(from_archive.definitions) > 0, True)
    locale = LocaleStrings(game_dir)
    print(f"\n=== game data ===")
    print(f"   awards.cfg definitions : {len(awards_cfg.definitions)}")
    print(f"   promotion awards       : "
          f"{sorted(d.award_id for d in awards_cfg.promotions())}")
    print(f"   award locale           : {len(locale.awards)} keys "
          f"({locale.sources()['awards']})")
    print(f"   rank  locale           : {len(locale.ranks)} keys "
          f"({locale.sources()['ranks']})")
    dead = [d.award_id for d in awards_cfg.definitions.values()
            if not d.reachable_in_proc and not d.reachable_by_def and not d.required]
    print(f"   unobtainable awards    : {dead or 'none'}")

    # Use the largest career file — the one with real history.
    target = max(careers, key=lambda c: c.path.stat().st_size)
    print(f"\n=== career: {target.path.name} ===")

    with KoreaCareerDatabase(target.path) as db:
        career = db.career()
        squad = db.squadron()
        player = db.player()
        pilots = db.pilots()
        print(f"   currentDate={career['currentDate']}  tvd={career['tvd']}  "
              f"pilots={len(pilots)}  awardPoints={squad['awardPoints']}")

        print(f"\n--- player ---")
        ks = KillStats(player["killStats"])
        attrs = PilotAttributes(player["persLevel"], player["leadLevel"])
        print(f"   {player['name']} {player['lastName']}  "
              f"{locale.rank_name(player['country'], player['rankId'])} "
              f"(rankId={player['rankId']})")
        print(f"   sorties={player['sorties']} good={player['goodSorties']} "
              f"flightTime={player['flightTime']}s = {player['flightTime']/3600:.1f}h")
        print(f"   airborne={ks.airborne} static_air={ks.static_air} "
              f"ground={ks.ground_total}")
        print(f"   categories={ks.category_totals()}")
        print(f"   attributes={attrs.levels} points={attrs.points}")
        if ks.unknown_keys():
            print(f"   !! unclassified killStats keys: {sorted(ks.unknown_keys())}")

        print(f"\n--- awards held (player) ---")
        for row in db.awards(player["id"]):
            defn = awards_cfg.get(row["type"])
            name = locale.award_name(row["type"], defn.name if defn else "")
            print(f"   {row['type']}  {name[:46]:<48} "
                  f"earned={row['earnedDate']} received={row['receivedDate']} "
                  f"pending={row['isPending']}")

        print(f"\n--- award/promotion events (player, last 8) ---")
        rows = [r for r in db.events(player["id"]) if is_award_event(r["type"])]
        for row in rows[-8:]:
            defn = awards_cfg.get(row["ipar2"])
            name = locale.award_name(row["ipar2"], defn.name if defn else "")
            print(f"   {row['date'][:10]}  {describe(row['type']).key:<9} "
                  f"{award_action(row['ipar3']):<9} {award_source(row['missionId']):<7} "
                  f"{name[:40]}")

        print(f"\n--- event type coverage ---")
        counts = {}
        for row in db.events():
            counts[row["type"]] = counts.get(row["type"], 0) + 1
        for code in sorted(counts):
            info = describe(code)
            print(f"   type {code:<3} n={counts[code]:<6} {info.confidence:<9} {info.label}")

        # ---- parser fixtures, independent of any career -------------------
        # These were read off the game's own pilot panels. They used to be
        # looked up by pilot id in whatever career happened to be installed,
        # which meant they broke the moment that career was deleted - and
        # worse, they then failed against a healthy parser. The raw packed
        # values are recorded here instead, so the checks test the parsing
        # and nothing else.
        #
        # persLevel and leadLevel pack three nibbles low to high as skills,
        # courage, discipline; the panel prints skills, discipline, courage,
        # so the middle two are crossed. Levels display one higher than they
        # are stored, boosters display as stored. The player's own 0x220 is
        # the case that fixes it: 0/2/2 on the panel.
        print(f"\n=== parser fixtures ===")
        for label, pers, lead, levels, points in (
                ("panel 4/5/5 ups 13/2/2", 1091, 557, [4, 5, 5], [13, 2, 2]),
                ("panel 4/5/4 ups 1/0/0", 1075, 1, [4, 5, 4], [1, 0, 0]),
                ("panel 4/3/5 ups 1/1/0", 579, 257, [4, 3, 5], [1, 1, 0]),
                ("panel 3/4/3 ups 0/1/1", 802, 272, [3, 4, 3], [0, 1, 1]),
        ):
            attrs = PilotAttributes(pers, lead)
            check(f"{label} levels",
                  [r["level"] for r in attrs.display_rows()], levels)
            check(f"{label} points",
                  [r["points"] for r in attrs.display_rows()], points)

        # The commander has no simulated skill: the panel draws him no bars
        # at all and shows boosters instead. leadLevel 0x220 is 0/2/2.
        commander = PilotAttributes(0, 0x220)
        check("commander has no levels", commander.has_levels, False)
        check("commander levels are None",
              [r["level"] for r in commander.display_rows()], [None, None, None])
        check("commander points", [r["points"] for r in commander.display_rows()],
              [0, 2, 2])

        # A hand-totted killStats blob, using only keys this game actually
        # writes. Five aircraft of which one was parked, so four airborne;
        # ground targets are the truck, the two tanks, the three guns and the
        # parked aircraft - a parked plane is a ground target - so 10 + 2 + 3
        # + 1 = 16. The first draft of this used "MediumBomber", which the
        # game never emits, and the parser quite rightly binned it as unknown
        # ground clutter and returned 17.
        ks = KillStats("Aircraft=5&LightFighter=3&MediumAttackPlane=1"
                       "&StaticPlane=1&Truck=10&MediumTank=2&HeavyFlak=3")
        check("fixture airborne", ks.airborne, 4)
        check("fixture static air", ks.static_air, 1)
        check("fixture ground targets", ks.ground_targets, 16)
        check("empty killStats is zero, not negative", KillStats("").airborne, 0)
        check("malformed killStats is zero", KillStats("rubbish").airborne, 0)

        # ---- checks against this career -----------------------------------
        print(f"\n=== checks ===")
        fixture_career = target.pilot_name == "Manuel Rivera"
        rivera = next((p for p in pilots if p["id"] == 17), None) if fixture_career else None
        if rivera is not None:
            ra = PilotAttributes(rivera["persLevel"], rivera["leadLevel"])
            # From the in-game panel: SKILLS 4, DISCIPLINE 5, COURAGE 5, ups 13/2/2
            check("pilot 17 skills", ra.skills, 4)
            check("pilot 17 discipline", ra.discipline, 5)
            check("pilot 17 courage", ra.courage, 5)
            check("pilot 17 up-points", list(ra.points.values()), [13, 2, 2])
            check("pilot 17 rank name",
                  locale.rank_name(rivera["country"], rivera["rankId"]),
                  "First Lieutenant")
            check("player rank name",
                  locale.rank_name(player["country"], player["rankId"]), "Major")

        funston = (next((p for p in pilots if p["id"] == 8), None)
                   if fixture_career else None)
        if funston is not None:
            fa = PilotAttributes(funston["persLevel"], funston["leadLevel"])
            # From the in-game panel: SKILLS 4, DISCIPLINE 5, COURAGE 4, ups 1/0/0.
            # This pilot is what fixes the packed nibble order.
            check("pilot 8 skills", fa.skills, 4)
            check("pilot 8 discipline", fa.discipline, 5)
            check("pilot 8 courage", fa.courage, 4)
            check("pilot 8 up-points",
                  [r["points"] for r in fa.display_rows()], [1, 0, 0])
            fk = KillStats(funston["killStats"])
            # Panel: AIR VICTORIES 0, GROUND TARGETS 115.
            check("pilot 8 air victories", fk.airborne, 0)
            check("pilot 8 ground targets", fk.ground_targets, 115)

        if rivera is not None:
            # Panel: AIR VICTORIES 1, GROUND TARGETS 102.
            rk = KillStats(rivera["killStats"])
            check("pilot 17 air victories", rk.airborne, 1)
            check("pilot 17 ground targets", rk.ground_targets, 102)

        # The player's own panel reports up-numbers 0 / 2 / 2 in display order,
        # from leadLevel 0x220. A third pilot confirming the packed order, and
        # the only one whose skills nibble is zero.
        # Whatever career is installed, the player is the one man the game
        # simulates no skill for. That is an invariant, not a fixture.
        pa = PilotAttributes(player["persLevel"], player["leadLevel"])
        check("player has no skill levels", pa.has_levels, False)
        check("player levels are None",
              [r["level"] for r in pa.display_rows()], [None, None, None])

        for pid, levels, points in (() if not fixture_career else
                                    ((4, [4, 3, 5], [1, 1, 0]),
                                     (11, [3, 4, 3], [0, 1, 1]))):
            row = next((p for p in pilots if p["id"] == pid), None)
            if row is None:
                continue
            attrs = PilotAttributes(row["persLevel"], row["leadLevel"])
            check(f"pilot {pid} levels",
                  [r["level"] for r in attrs.display_rows()], levels)
            check(f"pilot {pid} up-points",
                  [r["points"] for r in attrs.display_rows()], points)

        m50 = (db.query_one("SELECT * FROM sortie WHERE isPlayer=1 AND missionId=50")
               if fixture_career else None)
        if not fixture_career:
            skip("career fixtures (pilots 4/8/11/17, missions 31 and 50)",
                 f"recorded against {FIXTURE_CAREER}; "
                 f"installed is {target.pilot_name}, {target.squadron_name}")
        if m50 is not None:
            # The DSC sortie: 4 airborne Yak-9P + 1 La-11 destroyed on the ground.
            k = KillStats(m50["killStats"])
            check("mission 50 airborne", k.airborne, 4)
            check("mission 50 static air", k.static_air, 1)

        # AI kills are attributed by pairing the blob's formation slots against
        # the sortie rows positionally. Two unrelated fields have to agree for
        # every pair, or the attribution is guesswork: the flight time and the
        # air-kill count. Checked over every mission, not a sampled one.
        # The flight-time half of this has to allow for the tracker's own
        # corrections: applying them rewrites sortie.flightTime on purpose, so
        # on a corrected mission the blob and the row are *meant* to differ.
        # Checking them anyway made the validator fail on a working product -
        # fifteen missions, every one of them in the sidecar. The kill half is
        # untouched by corrections and stays strict everywhere.
        corrected = set()
        try:
            sidecar = corrections.load(target.path.stem) or {}
            corrected = {int(k) for k in (sidecar.get("missions") or {})
                         if str(k).isdigit()}
        except Exception:                      # no sidecar is not a failure
            pass

        total = kills_ok = times_ok = times_checked = flights = 0
        for row in db.query("SELECT id, result FROM mission"):
            slots = MissionResult(row["result"]).flight_slots()
            sorties = db.query(
                """SELECT killStats, flightTime FROM sortie
                   WHERE missionId=? AND isDeleted=0 AND isPlayer=0
                   ORDER BY id""", (row["id"],))
            if not slots or len(slots) != len(sorties):
                continue
            flights += 1
            for slot, sortie in zip(slots, sorties):
                total += 1
                if _blob_air(slot) == KillStats(sortie["killStats"]).airborne:
                    kills_ok += 1
                if row["id"] in corrected:
                    continue
                times_checked += 1
                if int(slot["totalFlightTime"]) == sortie["flightTime"]:
                    times_ok += 1
        every_ai_sortie = sum(len(db.query(
            """SELECT id FROM sortie WHERE missionId=? AND isDeleted=0
               AND isPlayer=0""", (r["id"],)))
            for r in db.query("SELECT id FROM mission"))
        check("AI slot pairing covers every mission", flights > 0, True)
        check("AI slot pairing reaches every AI sortie", total, every_ai_sortie)
        check("AI slots agree on air kills", kills_ok, total)
        check(f"AI slots agree on flight time ({len(corrected)} corrected "
              f"mission(s) excluded)", times_ok, times_checked)

        aggregator = CareerAggregator(game_dir)
        detail = (aggregator.mission_detail(
            f"{target.pilot_name}, {target.squadron_name}", 34)
            if fixture_career else None)
        if detail is not None:
            # The one AI air kill that mission belongs to Manuel Rivera, and
            # killStats says so independently of the blob.
            scorers = {k["actor"] for k in detail["log"] if k["air"]}
            check("mission 31 air kill attributed", scorers, {"Manuel Rivera"})
            check("no raw account name in the log",
                  any("Arrow" in k["actor"] for k in detail["log"]), False)

        # --- i18n ---------------------------------------------------------
        # A locale that drifts from English fails silently: the front end falls
        # back key by key, so a missing string looks like an English label
        # rather than an error. Same for a placeholder lost in translation —
        # {reason} becomes literal text instead of the message.
        import json as _json
        import re as _re
        loc_dir = Path(korea_service_record.__file__).parent / "locales"

        def _flat(obj, prefix=""):
            out = {}
            for k, v in obj.items():
                out.update(_flat(v, prefix + k + ".") if isinstance(v, dict)
                           else {prefix + k: v})
            return out

        # A countable string is an object of CLDR plural forms rather than
        # one string, and the languages do not agree on which forms exist:
        # English and German need one/other, Russian one/few/many/other,
        # Chinese other alone. So a plural key is compared by its stem -
        # every language must carry the stem and an "other" - and never by
        # the set of forms, which would demand Russian's "few" of Chinese.
        CATEGORIES = {"zero", "one", "two", "few", "many", "other"}

        def _stem(key):
            head, _, last = key.rpartition(".")
            return head if head and last in CATEGORIES else key

        def _plural_stems(flat):
            return {_stem(k) for k in flat if _stem(k) != k}

        english = _flat(_json.loads((loc_dir / "en.json").read_text(encoding="utf-8")))
        en_plural = _plural_stems(english)
        en_keys = {_stem(k) for k in english}
        for other in sorted(loc_dir.glob("*.json")):
            if other.stem == "en":
                continue
            strings = _flat(_json.loads(other.read_text(encoding="utf-8")))
            keys = {_stem(k) for k in strings}
            check(f"{other.stem}.json has every key", en_keys - keys, set())
            check(f"{other.stem}.json has no stray key", keys - en_keys, set())
            # Whatever forms a language chose, "other" must be among them:
            # it is the one the front end falls back to.
            check(f"{other.stem}.json plurals have an \"other\" form",
                  sorted(s for s in en_plural if f"{s}.other" not in strings), [])
            # A plural form is checked against English's "other", since
            # that is the only form English is certain to have.
            def _english_for(key):
                stem = _stem(key)
                return english.get(key, english.get(f"{stem}.other"))
            holes = [k for k in strings
                     if _english_for(k) is not None
                     and set(_re.findall(r"\{(\w+)\}", _english_for(k)))
                     != set(_re.findall(r"\{(\w+)\}", strings[k]))]
            check(f"{other.stem}.json keeps its placeholders", sorted(holes), [])

        # Every key the payload asks the front end to translate must exist, or
        # the reader sees "incidences.plane_lost" on the page.
        detail = aggregator.career_detail(
            f"{target.pilot_name}, {target.squadron_name}", None)
        if detail is not None:
            asked = set()
            for row in (detail["incidences"] + detail["missions_flown"]
                        + detail["performance"]):
                asked.update(v for v in (row.get("key"), row.get("value_key"),
                                         row.get("detail_key")) if v)
            asked.update("combat." + item["key"] for item in detail["combat"]["headline"])
            check("every key the server emits exists in en.json",
                  sorted(asked - set(english)), [])

        dsc = awards_cfg.get(601021)
        if dsc is not None:
            check("601021 has no noAwards guard", "noAwards" in dsc.in_proc, False)
            check("601021 in_proc reachable", dsc.reachable_in_proc, True)

    print()
    if SKIPPED:
        print(f"skipped {len(SKIPPED)}: {SKIPPED}")
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    default = r"E:\SteamLibrary\steamapps\common\IL2Series"
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else default))
