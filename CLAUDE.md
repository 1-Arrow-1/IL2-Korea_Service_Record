# IL-2 Korea Service Record

Career tracker for IL-2 Sturmovik: Korea plus an awards/promotions mod, shipped
together by one Inno Setup installer. Python/Flask, PyInstaller, six languages.

## i18n is part of every change, never a follow-up

Anything new that a user can read — a UI label, a pilot state, an event type,
a rank, an award, an installer message — ships in **all six languages in the
same change**. Never add English alone with a note to translate later; the
missing keys surface as raw `state.state 3`-style text in the tracker and as
`RANK6016!LOCALIZE!` in the game, and both have reached the user.

There are two separate systems, and a change often touches both:

### 1. Tracker UI strings

`korea_service_record/locales/{en,de,es,fr,ru,zh}.json` — one file per
language, identical key sets. Add the key to all six at once, then run

    python tools/validate.py

which fails on a key missing from any locale, a stray key in one, or a lost
`{placeholder}`. Installer text lives in `[CustomMessages]` in
`installer/IL2_Korea_Service_Record.iss`, one block per language — add there
too when the installer gains a message.

### 2. Game-side locale files (the mod)

The game uses its own codes: `eng ger spa fra rus chs`. Where the game has a
word for something, use the game's word — `i18n.py` `GAME_STRINGS` overlays
them. When a change needs a string the game does not have, create it:

| what               | file, one per language                              |
|--------------------|-----------------------------------------------------|
| award name         | `nsdata/assets/locale/awards.locale=<lang>.json`    |
| award description  | `nsdata/assets/awards/6xx/<id>.locale=<lang>.txt`   |
| rank name          | `nsdata/assets/locale/ranks.locale=<lang>.json`     |

Match the file's own conventions: each language uses its own equivalent
(German ranks run Leutnant to Oberst, not the American titles), and where the
stock file leaves a language in English — Spanish does for country 601 — match
that rather than be the one file that diverges.

**A new game-side file does not ship until it is listed in two places:**
`MOD_FILES` in `tools/stage_release.py` *and* the `[Files]` section of
`installer/IL2_Korea_Service_Record.iss`. Missing from either and the installer
silently omits it. Then `python tools/stage_release.py --refresh-mod`.

### Editing the game's files — and the tracker's own locales

They are UTF-8 without BOM, CRLF throughout, some with Cyrillic. Insert
textually (see `tools/add_rank_names.py`) rather than round-tripping through
`json.dumps`, which reformats every existing key and buries the real change.
Keep new text ASCII where ASCII says the same thing.

**Read them with `read_bytes().decode()`, never `read_text()`.** Universal
newlines turn CRLF into LF silently on the way in; write the result back and
the file has changed line endings while looking identical in an editor. This
bit twice in one day — once converting all six tracker locales, once shipping
a derived `awards.cfg` — and was only caught by a byte-count assertion. Assert
CRLF and no BOM after any write.

Roster headings in `korea_service_record/locales/*.json` (`roster.*`) may
carry soft hyphens (U+00AD) where a long word may break; `detail.css` sets
`hyphens: manual` on the roster `th` to honour them. `tools/measure_roster.py`
reports the table's real width per language via Chrome DevTools — use it
before claiming anything fits.

## Verifying UI work

The user runs the tracker in **English**. Reproduce reported layout problems
in English — German headings are often single words and can hide a wrapping
bug entirely. Headless Chrome renders a page for inspection:

    chrome --headless --disable-gpu --virtual-time-budget=15000 \
      --window-size=2072,11000 --screenshot=out.png \
      "http://127.0.0.1:5002/#career/<url-encoded career id>"

The route is `#career/<id>`, and the URL must be `http://` — a file path is
read as a hostname and renders an error page silently.

## Release

    pyinstaller korea_service_record.spec --noconfirm
    python tools/stage_release.py
    iscc installer\IL2_Korea_Service_Record.iss
    python tools/make_release_zip.py
    git push origin main && git push origin v1.2.3
    gh release upload v1.2.3 "installer/Output/IL2_Korea_Service_Record_Setup_v1.2.3.exe" ^
                             "installer/Output/IL-2 Korea Service Record v1.2.3.zip" --clobber

Bump `MyAppVersion` in the .iss and `VERSION` in `make_release_zip.py`
together. The zip is the setup exe plus a README and nothing else.

**The binaries are uploaded by hand, and that is deliberate.** Pushing the tag
makes `build.yml` open the GitHub release with generated notes, but it uploads
nothing: the runner installs PyInstaller from PyPI and therefore builds with
the *stock* bootloader, the fingerprint Defender keys on. Until 2026-09-23 the
workflow did upload, so v1.6.0 and v1.6.1 both served the runner's build while
the forum post quoted the checksum of the local one - the checksum a reader was
invited to verify. Check what the release actually serves before posting:

    python tools/ci.py releases 1

and compare the digest it prints against `sha256sum` of the file you built.

`stage_release.py` **without flags** copies `dist/` into
`installer/payload/tracker`; `--refresh-mod` alone refreshes only the mod
files, and Inno then packs whatever tracker build is already in the
payload — 1.4.0 shipped a 1.3.0 tracker for ten minutes that way. Verify
with `ls installer/payload/tracker/_internal/korea_service_record/locales/ranks`
(or any file the release added) before compiling.

**The PyInstaller bootloader is a local rebuild, not the stock one.** A forum
user's Defender flagged 1.3.0 as `Trojan:Script/Wacatac.C!ml` on download
(2026-09-15), and Defender here quarantined PyInstaller's own PyPI source
tarball for the same reason: the stock prebuilt bootloader binaries are the
fingerprint the heuristic keys on. `bootloader/` was compiled from the
v6.17.0 tag with MSVC (`python waf all --target-arch=64bit` under vcvars64)
and the four `run*.exe` copied over
`site-packages/PyInstaller/bootloader/Windows-64bit-intel/` (stock copies in
`stock-backup/` beside them). Any `pip install --upgrade pyinstaller` will
put the stock ones back — rebuild from the matching tag before the next
release if that happens (sources: `C:\Users\bleih\pyi-build\src`, a sparse
checkout of `bootloader/` + `PyInstaller/_shared_with_waf.py`; the full
checkout carries the flagged binaries). The zip's README prints the setup
exe's SHA-256; scan `installer\Output` with `MpCmdRun -Scan -ScanType 3`
before uploading.
