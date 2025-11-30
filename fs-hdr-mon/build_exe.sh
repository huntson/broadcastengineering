#!/bin/bash
# Build script for FS-HDR Monitor executable
# This script builds a standalone executable using PyInstaller

echo "========================================"
echo "FS-HDR Monitor - Build Script"
echo "========================================"
echo

# Check if we're in the right directory
if [ ! -f "app/fs_mon.py" ]; then
    echo "ERROR: fs_mon.py not found in app/ directory"
    echo "Please run this script from the fs-hdr-mon root directory"
    exit 1
fi

# Check if PyInstaller is installed
echo "Checking for PyInstaller..."
python3 -c "import PyInstaller" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyInstaller not found. Installing..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install PyInstaller"
        exit 1
    fi
fi

echo
echo "Building executable..."
cd app

# Build the executable
pyinstaller --onefile --windowed --name "FS-HDR-Monitor" fs_mon.py

if [ $? -ne 0 ]; then
    echo
    echo "ERROR: Build failed!"
    cd ..
    exit 1
fi

cd ..

echo
echo "========================================"
echo "Build Complete!"
echo "========================================"
echo
echo "Executable location: app/dist/FS-HDR-Monitor"
echo
echo "Next steps:"
echo "1. Copy FS-HDR-Monitor to your deployment location"
echo "2. Create config.json in the same folder as the executable"
echo "3. Run ./FS-HDR-Monitor"
echo

# Copy config-example.json to dist
cp app/config-example.json app/dist/config-example.json
echo "config-example.json copied to dist folder"
echo
