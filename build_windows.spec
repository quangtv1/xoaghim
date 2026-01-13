# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Windows build

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all ultralytics submodules
ultralytics_imports = collect_submodules('ultralytics')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources', 'resources'),  # Includes resources/models/*.pt
    ] + collect_data_files('ultralytics'),
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
        # YOLO / Ultralytics
        'ultralytics',
        'ultralytics.nn',
        'ultralytics.nn.tasks',
        'ultralytics.engine',
        'ultralytics.engine.model',
        'ultralytics.engine.predictor',
        'ultralytics.engine.results',
        'ultralytics.models',
        'ultralytics.models.yolo',
        'ultralytics.models.yolo.detect',
        'ultralytics.utils',
        'ultralytics.data',
        'ultralytics.cfg',
        # HuggingFace
        'huggingface_hub',
        'huggingface_hub.hf_api',
        'huggingface_hub.file_download',
        # PyTorch (CPU)
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'torch.utils',
        'torch.utils.data',
        'torchvision',
        'torchvision.ops',
        # Config/Utils
        'yaml',
        'scipy',
        'scipy.ndimage',
        'requests',
        'tqdm',
        'matplotlib',
        'pandas',
        'seaborn',
        'psutil',
    ] + ultralytics_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tensorflow',
        'tensorboard',
        'keras',
    ],
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
    name='XoaGhim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Enable console to see errors (can disable later)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='resources/icon.ico',  # Uncomment if you have an icon file
)
