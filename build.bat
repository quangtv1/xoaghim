@echo off
REM Build script for Windows
REM Run this on a Windows machine

echo ========================================
echo    Xoa Vet Ghim - Windows Build
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Create virtual environment if not exists
if not exist "venv" (
    echo [1/5] Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo [2/5] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo [3/5] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

REM Build executable
echo [4/5] Building executable...
pyinstaller build_windows.spec --clean

REM Done
echo.
echo [5/5] Build complete!
echo.
echo Output: dist\XoaVetGhim.exe
echo.
pause
