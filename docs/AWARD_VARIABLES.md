# Award condition variables: what actually works

Audited 2026-09-23 against `careerProcessor.dll` in Ghidra — the registration
function, every setter, and the call graph that decides which setter runs in
which pass. This supersedes the legend at the foot of `awards.cfg`, which is
wrong in five places.

A variable is usable only if something **sets** it in the pass being
evaluated. An identifier that is never set reads as **zero**, silently: no
error, no log line, and an award that simply never fires.

## The three passes

| pass | entry | what runs |
|---|---|---|
| mission debrief | `FUN_18003d460` | `FUN_18001afd0` with the pilot's real sortie |
| roster sweep | `FUN_180058450`, `FUN_180036250`, `FUN_180036410` | `FUN_18001afd0` with an **empty** sortie |
| squadron (`IsSquadron=1`) | `FUN_180058450` → `FUN_18001b330` | the squadron's own setter |

`FUN_18001afd0` calls `FUN_18001c120` (career totals) and `FUN_18001bd50`
(dates); `FUN_18001b330` calls `FUN_18001bd50` and `FUN_18001d050`
(operations). Both call the award loop `FUN_18001d330`, which calls
`FUN_18001be80`.

## Usable in a personal award (49)

**Career totals** — `FUN_18001c120`
`AirObj` `BldObj` `BmbrObj` `ComplSorties` `Country` `Efficiency` `FghtObj`
`FlTime` `GrObj` `IsCommander` `IsPlayer` `PCP` `RankID` `SeaCargoObj`
`SeaDestrObj` `SeaObj` `SeaSmallObj` `SeaSubObj` `ServiceDays` `Sorties`
`SquadronID` `TankObj` `TrnsObj` `WIA`

**This sortie** — `FUN_18001afd0`
`AirObjSortie` `BattleEnd` `BldObjSortie` `BmbrObjSortie` `FghtObjSortie`
`GrObjSortie` `noAwards` `RNDsortie` `SeaCargoObjSortie` `SeaDestrObjSortie`
`SeaObjSortie` `SeaSmallObjSortie` `SeaSubObjSortie` `TankObjSortie`
`TrnsObjSortie` `WarEnd` `WIASortie`

**Dates** — `FUN_18001bd50`: `CareerDays` `CDate` `DaysLeft` `DaysTotal`
`Progress` · **since last** — `FUN_18001be80`: `DaysAwarded` `DaysPromoted`
· and `RND`, re-rolled on every read.

## Usable in a squadron award (29)

**Squadron totals** — `FUN_18001b330`
`AirObj` `BattleEnd` `BldObj` `BmbrObj` `ComplSorties` `Country` `Efficiency`
`FghtObj` `FlTime` `GrObj` `SeaCargoObj` `SeaDestrObj` `SeaObj` `SeaSmallObj`
`SeaSubObj` `Sorties` `SquadronID` `TankObj` `WarEnd`

**Operations** — `FUN_18001d050`: `OpTotal` `OpGood` and the per-operation
`Op<N>` / `OpEnd<N>`, whose names are built at run time · plus the same
dates, since-last and `RND` as above.

## Where the legend is wrong

1. **`OpSuccess` does not exist.** Not registered, not set, referenced
   nowhere. The engine invents it as zero, so a condition using it can never
   be true. **Use `OpGood`.**
2. **`Op*` are squadron-only.** The legend says "полк/пилот" and even
   describes what `OpN` means for a pilot. `FUN_18001d050` is called only
   from the squadron pass, so in a personal award every one of them is zero.
3. **`Efficiency` is not squadron-only.** The legend says
   "только при расчёте наград полка", but `FUN_18001c120` sets it for a
   pilot from his squadron's value. It is usable in a personal award.
4. **`TrnsObj` is missing from the squadron pass.** Every other kill counter
   is set in both; this one only in `FUN_18001c120`. Zero for a squadron —
   almost certainly an oversight in the game rather than a rule.
5. **Four real variables are absent from the legend**: `CDate` (used all over
   the stock file and working), `ExAw` (the `AwardRemove` test), `noAwards`,
   and `awardprewver`, whose purpose is unknown.

Registration is not what makes a variable work: nine legend names —
`DaysAwarded` `DaysLeft` `DaysPromoted` `DaysTotal` `Efficiency` `OpTotal`
`Progress` `ServiceDays` and `OpSuccess` — are not in the registration list,
yet all but `OpSuccess` are set by a setter and work.

## Traps that are not about availability

- **`noAwards` is a dead guard.** It means "nothing has been awarded yet
  this sortie", and the loop clears it after any grant. The Air Medal is
  cumulative and its cluster's `AwardRemove` deletes the base row, so the
  engine re-grants it on nearly every sortie and clears the flag before
  anything below it in the file is reached. Do not build on it.
- **In the roster sweeps the sortie is empty**, so every `*Sortie` variable
  is set — to zero. Per-sortie conditions belong in `AwardInProc` only.
- **File order decides.** The first award whose condition passes takes the
  slot; an unguarded award earlier in the file beats a guarded one below it.
- **`FlTime` is hours**, not minutes, and the player accrues about half an
  AI's, because only flown time counts.
- **`RND` is 0–1000 and re-rolled on every read**, so `(RND<500)&(RND<500)`
  is 25 %, not 50 %. `RNDsortie` is rolled once per mission.

## Reproducing this

```
analyzeHeadless <ghidra>/proj careerProcessor -process careerProcessor.dll \
  -noanalysis -scriptPath <scripts> -postScript award_vars_xrefs.java out.tsv <names...>
analyzeHeadless ... -postScript award_paths.java out.txt NAMES <short names> FUNCS <hex...>
```

Scripts in `IL2Korea-Modding/research/ghidra_scripts`. Two notes: the
project is already imported and analysed, so use `-process`, never
`-import`; and the Windows launcher is a `.bat`, whose argument parser eats
`=` and `,` — pass plain space-separated tokens.
