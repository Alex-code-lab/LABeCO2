# -*- mode: python ; coding: utf-8 -*-
# LABeCO2 — Windows onefile spec
# Compilé avec : pyinstaller --clean LABeCO2_windows.spec

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)

from PyInstaller.utils.hooks import collect_all

numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all('numpy')
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all('pandas')

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
