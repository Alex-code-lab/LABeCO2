# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('manips_types\\manips_type.sqlite', 'manips_types'), ('data_base_GES1point5\\data_base_GES1point5.hdf5', 'data_base_GES1point5'), ('data_masse_eCO2\\data_eCO2_masse_consommable.hdf5', 'data_masse_eCO2'), ('styles\\styles.qss', 'styles'), ('images\\icon.icns', 'images'), ('data_masse_eCO2\\data_eCO2_masse_consommable.hdf5', 'data_masse_eCO2'), ('data_masse_eCO2\\empreinte_carbone_materiaux.h5', 'data_masse_eCO2'), ('images\\Logo.png', 'images')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    icon=['images\\icon.icns'],
)
