# Runtime hook to fix PyTorch DLL loading on Windows
import os
import sys

# Add torch lib directory to PATH before any torch imports
if hasattr(sys, '_MEIPASS'):
    torch_lib_path = os.path.join(sys._MEIPASS, 'torch', 'lib')
    if os.path.exists(torch_lib_path):
        # Prepend to PATH so torch DLLs are found first
        os.environ['PATH'] = torch_lib_path + os.pathsep + os.environ.get('PATH', '')
        print(f"[hook-torch] Added to PATH: {torch_lib_path}")

        # Also try to add DLL directory (Windows 10+)
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(torch_lib_path)
                print(f"[hook-torch] Added DLL directory: {torch_lib_path}")
            except Exception as e:
                print(f"[hook-torch] add_dll_directory failed: {e}")
