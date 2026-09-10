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

Console stays on. The exe is the application — there is no launcher in front of
it — so the window that prints "Serving: http://127.0.0.1:5002/" is how the
user knows it is running and how they stop it. It also means a first-release
bug report arrives with a traceback attached.
"""

from pathlib import Path

base = Path(SPECPATH)
package = base / "korea_service_record"

datas = [
    # The whole front end: index.html, css, js, and images — flags, the eight
    # aircraft, the stamps, the paper texture, the photo frame.
    (str(package / "static"), "korea_service_record/static"),
    # UI strings for the six languages. The game's own locale files are read
    # from the installation at runtime and are deliberately not bundled.
    (str(package / "locales"), "korea_service_record/locales"),
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
]

excludes = [
    # numpy is a build-time dependency of tools/make_paper.py and
    # tools/make_plane_art.py, which generate artwork that ships as PNG.
    # Nothing at runtime imports it, and it is 30 MB.
    "numpy",
    "matplotlib",
    "pandas",
    "pytest",
    "tkinter",
]

a = Analysis(
    ["run.py"],
    pathex=[str(base)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

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
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IL2_Korea_Service_Record",
)
