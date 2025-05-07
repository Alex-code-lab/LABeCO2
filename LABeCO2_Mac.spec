# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('manips_types/manips_type.sqlite', 'manips_types'),
        ('data_base_GES1point5/data_base_GES1point5.hdf5', 'data_base_GES1point5'),
        ('data_masse_eCO2/data_eCO2_masse_consommable.hdf5', 'data_masse_eCO2'),
        ('data_masse_eCO2/empreinte_carbone_materiaux.h5', 'data_masse_eCO2'),
        ('styles/styles.qss', 'styles'),
        ('images/icon.icns', 'images'),
        ('images/Logo.png', 'images'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=False,                # GUI → pas de console
    disable_windowed_traceback=False,
    argv_emulation=False,         # Utile surtout pour .app signées
    icon='images/icon.icns',      # ← chaîne, pas liste
)
app = BUNDLE(
    exe,
    name='LABeCO2.app',
    icon='images/icon.icns',
    bundle_identifier='com.labeco2.LABeCO2'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LABeCO2_app'            # nom différent du binaire
)