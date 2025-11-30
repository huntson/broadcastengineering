#!/bin/bash
# Download the latest cobalt-name-editor.exe release to the correct location

set -e

echo "Downloading latest cobalt-name-editor.exe..."

# Download from the cobalt-name-editor-latest tag
gh release download cobalt-name-editor-latest --repo huntson/broadcastengineering --pattern "cobalt-name-editor.exe" --clobber --dir dist

echo "✓ Downloaded to dist/cobalt-name-editor.exe"
ls -lh dist/cobalt-name-editor.exe
