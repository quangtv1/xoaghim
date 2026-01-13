# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Windows build

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs, collect_all

block_cipher = None

# Collect all ultralytics submodules
ultralytics_imports = collect_submodules('ultralytics')

# Collect ALL torch files (data, binaries, submodules) to fix DLL loading
torch_datas, torch_binaries, torch_hiddenimports = collect_all('torch')
torchvision_datas, torchvision_binaries, torchvision_hiddenimports = collect_all('torchvision')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=torch_binaries + torchvision_binaries,
    datas=[
        ('resources', 'resources'),  # Includes resources/models/*.pt
    ] + collect_data_files('ultralytics') + torch_datas + torchvision_datas,
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
    ] + ultralytics_imports + torch_hiddenimports + torchvision_hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/hook-torch.py'],
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

# Use onedir mode for better DLL compatibility
exe = EXE(
    pyz,
    a.scripts,
    [],  # No binaries in exe for onedir mode
    exclude_binaries=True,  # Exclude binaries from exe
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

# Collect all files into a directory
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XoaGhim',
)
