"""
Write the award-criteria quick reference.

    python tools/award_criteria_table.py

The yes/no columns come from the setter lists read out of
careerProcessor.dll in Ghidra on 2026-09-23 - see docs/AWARD_VARIABLES.md
for the method and the call graph behind them - so they cannot drift from
the decompile by being retyped. If the game is ever patched, redo the audit
and correct the six sets below; nothing else here needs touching.

Writes docs/AWARD_CRITERIA.md, and a copy beside awards.cfg in the modding
folder, which is where it is actually wanted.
"""

from pathlib import Path

# Exactly what each setter was seen to pass to FUN_180065160.
C120 = set("""airobj bldobj bmbrobj complsorties country efficiency fghtobj fltime grobj
iscommander isplayer pcp rankid seacargoobj seadestrobj seaobj seasmallobj seasubobj
servicedays sorties squadronid tankobj trnsobj wia""".split())
AFD0 = set("""airobjsortie battleend bldobjsortie bmbrobjsortie fghtobjsortie grobjsortie
noawards rndsortie seacargoobjsortie seadestrobjsortie seaobjsortie seasmallobjsortie
seasubobjsortie tankobjsortie trnsobjsortie warend wiasortie""".split())
BD50 = set("careerdays cdate daysleft daystotal progress".split())
BE80 = set("daysawarded dayspromoted".split())
B330 = set("""airobj battleend bldobj bmbrobj complsorties country efficiency fghtobj fltime
grobj seacargoobj seadestrobj seaobj seasmallobj seasubobj sorties squadronid tankobj
warend""".split())
D050 = set("opgood optotal".split())

PILOT = C120 | AFD0 | BD50 | BE80 | {"rnd", "exaw"}
SQUAD = B330 | BD50 | BE80 | D050 | {"rnd", "exaw"}

ROWS = [
    ("Country", "The country: 601 USAF, 602 USN, 603 USMC, 501 USSR, 502 PRC, 503 DPRK"),
    ("CDate", "Today's date in the career, as YYYYMMDD. Undocumented, but the stock file relies on it"),
    ("RND", "A fresh random 0-1000 on every read. RND<600 is a 60 % chance"),
    ("RNDsortie", "Random 0-1000, rolled once when the mission ends, so several awards can share one roll"),
    ("ExAw", "Holds award N. Only meaningful inside AwardRemove"),
    ("noAwards", "Nothing has been awarded yet this sortie - but see the warning below"),
    (None, "Rank, standing and person"),
    ("RankID", "Rank, 0 = 2nd Lt upward. Not capped at 5, whatever the legend says"),
    ("PCP", "Career points: roughly score plus credit for rank, awards and command"),
    ("IsCommander", "He commands the squadron (boolean)"),
    ("IsPlayer", "A human flies this man (boolean)"),
    ("SquadronID", "The squadron's id"),
    ("Efficiency", "The squadron's efficiency, 0-3. The legend calls this squadron-only; it is not"),
    (None, "Service and time"),
    ("FlTime", "Flight time in HOURS, not minutes. Warped time is not counted"),
    ("Sorties", "Sorties flown"),
    ("ComplSorties", "Sorties completed successfully"),
    ("CareerDays", "Days elapsed in the career"),
    ("ServiceDays", "Days since this man joined the squadron"),
    ("DaysPromoted", "Days since his last promotion"),
    ("DaysAwarded", "Days since his last decoration"),
    ("DaysTotal", "Days from the start of the career to the end of the war"),
    ("DaysLeft", "Days still to run until the end of the war"),
    ("Progress", "How far through the war the career is, 0-100"),
    ("WarEnd", "The war has ended"),
    ("BattleEnd", "The career on the theatre of that id has ended, e.g. BattleEnd=13"),
    (None, "Wounds"),
    ("WIA", "How many times he has been wounded"),
    ("WIASortie", "He was wounded on this sortie (boolean)"),
    (None, "Kills, career totals"),
    ("AirObj", "Aircraft destroyed. Aircraft minus parked ones"),
    ("GrObj", "Materiel destroyed: vehicles, guns, flak. A parked aircraft counts here"),
    ("SeaObj", "Ships destroyed"),
    ("BldObj", "Buildings destroyed"),
    ("FghtObj", "Fighters destroyed"),
    ("BmbrObj", "Bombers destroyed. The legend mislabels this as transports"),
    ("TrnsObj", "Transport aircraft destroyed"),
    ("TankObj", "Tanks destroyed"),
    ("SeaSmallObj", "Small craft destroyed"),
    ("SeaCargoObj", "Cargo ships destroyed"),
    ("SeaDestrObj", "Destroyers destroyed"),
    ("SeaSubObj", "Submarines destroyed"),
    (None, "Kills, this sortie only"),
    ("AirObjSortie", "Aircraft destroyed on this sortie"),
    ("GrObjSortie", "Materiel destroyed on this sortie"),
    ("SeaObjSortie", "Ships destroyed on this sortie"),
    ("BldObjSortie", "Buildings destroyed on this sortie"),
    ("FghtObjSortie", "Fighters destroyed on this sortie"),
    ("BmbrObjSortie", "Bombers destroyed on this sortie"),
    ("TrnsObjSortie", "Transports destroyed on this sortie"),
    ("TankObjSortie", "Tanks destroyed on this sortie"),
    ("SeaSmallObjSortie", "Small craft destroyed on this sortie"),
    ("SeaCargoObjSortie", "Cargo ships destroyed on this sortie"),
    ("SeaDestrObjSortie", "Destroyers destroyed on this sortie"),
    ("SeaSubObjSortie", "Submarines destroyed on this sortie"),
    (None, "Operations"),
    ("OpTotal", "Campaign operations the squadron has taken part in"),
    ("OpGood", "Of those, the ones that ended in success"),
    ("Op<N>", "Operation N was a success, e.g. Op3. The name is built at run time"),
    ("OpEnd<N>", "Hidden operation N has ended, e.g. OpEnd691"),
    ("OpSuccess", "DOES NOT EXIST. Reads as zero, so the award can never fire. Use OpGood"),
]

HEAD = """# Award criteria: what you can test, and where

Which condition variables `awards.cfg` can actually use, and whether they
mean anything for a squadron award (`IsSquadron=1`) or a personal one.
Taken from careerProcessor.dll, not from the legend at the foot of
awards.cfg, which is wrong in six places - they are marked below.

**A "no" is not an error.** An unset variable reads as zero, with no parse
failure and nothing in `_career.log`; the award simply never fires.

"""

TAIL = """
**{pilot} usable for a pilot, {squad} for a squadron.**

## Three things the columns cannot say

- **`noAwards` is "yes" for a pilot but useless in practice.** It is set at
  the start of each sortie and cleared after any grant, and the cumulative
  Air Medal re-fires on nearly every sortie - clearing it before anything
  lower in the file is reached. Do not build on it.
- **The `*Sortie` variables are "yes" only in `AwardInProc`.** The roster
  sweeps that evaluate `AwardByDef` hand the evaluator an empty sortie, so
  those variables are set - to zero. Per-sortie tests belong in
  `AwardInProc` alone.
- **File order decides who gets an award.** The first condition that passes
  takes the slot, so an unguarded award earlier in the file beats a guarded
  one below it.

## Where the legend is wrong

1. `OpSuccess` does not exist anywhere in the engine. Use `OpGood`.
2. The `Op*` family is squadron-only, though the legend describes what
   `OpN` means for a pilot.
3. `Efficiency` is not squadron-only - it is set for pilots too.
4. `TrnsObj` is missing from the squadron pass, alone among the kill
   counters.
5. `CDate`, `ExAw`, `noAwards` and `awardprewver` are real but undocumented.
6. `BmbrObj` and `TrnsObj` carry the same description; by name `BmbrObj`
   is bombers.

Full audit, with the functions and the call graph: `docs/AWARD_VARIABLES.md`.
Regenerate this file with `python tools/award_criteria_table.py`.
"""


def mark(name, available):
    key = name.lower().replace("<n>", "")
    if name == "OpSuccess":
        return "no"
    if key in ("op", "opend"):                 # names built at run time
        return "yes" if available is SQUAD else "no"
    return "yes" if key in available else "no"


def build():
    lines = ["| Criterion | What it is | Squadron | Single pilot |",
             "|---|---|:--:|:--:|"]
    for name, desc in ROWS:
        if name is None:
            lines.append(f"| **{desc}** | | | |")
            continue
        lines.append(f"| `{name}` | {desc} | {mark(name, SQUAD)} | {mark(name, PILOT)} |")
    return HEAD + "\n".join(lines) + "\n" + TAIL.format(pilot=len(PILOT), squad=len(SQUAD))


def main():
    doc = build()
    repo = Path(__file__).resolve().parent.parent
    modding = Path.home() / "IL2Korea-Modding"
    for target in (repo / "docs" / "AWARD_CRITERIA.md", modding / "AWARD_CRITERIA.md"):
        if target.parent.is_dir():
            target.write_text(doc, encoding="utf-8")
            print("wrote", target)
        else:
            print("skipped, no such folder:", target.parent)
    print(f"{len(PILOT)} usable for a pilot, {len(SQUAD)} for a squadron")


if __name__ == "__main__":
    main()
