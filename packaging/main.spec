# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.', './windows', './utils'],
    binaries=[
        ('/opt/homebrew/Cellar/python@3.11/3.11.11/Frameworks/Python.framework/Versions/3.11/Python', '.'),
        ('/opt/homebrew/lib/libhdf5.dylib', '.'), 
        ('/opt/homebrew/lib/libhdf5_hl.dylib', '.')
    ],
    datas=[
        ('data_base_GES1point5/data_base_GES1point5.hdf5', 'data_base_GES1point5'),
        ('images/Logo.png', 'images'),
    ],
    hiddenimports=[
            'tables', 
            'tables._comp_bzip2', 
            'tables._comp_lzo', 
            'pandas.io.pytables',
            'pkg_resources._vendor.jaraco.functools',
            'pkg_resources._vendor.jaraco.context',
            'pkg_resources._vendor.jaraco.text'
        ],
    hookspath=['.'],  # Chemin du hook personnalisé
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)