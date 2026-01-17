# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Windows build - Version 1.1.20
# Builds to folder with all DLLs included for proper ONNX Runtime support

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all, collect_dynamic_libs

block_cipher = None

# Collect onnxruntime - ensure all DLLs are included
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all('onnxruntime')

# Also collect dynamic libs explicitly
onnx_dynamic_libs = collect_dynamic_libs('onnxruntime')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=onnx_binaries + onnx_dynamic_libs,
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
        'onnxruntime.capi',
        'onnxruntime.capi._pybind_state',
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

# Onedir mode - creates folder with all DLLs
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # Important: binaries go to COLLECT
    name='XoaGhim-1.1.20',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Hide console window (GUI only)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# COLLECT creates the output folder with all dependencies
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XoaGhim-1.1.20',
)
