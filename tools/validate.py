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


def check(label, actual, expected):
    ok = actual == expected
    print(f"   [{'ok ' if ok else 'FAIL'}] {label}: {actual!r}"
          + ("" if ok else f"  (expected {expected!r})"))
    if not ok:
        FAILURES.append(label)


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
    awards_cfg = AwardsConfig(cfg_path)
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

        # ---- regression checks against known-true facts -------------------
        print(f"\n=== checks ===")
        rivera = next((p for p in pilots if p["id"] == 17), None)
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

        funston = next((p for p in pilots if p["id"] == 8), None)
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
        pa = PilotAttributes(player["persLevel"], player["leadLevel"])
        check("player up-points", [r["points"] for r in pa.display_rows()], [0, 2, 2])
        # The commander's panel shows boosters and draws no bars at all.
        check("player has no skill levels", pa.has_levels, False)
        check("player levels are None",
              [r["level"] for r in pa.display_rows()], [None, None, None])

        for pid, levels, points in ((4, [4, 3, 5], [1, 1, 0]),
                                    (11, [3, 4, 3], [0, 1, 1])):
            row = next((p for p in pilots if p["id"] == pid), None)
            if row is None:
                continue
            attrs = PilotAttributes(row["persLevel"], row["leadLevel"])
            check(f"pilot {pid} levels",
                  [r["level"] for r in attrs.display_rows()], levels)
            check(f"pilot {pid} up-points",
                  [r["points"] for r in attrs.display_rows()], points)

        m50 = db.query_one(
            "SELECT * FROM sortie WHERE isPlayer=1 AND missionId=50")
        if m50 is not None:
            # The DSC sortie: 4 airborne Yak-9P + 1 La-11 destroyed on the ground.
            k = KillStats(m50["killStats"])
            check("mission 50 airborne", k.airborne, 4)
            check("mission 50 static air", k.static_air, 1)

        # AI kills are attributed by pairing the blob's formation slots against
        # the sortie rows positionally. Two unrelated fields have to agree for
        # every pair, or the attribution is guesswork: the flight time and the
        # air-kill count. Checked over every mission, not a sampled one.
        pairs = flights = 0
        for row in db.query("SELECT id, result FROM mission"):
            result = MissionResult(row["result"])
            slots = result.flight_slots()
            sorties = db.query(
                """SELECT killStats, flightTime FROM sortie
                   WHERE missionId=? AND isDeleted=0 AND isPlayer=0
                   ORDER BY id""", (row["id"],))
            if not slots or len(slots) != len(sorties):
                continue
            flights += 1
            for slot, sortie in zip(slots, sorties):
                if (int(slot["totalFlightTime"]) == sortie["flightTime"]
                        and _blob_air(slot) == KillStats(sortie["killStats"]).airborne):
                    pairs += 1
        check("AI slot pairing covers every mission", flights > 0, True)
        check("AI slots agree on time and air kills",
              pairs, sum(len(db.query(
                  """SELECT id FROM sortie WHERE missionId=? AND isDeleted=0
                     AND isPlayer=0""", (r["id"],)))
                  for r in db.query("SELECT id FROM mission")))

        aggregator = CareerAggregator(game_dir)
        detail = aggregator.mission_detail(
            f"{target.pilot_name}, {target.squadron_name}", 34)
        if detail is not None:
            # The one AI air kill that mission belongs to Manuel Rivera, and
            # killStats says so independently of the blob.
            scorers = {k["actor"] for k in detail["log"] if k["air"]}
            check("mission 31 air kill attributed", scorers, {"Manuel Rivera"})
            check("no raw account name in the log",
                  any("Arrow" in k["actor"] for k in detail["log"]), False)

        dsc = awards_cfg.get(601021)
        if dsc is not None:
            check("601021 has no noAwards guard", "noAwards" in dsc.in_proc, False)
            check("601021 in_proc reachable", dsc.reachable_in_proc, True)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    default = r"E:\SteamLibrary\steamapps\common\IL2Series"
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else default))
