# -*- mode: python ; coding: utf-8 -*-
# LABeCO2 — macOS app spec
# Compilé avec : pyinstaller LABeCO2_Mac.spec

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
