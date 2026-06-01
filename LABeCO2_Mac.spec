# -*- mode: python ; coding: utf-8 -*-
# LABeCO2 — macOS app spec
# Compilé avec : pyinstaller LABeCO2_Mac.spec

# ─────────────────────────────────────────────────────────────────────
# Filtrage des modules Qt inutiles (gain ~500 MB sur le bundle final)
# ─────────────────────────────────────────────────────────────────────
# PySide6 6.4+ embarque QtWebEngineCore (Chromium) qui pèse 446 MB à lui
# seul, plus QtQuick/Qt3D/QtMultimedia etc. LABeCO2 n'utilise que
# QtCore + QtGui + QtWidgets. Mettre ces modules dans `excludes` ne suffit
# PAS (Qt charge ses libs en runtime) : il faut filtrer manuellement
# a.binaries et a.datas après l'Analysis.
_QT_FRAMEWORKS_TO_EXCLUDE = (
    # Le gros morceau : 446 MB
    'QtWebEngine', 'QtWebChannel', 'QtWebSockets', 'QtWebView',
    # 3D, Quick, QML
    'Qt3D', 'QtQuick', 'QtQml', 'QtShaderTools',
    # Multimédia & spatial
    'QtMultimedia', 'QtSpatialAudio', 'QtTextToSpeech',
    # Géo
    'QtPositioning', 'QtLocation',
    # PDF
    'QtPdf',
    # Connectivité périphérique
    'QtBluetooth', 'QtNfc', 'QtSerialPort', 'QtSerialBus', 'QtSensors',
    # Visu non-utilisée par LABeCO2 (on fait du matplotlib)
    'QtDataVisualization', 'QtCharts',
    # Workflow / état
    'QtScxml', 'QtStateMachine', 'QtRemoteObjects',
    # Outillage de dev (Designer, etc.)
    'QtDesigner', 'QtUiTools',
)


def _exclude_qt(path: str) -> bool:
    return any(kw in path for kw in _QT_FRAMEWORKS_TO_EXCLUDE)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # --- Base SQLite de référence ---
        ('data/labeco2_reference.sqlite', 'data'),

        # --- Base SQLite types de manips ---
        ('scenarios/manips_type.sqlite', 'scenarios'),

        # --- Interface ---
        ('styles/styles.qss',  'styles'),
        ('assets/Logo.png',    'assets'),
        ('assets/icon.icns',   'assets'),
    ],
    hiddenimports=[
        # NumPy 2.x
        'numpy.core',
        'numpy.core.multiarray',
        'numpy.core.numeric',
        'numpy.core.umath',
        'numpy._core',
        'numpy._core.multiarray',
        'numpy._core.numeric',
        'numpy._core.umath',
        # Pandas
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.timestamps',
        # SQLite
        'ui.sqlite_legacy_adapter',
        'ui.sqlite_writer',
        # Matplotlib backend Qt
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt5agg',
        # adjustText (chevauchement étiquettes graphiques) — import indirect
        # depuis ui/charts/{bar_chart_proportional,bar_chart_price_mass,pie_chart}.py
        'adjustText',
    ],
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
# Doit être fait APRÈS Analysis. Réduit le bundle de ~500 MB sur macOS.
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
    icon='assets/icon.icns',
)

app = BUNDLE(
    exe,
    name='LABeCO2.app',
    icon='assets/icon.icns',
    bundle_identifier='com.labeco2.LABeCO2',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LABeCO2_app',
)
