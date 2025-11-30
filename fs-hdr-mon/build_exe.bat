@echo off
REM Build script for FS-HDR Monitor executable
REM This script builds a standalone .exe using PyInstaller

echo ========================================
echo FS-HDR Monitor - EXE Build Script
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "app\fs_mon.py" (
    echo ERROR: fs_mon.py not found in app\ directory
    echo Please run this script from the fs-hdr-mon root directory
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
echo Checking for PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo.
echo Building executable...
cd app

REM Build the executable
pyinstaller --onefile --windowed --name "FS-HDR-Monitor" fs_mon.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    cd ..
    pause
    exit /b 1
)

cd ..

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Executable location: app\dist\FS-HDR-Monitor.exe
echo.
echo Next steps:
echo 1. Copy FS-HDR-Monitor.exe to your deployment location
echo 2. Create config.json in the same folder as the .exe
echo 3. Run FS-HDR-Monitor.exe
echo.

REM Ask if user wants to copy config-example.json
echo Would you like to copy config-example.json to dist folder? (Y/N)
set /p COPY_CONFIG=
if /i "%COPY_CONFIG%"=="Y" (
    copy app\config-example.json app\dist\config-example.json
    echo config-example.json copied to dist folder
)

echo.
echo Opening dist folder...
explorer app\dist

pause
