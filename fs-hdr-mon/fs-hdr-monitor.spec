# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app/fs_mon.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/config-example.json', '.'),
        ('app/license/lic_public.key', 'license'),
        ('VERSION', '.'),
    ],
    hiddenimports=[
        'flask',
        'requests',
        'threading',
        'json',
        'tkinter',
        'tkinter.scrolledtext',
        'nacl.signing',
        'nacl.encoding',
        'nacl.exceptions',
        '_cffi_backend',
        'gui',
        'gui_dialogs',
        'license',
    ],
    hookspath=[],
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
    name='FS-HDR-Monitor',
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
    icon='icon.ico',
)
