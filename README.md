# IL-2 Korea Service Record

A pilot and unit tracker for **IL-2 Sturmovik: Korea**, in the spirit of the
IL-2 Great Battles Campaign Tracker. Reads the game's own career databases and
flight logs; never writes to them.

Status: **data layer only.** No web UI yet.

## Why

Two requests on the IL-2 forum that the game itself does not answer:

> "Now if only someone could make a program for unit/pilot management, such as
> easy to see pilot skill, courage, and discipline levels." — *Swoose*

> "...current rank and awards, kills air/ground and average kills per mission,
> history of wounds, aircraft lost ... a Flight at a time or by individuals."
> — *Viking1*

Every one of those fields is in the career database. Several are packed in ways
that need decoding, and one — rank — the game's own UI gets wrong.

## What is decoded so far

| Thing | Where | Notes |
|---|---|---|
| Careers | `data/Career/*.db` | one file per career, unlike GB's single `cp.db` |
| Kills | packed `killStats` string | `Aircraft` is a rollup **including** `StaticPlane`; airborne = `Aircraft - StaticPlane` |
| Attributes | `pilot.persLevel` | nibble-packed, low first: skills, discipline, courage; UI shows value **+1** |
| Attribute progress | `pilot.leadLevel` | same packing, shown as the purple "up" numbers |
| Awards | `award` table + `scg/2/awards.cfg` | `isDeleted=1` means retired by a higher cluster, not deleted |
| Award route | `event.missionId` | a real mission id = earned at debrief; `-1` = roster sweep |
| Ranks | `pilot.rankId` + `ranks.locale` | see the warning below |
| Events | `event.type` | 0 kill, 19 promotion, 20 award, 33 operation confirmed; 5/14/16 likely; ten more unidentified |

### The game's rank display is wrong — ours is not

The in-game **Award and Promotion** panel shifts every row up by the number of
promotions a pilot has had. A First Lieutenant with one promotion is shown as
"Captain", and his starting rank as "First Lieutenant". A never-promoted pilot
displays correctly, which is why the bug is easy to miss. `pilot.rankId` is
correct and is what this tool uses.

### Flight logs

`data/FlightLogs/*.mlg` use the same binary format as Great Battles at
**version 18** (GB is 17). The GB `mlg2txt.py` decodes them after relaxing that
one version assert — all 26 observed `AType` records parse, including `AType:3`
kills, `AType:10` plane init and `AType:12` object spawn with pilot names. So
per-mission, per-pilot attribution is available, not just cumulative counters.

## Known gaps

- **Locale files are encrypted.** `awards.locale=*.json` and `ranks.locale=*.json`
  live inside `Interface.gtp`. They are only loose on a modded install. The
  extractor must be wired in before a stock install can show real names.
- **`pilot.persLevel` is 0 for the player** in the test career, so the
  commander's own attributes may be stored elsewhere. Unresolved.
- Ten `event.type` values remain unidentified.
- Attribute order: discipline vs courage is inferred from a single pilot whose
  two nibbles are equal. `ORDER_VERIFIED` in `attributes.py` is `False` until
  a pilot with differing values confirms it.

## Layout

```
korea_service_record/
  gamedata.py            game dir resolution, awards.cfg, locale strings
  career/
    database.py          read-only SQLite wrapper + career discovery
    killstats.py         packed killStats parser
    attributes.py        persLevel / leadLevel nibble decode
    events.py            event type map with confidence levels
tools/
  validate.py            checks every derived value against a live career
```

## Validate

```
python tools/validate.py "E:/SteamLibrary/steamapps/common/IL2Series"
```

Assertions encode facts cross-checked against the game's own screens — e.g.
pilot 17's panel reads SKILLS 4 / DISCIPLINE 5 / COURAGE 5, and the mission that
earned the Distinguished Service Cross had exactly 4 airborne kills and 1
aircraft destroyed on the ground.

## Licence

TBD.
