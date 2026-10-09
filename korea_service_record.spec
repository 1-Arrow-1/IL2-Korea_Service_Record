# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build for the IL-2 Korea Service Record.

    pyinstaller korea_service_record.spec --noconfirm

Produces dist/IL2_Korea_Service_Record/, which is what the Inno Setup script
installs. One-directory rather than one-file: a one-file build unpacks itself
to a temporary folder on every launch, which for a 40 MB payload is a visible
delay each time the user opens their record, and it defeats the on-disk caches
the tracker keeps between runs.

Data layout matters here. Flask resolves ``static_folder="static"`` against the
package directory, and ``i18n.LOCALES_DIR`` is ``Path(__file__).parent /
"locales"``. Both therefore have to land *inside* korea_service_record/ in the
bundle, not at its root, or the app starts and then serves nothing.

Console off. A black terminal behind the browser window looks like a mistake to
anyone who did not build it, so the exe is windowed — but the console was doing
real work, and run.py replaces each part of it: a tray icon to show the server
is up and to quit it, a log file under %LOCALAPPDATA% so bug reports still
carry a traceback, and a check on startup that catches a second launch. See its
module docstring. Run it under Python, or pass --console, to get the terminal
back for development.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

base = Path(SPECPATH)
package = base / "korea_service_record"

datas = [
    # The whole front end: index.html, css, js, and images — flags, the eight
    # aircraft, the stamps, the paper texture, the photo frame.
    (str(package / "static"), "korea_service_record/static"),
    # UI strings for the six languages. The game's own locale files are read
    # from the installation at runtime and are deliberately not bundled.
    (str(package / "locales"), "korea_service_record/locales"),
    # Lightweight U-2-Net weights used only by the Career Helper's custom
    # portrait editor. The adjacent Apache-2.0 license is bundled with them.
    (str(package / "models"), "korea_service_record/models"),
    # The tray icon loads this at runtime. The copy Windows shows on the exe
    # itself is embedded separately, below.
    (str(base / "installer" / "IL2_Korea_Service_Record.ico"), "."),
    (str(base / "vendor" / "directxtex" / "LICENSE.txt"),
     "licenses/directxtex"),
    (str(base / "vendor" / "onnxruntime"), "licenses/onnxruntime"),
]
# OpenCC's conversion tables (JSON config and dictionaries, read at runtime):
# the Chinese personnel file turns the game's simplified Chinese into the
# traditional characters of 1951. Without them the file stays simplified.
datas += collect_data_files("opencc")

binaries = [
    # The helper calls this directly to produce the game's known-good
    # 512x512 BC7_UNORM / three-mip DDS format.
    (str(base / "vendor" / "directxtex" / "texconv.exe"), "."),
]

hiddenimports = [
    "flask",
    "werkzeug",
    "jinja2",
    "sqlite3",
    "PIL",
    "PIL.Image",
    # The rank, award and squadron artwork is BC7 inside DX10 DDS atlases;
    # without this plugin every emblem 404s and the page looks unstyled.
    "PIL.DdsImagePlugin",
    # The tray icon. pystray picks its backend at import time by platform, so
    # the Windows one is never reachable by static analysis.
    "pystray",
    "pystray._win32",
    "PIL.IcoImagePlugin",
    # imported inside hanzi._converter() only
    "opencc",
]

excludes = [
    # numpy WAS excluded here as a build-time-only dependency. It is not one
    # any more: the roll on a ribbon and on a drape (ribbons.roll,
    # medals.roll) and every measurement the shadowbox takes of a piece of
    # art go through it. Excluding it built an exe that served the page and
    # the atlas slices perfectly and then returned 500 for every composed
    # medal - which source runs never show, because numpy is installed here.
    "matplotlib",
    "pandas",
    "pytest",
]

a = Analysis(
    ["run.py"],
    pathex=[str(base)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# The Career Helper: a second, windowed exe in the same folder, sharing the
# package, the bundled data and the _internal libraries (tkinter included -
# the tracker never imports it, but a second COLLECT would double the size).
helper = Analysis(
    ["career_helper.py"],
    pathex=[str(base)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports + [
        "PIL.ImageTk",
        "onnxruntime",
        "onnxruntime.capi._pybind_state",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[e for e in excludes if e != "tkinter"],
    noarchive=False,
)
MERGE((a, "run", "IL2_Korea_Service_Record"), (helper, "career_helper", "IL2_Korea_Career_Helper"))

pyz = PYZ(a.pure, a.zipped_data)
helper_pyz = PYZ(helper.pure, helper.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IL2_Korea_Service_Record",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Drawn by tools/make_icon.py. Windows reads the sizes it wants straight
    # out of the exe, so the Start Menu shortcut and the taskbar get it
    # without the installer having to point at anything.
    icon=str(base / "installer" / "IL2_Korea_Service_Record.ico"),
)

helper_exe = EXE(
    helper_pyz,
    helper.scripts,
    [],
    exclude_binaries=True,
    name="IL2_Korea_Career_Helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(base / "installer" / "IL2_Korea_Service_Record.ico"),
)

coll = COLLECT(
    exe,
    helper_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    helper.binaries,
    helper.zipfiles,
    helper.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IL2_Korea_Service_Record",
)
