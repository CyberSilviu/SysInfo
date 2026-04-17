# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['ZF-Info64-Windows.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('logo ZF-Logo64.png', '.'),
    ],
    hiddenimports=['psutil', 'PIL', 'PIL.Image', 'PIL.ImageTk',
                   'urllib', 'urllib.parse', 'urllib.request', 'urllib.response',
                   'urllib.error', 'urllib.robotparser', 'pathlib'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ZF-Info64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='zf_icon.ico',
    version_file=None,
)
