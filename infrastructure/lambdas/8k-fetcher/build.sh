#!/bin/bash
# Build 8k-fetcher Lambda deployment package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
ZIP_NAME="8k-fetcher-with-deps.zip"

echo "Building 8k-fetcher Lambda..."

# Clean build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install dependencies
pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$BUILD_DIR" --quiet

# Copy handler
cp "$SCRIPT_DIR/handler.py" "$BUILD_DIR/"

# Create ZIP
cd "$BUILD_DIR"
zip -r "../$ZIP_NAME" . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*"

echo "Created: $SCRIPT_DIR/$ZIP_NAME"

# Cleanup
rm -rf "$BUILD_DIR"
