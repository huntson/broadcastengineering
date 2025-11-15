#!/bin/bash
# Download the latest cobalt-name-editor.exe release to the correct location

set -e

echo "Downloading latest cobalt-name-editor.exe..."

# Get the latest release tag
LATEST_TAG=$(gh release list --repo huntson/broadcastengineering --limit 1 | awk '{print $3}')

echo "Latest version: $LATEST_TAG"

# Download to the cobalt-name-editor directory
cd cobalt-name-editor
gh release download "$LATEST_TAG" --repo huntson/broadcastengineering --pattern "*.exe" --clobber

echo "✓ Downloaded to cobalt-name-editor/cobalt-name-editor.exe"
ls -lh cobalt-name-editor.exe
