#!/bin/bash
# Build 8k-processor Lambda deployment package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
ZIP_NAME="8k-processor-with-deps.zip"

echo "Building 8k-processor Lambda..."

# Clean build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install dependencies
pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$BUILD_DIR" --quiet

# Copy handler
cp "$SCRIPT_DIR/handler.py" "$BUILD_DIR/"

# Copy shared modules
SHARED_DIR="$SCRIPT_DIR/../shared"
mkdir -p "$BUILD_DIR/shared"
cp "$SHARED_DIR"/*.py "$BUILD_DIR/shared/"
echo "Copied shared modules"

# Smoke test imports
cd "$BUILD_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import handler
    print('handler.py imports successfully')
except ImportError as e:
    print(f'ERROR: Import failed: {e}')
    sys.exit(1)
" || { echo 'Smoke test failed!'; exit 1; }
cd "$SCRIPT_DIR"

# Create ZIP
cd "$BUILD_DIR"
zip -r "../$ZIP_NAME" . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*"

echo "Created: $SCRIPT_DIR/$ZIP_NAME"

# Cleanup
rm -rf "$BUILD_DIR"
