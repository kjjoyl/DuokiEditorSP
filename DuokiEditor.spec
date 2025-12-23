# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['duoki_editor\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('duoki_editor/resources', 'duoki_editor/resources'), ('duoki_editor/config.ini', 'duoki_editor'), ('duoki_editor/constants.json', 'duoki_editor')],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtMultimedia', 'pypinyin', 'pandas', 'openpyxl', 'requests'],
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
    [],
    exclude_binaries=True,
    name='DuokiEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['duoki_editor\\resources\\icons\\app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DuokiEditor',
)
