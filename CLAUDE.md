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

One command, from a clean tree, signed in to Azure with the identity holding the
**Artifact Signing Certificate Profile Signer** role:

    az login
    .\tools\build_release.ps1 -Version 1.8.2 -Publish

That is the whole release. It bumps both version strings and commits them,
validates, builds, signs, packages, scans, pushes main, tags the built commit,
opens the GitHub release, uploads, **downloads the assets back and fails if the
served bytes differ from the local build**, and writes those verified checksums
into `docs/forum-post-<version>.txt`.

The only thing left by hand is posting the forum text. There is no API for it.

Useful variations:

    .\tools\build_release.ps1                      # build and sign only, no publish
    .\tools\build_release.ps1 -Version 1.8.2 -Publish -DryRun   # all but push/tag/upload
    .\tools\build_release.ps1 -SkipValidation
    .\tools\build_release.ps1 -MetadataPath "D:\secure\metadata.json"

Without `-Version` it builds whatever the .iss already says; it refuses if the
.iss and `make_release_zip.py` disagree, and it refuses to build a publish from
a dirty working tree.

### What it refuses to do

* **Replace assets on a release that has downloads.** The checksum in a posted
  forum message is a promise about specific bytes; swapping them makes it a lie.
  Ship a new version instead. `-Force` overrides, and should not be needed.
* **Call a release done without checking it.** Every build signs afresh, and an
  Authenticode signature carries a timestamp, so no two builds are byte-identical
  and hashes noted from an earlier run are stale. The script compares what GitHub
  serves against what it built, and only those hashes reach the forum post.

### The chain

0. `tools/validate.py` unless `-SkipValidation`. It reads the live installation
   and its career fixtures depend on which careers exist, but the rest is the
   source tree, and its locale checks are the only guard against shipping a key
   that reaches the reader as `KEY!LOCALIZE!`.
1. PyInstaller build
2. Azure-sign and verify **both** `IL2_Korea_Service_Record.exe` and
   `IL2_Korea_Career_Helper.exe`
3. `python tools/stage_release.py`
4. Inno Setup build; Inno invokes the same Azure signing helper for Setup and
   the generated uninstaller
5. Verify the final Setup.exe
6. `python tools/make_release_zip.py`
7. Scan both artifacts with Microsoft Defender, abort on a detection
8. Publish, verify the served bytes, write the checksums

`tools/sign_artifact.ps1` auto-selects the newest x64 Windows SDK SignTool, uses
the Artifact Signing client dlib under LocalAppData, timestamps with Microsoft's
timestamp service, and verifies every result with both SignTool and
`Get-AuthenticodeSignature`. Any signing or verification failure aborts.

The metadata file stays outside the repository (default
`C:\CodeSigning\metadata.json`) and its shape is:

    {
      "Endpoint": "https://eus.codesigning.azure.net",
      "CodeSigningAccountName": "IL2KoreaSRSigning",
      "CertificateProfileName": "IL2KoreaPublic"
    }

Do **not** commit it. It contains no private key, but it is machine/account
configuration and does not belong in the source tree.

`.github/workflows/build.yml` is intentionally an **unsigned clean-machine CI
build**. It installs stock PyInstaller from PyPI, so it proves the tree builds on
a clean runner; it never produces the public binary. It may create the release
shell on a `v*` tag — the script tolerates a release that already exists.

The ZIP contains the **signed Setup.exe** plus its README. The Setup.exe in turn
contains the already-signed tracker and Career Helper, and its generated
uninstaller is signed by Inno Setup during compilation.

The public binaries still use the **locally rebuilt PyInstaller bootloader**,
not the stock one. Defender previously flagged the stock prebuilt PyInstaller
bootloader heuristically; keep the rebuilt bootloader procedure below intact.
Any `pip install --upgrade pyinstaller` can replace those local bootloader
files, so rebuild/copy the matching bootloader before the next release if
needed.

Before posting a release, verify what GitHub actually serves:

    python tools/ci.py releases 1

and compare its digest with the hash printed by `build_release.ps1`.

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
exe's SHA-256, and `build_release.ps1` scans `installer\Output` with
`MpCmdRun -Scan -ScanType 3` as its last step.
