# -*- mode: python ; coding: utf-8 -*-
# LABeCO2 — Windows onefile spec
# Compilé avec : pyinstaller --clean LABeCO2_windows.spec

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)

from PyInstaller.utils.hooks import collect_all

numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all('numpy')
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all('pandas')

# ─────────────────────────────────────────────────────────────────────
# Filtrage des modules Qt inutiles (gain ~300-500 MB sur le bundle final)
# ─────────────────────────────────────────────────────────────────────
# PySide6 6.4+ embarque QtWebEngineCore (Chromium) qui pèse plusieurs
# centaines de Mo à lui seul, plus QtQuick/Qt3D/QtMultimedia etc. LABeCO2
# n'utilise que QtCore + QtGui + QtWidgets. Mettre ces modules dans
# `excludes` ne suffit PAS (Qt charge ses libs en runtime) : il faut
# filtrer manuellement a.binaries et a.datas après l'Analysis.
_QT_FRAMEWORKS_TO_EXCLUDE = (
    # Le gros morceau : QtWebEngine (Chromium)
    'QtWebEngine', 'QtWebChannel', 'QtWebSockets', 'QtWebView',
    'Qt6WebEngine', 'Qt6WebChannel', 'Qt6WebSockets',
    # 3D, Quick, QML
    'Qt3D', 'QtQuick', 'QtQml', 'QtShaderTools',
    'Qt63D', 'Qt6Quick', 'Qt6Qml', 'Qt6ShaderTools',
    # Multimédia & spatial
    'QtMultimedia', 'QtSpatialAudio', 'QtTextToSpeech',
    'Qt6Multimedia', 'Qt6SpatialAudio', 'Qt6TextToSpeech',
    # Géo
    'QtPositioning', 'QtLocation',
    'Qt6Positioning', 'Qt6Location',
    # PDF
    'QtPdf', 'Qt6Pdf',
    # Connectivité périphérique
    'QtBluetooth', 'QtNfc', 'QtSerialPort', 'QtSerialBus', 'QtSensors',
    'Qt6Bluetooth', 'Qt6Nfc', 'Qt6SerialPort', 'Qt6SerialBus', 'Qt6Sensors',
    # Visu non-utilisée par LABeCO2 (on fait du matplotlib)
    'QtDataVisualization', 'QtCharts',
    'Qt6DataVisualization', 'Qt6Charts',
    # Workflow / état
    'QtScxml', 'QtStateMachine', 'QtRemoteObjects',
    'Qt6Scxml', 'Qt6StateMachine', 'Qt6RemoteObjects',
    # Outillage de dev (Designer, etc.)
    'QtDesigner', 'QtUiTools',
    'Qt6Designer', 'Qt6UiTools',
)


def _exclude_qt(path: str) -> bool:
    return any(kw in path for kw in _QT_FRAMEWORKS_TO_EXCLUDE)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[] + numpy_binaries + pandas_binaries,
    datas=[
        # --- Base SQLite de référence ---
        ('data\\labeco2_reference.sqlite', 'data'),

        # --- Base SQLite types de manips ---
        ('scenarios\\manips_type.sqlite', 'scenarios'),

        # --- Interface ---
        ('styles\\styles.qss',  'styles'),
        ('assets\\Logo.png',    'assets'),
        ('assets\\icon.ico',    'assets'),
    ] + numpy_datas + pandas_datas,
    hiddenimports=[
        # SQLite
        'ui.sqlite_legacy_adapter',
        'ui.sqlite_writer',
        # Matplotlib backend Qt
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt5agg',
        # adjustText (chevauchement étiquettes graphiques) — import indirect
        # depuis ui/charts/{bar_chart_proportional,bar_chart_price_mass,pie_chart}.py
        'adjustText',
    ] + numpy_hiddenimports + pandas_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PyQt5',
        'PyQt6',
        'wx',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)

# ─── Filtrage des binaires & datas Qt inutiles ─────────────────────────
# Doit être fait APRÈS Analysis. Réduit le bundle sensiblement.
a.binaries = [b for b in a.binaries if not _exclude_qt(b[1])]
a.datas = [d for d in a.datas if not _exclude_qt(d[1])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LABeCO2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
