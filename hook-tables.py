from PyInstaller.utils.hooks import collect_all
import os

datas, binaries, hiddenimports = collect_all('tables')

# Ajouter manuellement les bibliothèques Blosc
blosc_libs = [
    '/opt/homebrew/lib/libblosc.dylib',
    '/opt/homebrew/lib/libblosc.2.dylib',
    '/opt/homebrew/lib/libblosc.2.dylib',
    '/opt/homebrew/lib/libblosc2.dylib',
    '/opt/homebrew/lib/libblosc2.4.dylib',
]

for lib in blosc_libs:
    if os.path.exists(lib):
        binaries.append((lib, '.'))

# Ajouter les bibliothèques HDF5
hdf5_libs = [
    '/opt/homebrew/lib/libhdf5.dylib',
    '/opt/homebrew/lib/libhdf5_hl.dylib',
]

for lib in hdf5_libs:
    if os.path.exists(lib):
        binaries.append((lib, '.'))

# Ajouter les bibliothèques Blosc supplémentaires si présentes
additional_blosc_libs = [
    '/opt/homebrew/lib/libblosc.dylib',
    '/opt/homebrew/lib/libblosc2.dylib',
]

for lib in additional_blosc_libs:
    if os.path.exists(lib):
        binaries.append((lib, '.'))