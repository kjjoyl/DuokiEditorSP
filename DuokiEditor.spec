# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# 根据平台设置不同的路径分隔符和文件扩展名
if sys.platform == 'darwin':  # macOS
    main_path = 'duoki_editor/main.py'
    icon_path = 'duoki_editor/resources/icons/app_icon.icns'
    entitlements_path = 'entitlements.plist'
    info_plist_path = 'Info.plist'
else:  # Windows
    main_path = 'duoki_editor\\main.py'
    icon_path = 'duoki_editor\\resources\\icons\\app_icon.ico'
    entitlements_path = None
    info_plist_path = None

a = Analysis(
    [main_path],
    pathex=[],
    binaries=[],
    datas=[('duoki_editor/resources', 'duoki_editor/resources'), ('duoki_editor/config.ini', 'duoki_editor'), ('duoki_editor/constants.json', 'duoki_editor')],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtMultimedia', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore', 'PyQt6.QtNetwork', 'pandas', 'openpyxl', 'xlsxwriter', 'requests', 'pypinyin', 'PIL', 'bs4', 'selenium'],
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
    entitlements_file=entitlements_path,
    icon=icon_path if icon_path else None,
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

# macOS 特定配置
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='DuokiEditor.app',
        icon=icon_path,
        bundle_identifier='com.duokieditor.app',
        info_plist=info_plist_path,
        entitlements_file=entitlements_path,
    )
