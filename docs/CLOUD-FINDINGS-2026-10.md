# 2.2.0 review: killfix, napalmfix, recovery, database (cloud session, 2026-10-02)

Scope: `korea_service_record/career/killfix.py`, `korea_service_record/napalmfix.py`,
`korea_service_record/recovery.py`, and the `career/database.py` / `progress.py` /
`app.py` / `aggregator.py` changes from commit c1bec42. The work was done without the
game, career databases or flight logs. Everything below was read from the code or
reproduced on the synthetic SQLite fixtures in `tests/`. Anything marked
**(inferred)** was not reproduced and needs a check against real data.

Line numbers refer to this branch. The one code change on it removes an unused import
from `recovery.py`, which moves the lines after 131 up by one compared with c1bec42.

## Findings, by severity

### High

**H1. Users have no way to undo the correction or turn it off, and putting a backup back by hand gets corrected again.**
`napalmfix.restore()` (napalmfix.py:271) and `recovery.restore()` (recovery.py:271)
have no caller anywhere in the tree: nothing in `app.py`, `career_helper.py` or `tools/`
calls them. The only thing that sets `auto = False` is restore(), so both automatic runs
can never be switched off.
*Scenario:* a user follows the forum post's "IF YOU WANT TO UNDO IT" section and copies a
`.career-backup` over the career `.db`. The `.napalm.json` / `.recovered.json` records
still say `auto: true`. On the next career read, `recovery.auto_sync` puts the rows back
and `napalmfix.auto_sync` writes the corrected values again, because every target is
recomputed from the record. The backup only stays in force if the user also deletes or
edits the JSON records, and nothing tells them to.
*Severity reasoning:* the code writes into the game's file on every read with no opt-out,
and the published undo path does not work as described. Fixing it changes behaviour, so it
stays a finding.

### Medium

**M1. A lost mission that rebuilds to zero rows is retried, and backed up, on every read.**
`lost_missions()` (recovery.py:110) picks any mission whose `result` contains `players=`,
whose `pilotsList` is not empty, and which has no sortie row. `rebuild()` returns `[]`
when the players section has a header but no rows, when `parse_pilots_list` rejects the
header, or when no slot pairs with a player. `apply()` then inserts nothing, but it still
records the mission and saves. The mission stays "lost", so on every career read
`auto_sync` calls `corrections.backup()` (recovery.py:329) and then `apply()`.
*Scenario:* tested in `test_mission_rebuilding_to_nothing_is_not_retried_forever`
(xfail): three reads produce three backups. With `KEEP_BACKUPS = 12`
(corrections.py:52), twelve page loads rotate out every older backup of that career,
including the one taken before 2.2.0 first wrote to it.
*Real data:* none of the 97 missions verified locally rebuilt to zero rows, but a
false-positive mission (see Q4) would be the likely trigger **(inferred)**.

**M2. A backup is taken before every attempt, including attempts that then fail on the game's lock.**
napalmfix.py:335 and recovery.py:329 back up first, then `apply()` fails after 1 s with
`database is locked`, and the next read does the same again. The flight-time
`corrections.auto_sync` (corrections.py:470) has the same pattern, which predates 2.2.0.
*Scenario:* tested in `test_failed_attempt_on_a_locked_file_takes_no_backup` (xfail).
With the game holding a write lock, each career read leaves a new backup and writes
nothing. Twelve reads during a play session push out the backups that hold the game's
original values. The JSON records still hold those values, but per H1 nothing can use
them.
Related **(inferred)**: `shutil.copy2` (corrections.py:366) copies only the `.db`. If the
game is mid-commit, or the file is in WAL mode (see Q2), the copy can be torn or miss
committed pages.

**M3. The career file is committed before the JSON record is saved, so a failure in between loses state.**
- `napalmfix.apply`: commit at napalmfix.py:262, save at :267. If the save fails (disk
  full, permissions, AV lock on the JSON) or the process dies in between, the file holds
  corrected values and the record of the originals is lost. The next run reads the
  corrected values as "original", so the correction holds, but restore() can no longer
  put back the game's values or PCP gaps. Tested in
  `test_originals_survive_a_failed_record_save` (xfail).
- `napalmfix.restore`: commit at :308, save at :313. If the save fails, `auto` stays true
  and the next read applies the correction again, silently undoing the user's restore.
  Tested in `test_restore_sticks_even_if_the_record_save_fails` (xfail).
- `recovery.apply`: commit at recovery.py:260, then the napalm record is saved at :264,
  then the recovery record at :267. If the napalm save fails, the napalm offsets still
  hold the restored kills that are now also in sortie rows, so pilot and squadron totals
  are inflated by those kills, and napalmfix writes that into the file. If only the
  recovery save fails, the inserted rows are no longer listed anywhere, and restore() can
  never remove them. Not tested.

### Low

**L1. A sortie the game later deletes takes its whole count off the totals.**
napalmfix plans over `isDeleted = 0` sorties (napalmfix.py:161). The offsets were taken
with that sortie included, so after deletion the pilot and squadron totals lose its
corrected kills as well as the inflation. A pilot left with no live sortie is skipped
entirely (napalmfix.py:183-191) and keeps the old corrected total. Pinned by
`test_deleted_sortie_takes_its_whole_count_off_the_totals`. Whether this is wrong depends
on what the game itself does when it deletes a sortie (Q3).

**L2. A mission that lost only some of its rows is not detected (by design).**
`lost_missions()` skips any mission with at least one sortie row (recovery.py:116), and
`apply()` checks the same thing again (recovery.py:240). This matches the docstring,
which says the escapedJail INSERT fails for every row of a mission. Pinned by
`test_mission_that_lost_only_some_rows_is_not_detected`.

**L3. `rebuild()` pairs slots and players with `zip`, so a count mismatch drops rows silently.**
recovery.py:187-188. If the debrief has more AI rows than pilotsList has slots, or the
reverse, the extras are dropped without a warning. With no human row, `slots[0]` is
paired with the first AI row. The 701/701 local check says this does not happen on the
data seen so far **(inferred for other careers)**.

**L4. A leaf key that appears twice in one killStats string is cut twice.**
killfix.py:133-146 compares each pair against the same rebuilt count. For
`MilitaryFacility=3&MilitaryFacility=3` with one kill row, the cut is 4, not 2 below the
total of 6. The game is not known to write duplicate keys. Pinned by
`test_duplicate_leaf_key_is_reduced_twice`.

**L5. `KillCategories.from_resolver` crashes on unexpected file shapes.**
killfix.py:86-97. If a game update turns `statreporting.json` into a top-level array, or
`internal` or `objects` into a list or dict of another shape, the result is
`AttributeError`, or a string member is iterated character by character. The call sits
in `CareerAggregator.__init__` (aggregator.py:435) with no try, so the aggregator would
fail to build. `loads_lenient` already turns unparseable text into `{}`, which is
handled. This only matters if the file format changes **(inferred)**.

**L6. A rail cut is taken from `Raildoad` first, but the points formula reads only `Railroad`.**
`subtract()` spends the `Railroad` rollup cut across both spellings in stored order
(killfix.py:156-169), and `Raildoad` sorts first. `points()` reads only `Railroad`
(napalmfix.py:130). If a re-kill ever landed in a rail leaf, the part of the cut taken
from `Raildoad` would change killStats without changing the PCP excess. Only airfield
categories have been seen inflated, so this has no effect today **(inferred)**.

**L7. The PCP excess replays only the sortie rows in the file.**
`points()` starts its pots (vehicles mod 15, rail and buildings mod 5) at zero from the
pilot's first sortie row (napalmfix.py:206). The game's pots also hold sorties that have
no row (escapedJail missions not yet recovered, anything else missing), so the excess can
be off by one point at a pot boundary. The `gap = pcp - score` invariant is documented
as 46/46, but this cloud session could not check the excess per pilot (Q7).

**L8. The plan is read outside the write transaction.**
`apply()` plans on a read-only connection (napalmfix.py:244) and only then takes
`BEGIN IMMEDIATE` (:248). `auto_sync` also plans once before it backs up. If the game
commits in that window, for example a new sortie together with its totals, apply writes
pilot and squadron targets computed without it. The next read recomputes everything and
corrects it, because every target is rebuilt from the record. Recovery re-checks each
mission inside its transaction (recovery.py:240), so it does not have this gap.

**L9. Smaller items.**
- A deleted pilot row: recovery gives that pilot's restored sortie `rankId = 0` and a
  `pilotId` that points at no row (recovery.py:121-127). napalmfix skips the pilot and
  still corrects the sortie and the squadron (tested).
- `recovery.apply` returns `missions: len(todo)` even for missions it skipped as
  already restored (recovery.py:268). Cosmetic.
- `dt.datetime.utcnow()` (recovery.py:235) is deprecated from Python 3.12, and CI builds
  on 3.13. It only raises a DeprecationWarning. The fix is
  `dt.datetime.now(dt.timezone.utc)`, and it was left alone because it is not a typo.
- `_render` writes zero-valued keys (`StaticPlane=0`) and folds duplicate keys into one,
  where the game's own strings leave zeros out (Q6).
- An unreadable `.napalm.json` (bad JSON) loads as "no record" (napalmfix.py:63-71). The
  next write replaces it with a fresh record whose originals are the already-corrected
  values, and the old originals are gone.
- `napalmfix.plan` re-parses `statobjects.json` / `statreporting.json` and reads every
  type-0 event row on every career read, on top of the aggregator's own copy. This is a
  cost, not a bug.
- `/api/careers` does not run `auto_correct`. If the game writes inflated pilot totals
  back while the sorties stay corrected, `_cuts` finds nothing to cut, so the career
  list shows the inflated totals until that career's page is opened.

### Checked and found correct

- **Clean sortie:** no reduction and no write. `auto_sync` on a career without napalm
  kills creates no record and no backup.
- **Inflated sortie:** the cut equals the stored count minus the kill rows, charged to the
  leaf and its rollup.
- **Truck-mounted gun:** `min()` keeps the game's figure. A rebuilt count above the stored
  one never raises it.
- **Unknown names:** one unknown name gives one count of slack in every leaf category,
  and a blank name counts as unknown.
- **Empty or malformed killStats:** `None`, `""`, `&`, `X=`, `X=abc`, `X=1.5` and `=3`
  give no cut. `subtract()` keeps non-integer pairs as they are and never goes below 0.
- **Raildoad/Railroad:** neither spelling is ever cut on its own, because both are
  rollups. A rail leaf cut is charged to `Railroad` and spent across both spellings.
  `points()` ignores the typo, as the game does.
- **Missing squadron row:** handled, and the squadron offset stays `None`.
- **Missing pilot row:** that pilot is skipped, while the sortie and squadron are still
  corrected.
- **Idempotence:** a second run changes nothing in the file or the record and takes no
  backup. After napalmfix has written, the database read-time correction finds nothing
  left to cut, so nothing is cut twice.
- **Game writes its values back:** the same targets are written again. A new mission after
  a correction lands on the corrected totals, and its PCP points are kept.
- **File locked by the game:** an EXCLUSIVE lock means the plan cannot read, so there is
  no backup and no write. With a RESERVED or IMMEDIATE lock, apply fails and nothing is
  written, apart from the backup in M2. `restore()` on a locked file raises and rolls back
  as a whole.
- **restore():** puts back the game's sortie, pilot, squadron and PCP values, including
  after the game has added a mission, and running it twice is harmless.
- **recovery:** inserts every field as `rebuild()` computes it, lowers the napalm offsets
  by the restored kills, and the napalm run that follows corrects the restored rows.
  `restore()` deletes the rows, puts the offsets back, and drops the restored ids from
  the napalm record. With no napalm record yet, the offsets are taken after recovery and
  come out at zero.
- **Award progress** (`progress.py`) reads `_killStats_raw` when the read-time correction
  applied, and the file value otherwise. Once napalmfix has written, the file value is
  the corrected one, and that is also what the game reads next.

## What the tests cover

`tests/` has 79 tests (75 pass, 4 xfail) and runs with `python -m pytest`. pytest is not
in `requirements.txt`, so install it first with `pip install pytest`. The tests need no
game. They build SQLite files in `tmp_path` with only the columns the code queries, plus
loose `statobjects.json` / `statreporting.json` files under a fake game folder that
`AssetResolver` reads before it looks for archives. The tracker's `corrections` and
`backups` folders are redirected to `tmp_path`.

| file | covers |
|---|---|
| `test_killfix.py` | category table (case, suffixes, unknown, missing or empty files), `reductions` (clean, inflated, truck gun, unknown slack, no kill rows, malformed, rollups, rail), `subtract` (order, floor at 0, non-integers, Raildoad/Railroad spending) |
| `test_napalmfix.py` | points formula and pots, `_render`; clean career; apply with hand-computed sortie/pilot/squadron/PCP targets; second run; game overwrite; a new mission after correction; missing squadron row; missing pilot row; deleted sortie; EXCLUSIVE and IMMEDIATE locks; restore (basic, twice, no record, after a new mission, locked); unreadable record |
| `test_database_kills.py` | read-time correction of sorties, pilots and squadron with `_killStats_raw`; `kill_stats()`; no table; no second cut after napalmfix; award progress reads the raw counter; missing event table |
| `test_recovery.py` | lost-mission detection; rebuilt fields (slot pairing, kills with zeros dropped, rank minus later promotions, eventFlags, killed/lost fate); Raildoad kept; partial loss not detected; missing pilot; apply + record; napalm offset adjustment followed by a napalm run; recovery before a first napalm run; locked file; restore with offsets put back; restore with no record |

The four xfail tests are strict, so each one starts failing the suite the moment its
finding is fixed: M1, M2 and both halves of M3.

## What the tests cannot cover

- Whether `statobjects.json` / `statreporting.json` really categorise every kill-row name
  as the fixtures assume. The fixtures are a few hand-written lines, so the 266/355
  reproduction rate and the 84 inflated / 5 truck-gun split can only be checked on real
  careers.
- Whether the points formula and the `gap` invariant match the game (careerProcessor.dll),
  per pilot.
- The 701/701 recovery field match, and in particular the four fitted rules (the repair
  window, the 1% damage threshold, the status-1 era rule, the group-state condition).
  The tests only check that the code does what its docstring says on hand-built debriefs.
- The real `mission.result` encoding: the fixtures use a minimal, singly-encoded players
  section with no `damages` or `playerGroupState`.
- How the running game behaves: what it locks, whether it re-reads totals from the file,
  and when it writes them back.
- `tools/validate.py` was not run, because it reads the live installation.

## Open questions for a local session with the game data

1. **Totals in memory or from the file?** After napalmfix has written, does the game add
   the next sortie to the file's corrected totals, or write its inflated in-memory copy
   back? Compare `pilot.killStats` before and after one mission against the
   `.napalm.json` record. If it writes the memory copy back, every mission costs a
   rewrite and a backup (see M2).
2. **Journal and lock mode:** what do `PRAGMA journal_mode` and `PRAGMA locking_mode`
   report on a career file while the game has it open? If it uses WAL, the backups miss
   the `-wal` file (M2).
3. **Deleted sorties:** does the game ever set `sortie.isDeleted = 1` or delete sortie
   rows, and if so, does it lower pilot and squadron totals? (L1)
4. **Recovery false positives:** on every career, list the missions recovery would treat
   as lost and compare their dates with the escapedJail build window:
   `SELECT id, startTime FROM mission m WHERE isDeleted=0 AND result LIKE '%players=%' AND pilotsList<>'' AND NOT EXISTS (SELECT 1 FROM sortie s WHERE s.missionId=m.id)`
   A hit from before 2026-09-29 would get phantom sorties.
5. **Zero-row rebuilds:** does any mission from Q4 rebuild to zero rows, or to fewer rows
   than pilotsList has slots? (M1, L3)
6. **Format the game accepts:** does the game, and the mod's award engine, read
   killStats strings containing `Key=0` pairs, or keys in a different order, exactly as
   it reads its own? napalmfix writes both.
7. **PCP excess per pilot:** for a few pilots, does `points(original sorties) -
   points(corrected sorties)` equal the PCP the napalm sorties actually added? (L7)
8. **Rail spelling:** when a sortie has rail kills, which spelling does the game write on
   the sortie row, and is the `Raildoad` / `Railroad` split on the totals the sum of the
   sorties' own split? (L6)
9. **Undo path:** should restore() be reachable from the Career Helper or the tracker, or
   should the forum post say that the JSON records have to go too? (H1)
10. **Aircraft names:** are the aircraft names in type-0 rows (`mig15bis`, and so on)
    listed in `statobjects.json`? If not, every air kill counts as unknown slack. The "1
    unknown in 355" figure suggests they are listed.

## Change on this branch

- `recovery.py` `_fate()`: removed an unused `from .career.missionresult import _unquote`.
  Behaviour does not change.
- Added `tests/` and `pytest.ini`, which sets `testpaths = tests` and `pythonpath = .`.
  No runtime file changes, and nothing user-visible, so there is nothing to translate.
