# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('resources', 'resources')],
    hiddenimports=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'cv2', 'numpy', 'fitz', 'PIL', 'PIL.Image', 'shapely', 'shapely.geometry', 'onnxruntime', 'yaml', 'requests', 'tqdm', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'ultralytics', 'tensorflow', 'tensorboard', 'keras', 'scipy', 'matplotlib', 'pandas', 'seaborn'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XoaGhim-1.1.14',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XoaGhim-1.1.14',
)
app = BUNDLE(
    coll,
    name='XoaGhim-1.1.14.app',
    icon=None,
    bundle_identifier=None,
)
