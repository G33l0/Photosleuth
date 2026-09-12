# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build for PhotoSleuth (feature G35).

Build from the repository root:

    pip install -e ".[build]"
    pyinstaller packaging/photosleuth.spec --noconfirm --clean

The result is dist/PhotoSleuth/, which Inno Setup then packages.
One-folder is deliberate: a one-file build unpacks to a temp directory on every
launch, which makes startup slower and trips some antivirus heuristics.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
PACKAGE = ROOT / "photosleuth"
ICON = PACKAGE / "assets" / "photosleuth.ico"

sys.path.insert(0, str(ROOT))
from photosleuth import __version__  # noqa: E402

datas = [
    (str(PACKAGE / "assets"), "photosleuth/assets"),
]
# folium ships its Jinja templates and JS as package data.
datas += collect_data_files("folium")
datas += collect_data_files("branca")
# timezonefinder ships binary boundary data the geolocation checks depend on.
datas += collect_data_files("timezonefinder")

hiddenimports = [
    "photosleuth.gui",
    "photosleuth.geolocation",
    "photosleuth.gui.app",
    "photosleuth.gui.main_window",
    "photosleuth.integration",
    "PIL._tkinter_finder",
]
hiddenimports += collect_submodules("photosleuth")

# Qt modules PhotoSleuth never touches; dropping them saves ~150 MB.
# The crypto/web stacks are excluded too: nothing in PhotoSleuth imports them,
# and their PyInstaller hooks are slow and fragile.
excludes = [
    "tkinter", "matplotlib", "numpy.distutils", "pytest", "setuptools",
    "cryptography", "OpenSSL", "oauthlib", "jwt", "IPython", "notebook",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtQuick3D",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQml",
    # Map PNGs are rendered from OpenStreetMap tiles with Pillow, so the
    # WebEngine stack (~400 MB) is not needed.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoSleuth",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # no console window for the GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(ROOT / "packaging" / "version_info.txt")
    if (ROOT / "packaging" / "version_info.txt").is_file()
    else None,
)

# A second, console-attached executable so the CLI still works from cmd.exe.
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="photosleuth-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=str(ICON) if ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    exe_cli,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PhotoSleuth",
)
