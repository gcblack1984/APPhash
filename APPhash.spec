# -*- mode: python ; coding: utf-8 -*-
# Compilazione di APPhash in modalita' "onedir": APPhash.exe con le librerie
# affiancate nella cartella _internal (avvio piu' rapido del file unico).
#
#   pyinstaller --noconfirm --clean APPhash.spec

a = Analysis(
    ['apphash.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/apphash.ico', '.'),
        ('assets/apphash.png', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='APPhash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/apphash.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='APPhash',
)
