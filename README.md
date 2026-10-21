# IL-2 Korea Service Record

A career companion for **Korea. IL-2 Series**: service records, awards and
ribbon racks, flight records, combat reports, the squadron's aircraft and
logistics, a war diary with the in-game newspapers, Pilot's Notes for your
aircraft, a squadron portrait, and the Career Helper for managing your
squadron. It reads the game's own career files and flight logs, and it comes
with an optional awards mod.

Free to use. Six languages: English, German, French, Spanish, Russian and
Chinese.

## Download

Get the latest version from **[Releases](../../releases/latest)**:

- `IL2_Korea_Service_Record_Setup_vX.Y.Z.exe` — the installer (recommended)
- `IL-2.Korea.Service.Record.vX.Y.Z.zip` — the same program without an
  installer

The installer, the Service Record and the Career Helper are Authenticode
signed. Each release's forum post lists the SHA-256 checksums of both files.

## Updating

Installed copies update themselves from the **Update** page in the Career
Helper. Please always run the latest version: older ones are not kept
available.

## Running alongside the game

While the Service Record is open, it corrects your career as the game
writes it. Since the game build of 29 September 2026, napalm on airfields
books the same destroyed buildings again and again, and the game pays
career points for every phantom kill; the Service Record takes them back
out seconds after each debriefing, before the next day change, so no
promotion is granted on them. That only works while it is running, so let
it start and stop with the game:

| Switch | What it does |
|---|---|
| `--companion` | Starts the Service Record quietly in the tray, without opening the browser. If it is already open, nothing happens. |
| `--quit --companion` | Closes it again after any correction in progress has finished. If you opened it yourself, it stays open. |

### With Game Companion

[Game Companion](https://github.com/izolini/GameCompanion) by izolini
starts and stops utilities such as TrackIR, CrewChief or Joystick Gremlin
together with a game. Register the Service Record as one more utility:

| Field | Value |
|---|---|
| Name | IL-2 Korea Service Record |
| Executable Path | your installation folder, `IL2_Korea_Service_Record.exe` |
| Start Arguments | `--companion` |
| Post-launch wait (ms) | `0` |
| Instant, Delay Start, Run as Administrator, Auto-restart | unchecked |
| Stop Method | **Command**, with the arguments `--quit --companion` |

Then tick it in both the launch and the stop sequence of your IL-2 Korea
card (process name `IL2Series.exe`). Use **Command**, not **Kill**: Kill
could stop the Service Record in the middle of writing to your career.

### Without Game Companion

A desktop shortcut to `IL2_Korea_Service_Record.exe --companion`, started
before the game, does the same; close it from the tray afterwards.

## Support and feedback

Questions, bug reports and suggestions are welcome in the forum thread:
[IL-2 Korea Career Service Record](https://forum.il2-series.com/topic/5241-il-2-korea-career-service-record/).
