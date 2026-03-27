# -*- mode: python ; coding: utf-8 -*-
# LABeCO2 — Windows onefile spec
# Compilé avec : LABeCO2_env\Scripts\pyinstaller LABeCO2_windows.spec

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # --- Base de données GES1point5 ---
        ('data_base_GES1point5\\data_base_GES1point5.hdf5',  'data_base_GES1point5'),

        # --- Base de données masse / consommables ---
        ('data_masse_eCO2\\data_eCO2_masse_consommable.hdf5',   'data_masse_eCO2'),
        ('data_masse_eCO2\\data_eCO2_liquides_consommable.hdf5', 'data_masse_eCO2'),
        ('data_masse_eCO2\\empreinte_carbone_materiaux.h5',      'data_masse_eCO2'),
        ('data_masse_eCO2\\empreinte_carbone_solvants.h5',       'data_masse_eCO2'),
        ('data_masse_eCO2\\materiaux_labo.h5',                   'data_masse_eCO2'),
        ('data_masse_eCO2\\nacres_2022.h5',                      'data_masse_eCO2'),

        # --- Base SQLite types de manips ---
        ('manips_types\\manips_type.sqlite', 'manips_types'),

        # --- Interface ---
        ('styles\\styles.qss',  'styles'),
        ('images\\Logo.png',    'images'),
        ('images\\icon.ico',    'images'),
    ],
    hiddenimports=[
        # PyTables / HDF5
        'tables',
        'tables.flavor',
        'tables.leaf',
        'tables.array',
        'tables.carray',
        'tables.earray',
        'tables.vlarray',
        'tables.group',
        'tables.table',
        'tables.indexes',
        'tables.nodes.filenode',
        'numexpr',
        'numexpr.necompiler',
        'blosc2',
        # NumPy 2.x — numpy.core est réorganisé en numpy._core
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
    icon=['images\\icon.ico'],
)
