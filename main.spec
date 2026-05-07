# -*- mode: python ; coding: utf-8 -*-
# Build: see BUILD.md. To bundle Chromium in the exe:
#   1. In this folder: set PLAYWRIGHT_BROWSERS_PATH=.\bundled_browsers && playwright install chromium
#   2. pyinstaller main.spec
# Then the exe is self-contained (no separate browsers folder needed).

import os

# If bundled_browsers/ exists (from "playwright install chromium" into it), include it in the exe
_bundled = os.path.join(SPECPATH, "bundled_browsers")
if os.path.isdir(_bundled):
    _datas = [(_bundled, "browsers")]
else:
    _datas = []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'gui', 'automation', 'browser_manager', 'login_handler', 'sharing_logic',
        'models', 'captcha_solver', 'app_paths',
    ],
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
    name='PoshmarkSharingBot',
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
)
