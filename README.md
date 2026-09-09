# IL-2 Korea Service Record

A pilot and unit tracker for **IL-2 Sturmovik: Korea**, in the spirit of the
IL-2 Great Battles Campaign Tracker. Reads the game's own career databases and
flight logs; never writes to them.

Status: **working web UI.** Career list -> career detail, read-only.

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
| Kills | packed `killStats` string | two rollups (`Aircraft`, `Building`); airborne = `Aircraft - StaticPlane`; GROUND TARGETS excludes `Materiel` clutter |
| Attributes | `pilot.persLevel` | nibble-packed, low first: skills, **courage, discipline** — not the panel's display order; UI shows value **+1** |
| Attribute progress | `pilot.leadLevel` | same packing, shown as the purple "up" numbers |
| Awards | `award` table + `scg/2/awards.cfg` | `isDeleted=1` means retired by a higher cluster, not deleted |
| Award route | `event.missionId` | a real mission id = earned at debrief; `-1` = roster sweep |
| Ranks | `pilot.rankId` + `ranks.locale` | extracted from the encrypted `Interface.gtp`; see the warning below |
| Events | `event.type` | 16 of 17 types identified — kills, aircraft lost, pilots KIA, wounds, hospital, repairs, deliveries, promotions, awards, operations |

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

## Artwork

Medals, rank insignia and squadron emblems are sliced live out of the game's own
atlases. Each resource dictionary declares its own atlas-to-DDS mapping, so
nothing is hard-coded:

```
awards.xaml      3 atlases,  98 entries
ranks.xaml       6 atlases,  36 entries
squadrons.xaml  10 atlases,  73 entries
```

`/api/icon/<kind>/<id>?h=<px>` returns a PNG, cached per size — a rank insignia
is 467x198 and 200 KB in the atlas but 3.7 KB at the 28 pixels the page uses.
Because the asset layer prefers loose files, a modded install shows the modded
medals.

## Encrypted assets

Rank names, award names, `awards.xaml` and the medal atlases live inside
`Interface.gtp`, which is AES-192-ECB encrypted with a per-file key derived
from the file's own virtual path. The tracker decrypts what it needs on demand
and caches it under `%LOCALAPPDATA%/IL2KoreaTracker`, so it works on a stock
install with **no image pack to download** and nothing written into the game
folder.

A loose file always wins over the archive copy, matching the engine's own
override behaviour — so on a modded install the tool shows the mod's medals and
names.

## Known gaps

- **`pilot.persLevel` is 0 for the player**, decoding to the minimum 1/1/1.
  Probably correct rather than missing — the human supplies the skill — but the
  player's bar values have not been read off the panel to confirm it.
- One `event.type` remains unidentified: **13**, a single row for the player on
  1951.05.15, a day the career skips. Three types (8, 25, 32) are single-row and
  matched only to a UI string, so they are marked `likely` rather than
  `confirmed`.

## Layout

```
korea_service_record/
  gamedata.py            game dir resolution, awards.cfg, locale strings
  assets.py              loose -> cache -> archive resolution
  gtp/
    crypto.py            AES-192 + key schedule (lifted from il2k_extract.py)
    archive.py           gtpack container reader, bounded-memory FAT walk
  career/
    database.py          read-only SQLite wrapper + career discovery
    killstats.py         packed killStats parser
    attributes.py        persLevel / leadLevel nibble decode
    events.py            event type map with confidence levels
    aggregator.py        builds the API payloads
  app.py                 Flask factory + JSON API
  static/                index.html, css/, js/app.js
run.py                   launcher
tools/
  validate.py            checks every derived value against a live career
```

## Run

```
pip install -r requirements.txt
python run.py
```

Opens `http://127.0.0.1:5002/`. The game folder is auto-detected across the
usual Steam drives; override with `--game` or `KOREA_GAME_DIR`.

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
