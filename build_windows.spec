# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Windows build - ONNX Runtime version
# No PyTorch dependencies - uses ONNX for YOLO inference

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

block_cipher = None

# Collect onnxruntime data files
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all('onnxruntime')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=onnx_binaries,
    datas=[
        ('resources', 'resources'),  # Includes resources/models/*.onnx
    ] + onnx_datas,
    hiddenimports=[
        # PyQt5
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # Image processing
        'cv2',
        'numpy',
        'fitz',
        'PIL',
        'PIL.Image',
        # Geometry
        'shapely',
        'shapely.geometry',
        'shapely.ops',
        'shapely.validation',
        # ONNX Runtime
        'onnxruntime',
        # Config/Utils
        'yaml',
        'requests',
        'tqdm',
        'psutil',
    ] + onnx_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude PyTorch and related
        'torch',
        'torchvision',
        'ultralytics',
        'tensorflow',
        'tensorboard',
        'keras',
        'scipy',
        'matplotlib',
        'pandas',
        'seaborn',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single exe mode (simpler distribution)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='XoaGhim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Enable console for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
