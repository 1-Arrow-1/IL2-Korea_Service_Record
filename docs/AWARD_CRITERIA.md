# Award criteria: what you can test, and where

Which condition variables `awards.cfg` can actually use, and whether they
mean anything for a squadron award (`IsSquadron=1`) or a personal one.
Taken from careerProcessor.dll, not from the legend at the foot of
awards.cfg, which is wrong in six places - they are marked below.

**A "no" is not an error.** An unset variable reads as zero, with no parse
failure and nothing in `_career.log`; the award simply never fires.

| Criterion | What it is | Squadron | Single pilot |
|---|---|:--:|:--:|
| `Country` | The country: 601 USAF, 602 USN, 603 USMC, 501 USSR, 502 PRC, 503 DPRK | yes | yes |
| `CDate` | Today's date in the career, as YYYYMMDD. Undocumented, but the stock file relies on it | yes | yes |
| `RND` | A fresh random 0-1000 on every read. RND<600 is a 60 % chance | yes | yes |
| `RNDsortie` | Random 0-1000, rolled once when the mission ends, so several awards can share one roll | no | yes |
| `ExAw` | Holds award N. Only meaningful inside AwardRemove | yes | yes |
| `noAwards` | Nothing has been awarded yet this sortie - but see the warning below | no | yes |
| **Rank, standing and person** | | | |
| `RankID` | Rank, 0 = 2nd Lt upward. Not capped at 5, whatever the legend says | no | yes |
| `PCP` | Career points: roughly score plus credit for rank, awards and command | no | yes |
| `IsCommander` | He commands the squadron (boolean) | no | yes |
| `IsPlayer` | A human flies this man (boolean) | no | yes |
| `SquadronID` | The squadron's id | yes | yes |
| `Efficiency` | The squadron's efficiency, 0-3. The legend calls this squadron-only; it is not | yes | yes |
| **Service and time** | | | |
| `FlTime` | Flight time in HOURS, not minutes. Warped time is not counted | yes | yes |
| `Sorties` | Sorties flown | yes | yes |
| `ComplSorties` | Sorties completed successfully | yes | yes |
| `CareerDays` | Days elapsed in the career | yes | yes |
| `ServiceDays` | Days since this man joined the squadron | no | yes |
| `DaysPromoted` | Days since his last promotion | yes | yes |
| `DaysAwarded` | Days since his last decoration | yes | yes |
| `DaysTotal` | Days from the start of the career to the end of the war | yes | yes |
| `DaysLeft` | Days still to run until the end of the war | yes | yes |
| `Progress` | How far through the war the career is, 0-100 | yes | yes |
| `WarEnd` | The war has ended | yes | yes |
| `BattleEnd` | The career on the theatre of that id has ended, e.g. BattleEnd=13 | yes | yes |
| **Wounds** | | | |
| `WIA` | How many times he has been wounded | no | yes |
| `WIASortie` | He was wounded on this sortie (boolean) | no | yes |
| **Kills, career totals** | | | |
| `AirObj` | Aircraft destroyed. Aircraft minus parked ones | yes | yes |
| `GrObj` | Materiel destroyed: vehicles, guns, flak. A parked aircraft counts here | yes | yes |
| `SeaObj` | Ships destroyed | yes | yes |
| `BldObj` | Buildings destroyed | yes | yes |
| `FghtObj` | Fighters destroyed | yes | yes |
| `BmbrObj` | Bombers destroyed. The legend mislabels this as transports | yes | yes |
| `TrnsObj` | Transport aircraft destroyed | no | yes |
| `TankObj` | Tanks destroyed | yes | yes |
| `SeaSmallObj` | Small craft destroyed | yes | yes |
| `SeaCargoObj` | Cargo ships destroyed | yes | yes |
| `SeaDestrObj` | Destroyers destroyed | yes | yes |
| `SeaSubObj` | Submarines destroyed | yes | yes |
| **Kills, this sortie only** | | | |
| `AirObjSortie` | Aircraft destroyed on this sortie | no | yes |
| `GrObjSortie` | Materiel destroyed on this sortie | no | yes |
| `SeaObjSortie` | Ships destroyed on this sortie | no | yes |
| `BldObjSortie` | Buildings destroyed on this sortie | no | yes |
| `FghtObjSortie` | Fighters destroyed on this sortie | no | yes |
| `BmbrObjSortie` | Bombers destroyed on this sortie | no | yes |
| `TrnsObjSortie` | Transports destroyed on this sortie | no | yes |
| `TankObjSortie` | Tanks destroyed on this sortie | no | yes |
| `SeaSmallObjSortie` | Small craft destroyed on this sortie | no | yes |
| `SeaCargoObjSortie` | Cargo ships destroyed on this sortie | no | yes |
| `SeaDestrObjSortie` | Destroyers destroyed on this sortie | no | yes |
| `SeaSubObjSortie` | Submarines destroyed on this sortie | no | yes |
| **Operations** | | | |
| `OpTotal` | Campaign operations the squadron has taken part in | yes | no |
| `OpGood` | Of those, the ones that ended in success | yes | no |
| `Op<N>` | Operation N was a success, e.g. Op3. The name is built at run time | yes | no |
| `OpEnd<N>` | Hidden operation N has ended, e.g. OpEnd691 | yes | no |
| `OpSuccess` | DOES NOT EXIST. Reads as zero, so the award can never fire. Use OpGood | no | no |

**50 usable for a pilot, 30 for a squadron.**

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
