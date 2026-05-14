#!/bin/bash
# ============================================================================
# Newsletter Signup Lambda Build Script
# ============================================================================
# Simple build script for newsletter-signup Lambda.
# No complex module discovery needed - this is a standalone Lambda.
#
# Usage:
#   ./build.sh           # Full build
#   ./build.sh --quick   # Skip pip install (for code-only changes)
#
# Added: 2026-03-26

set -e  # Exit on error

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_NAME="newsletter-signup"

PACKAGE_DIR="$SCRIPT_DIR/package"
ZIP_FILE="$SCRIPT_DIR/${LAMBDA_NAME}.zip"

# Parse arguments
QUICK_BUILD=false
for arg in "$@"; do
    case $arg in
        --quick) QUICK_BUILD=true ;;
    esac
done

echo "============================================="
echo "Building $LAMBDA_NAME Lambda"
echo "============================================="

# -----------------------------------------------------------------------------
# Step 1: Clean Previous Build
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 1: Cleaning previous build ==="

rm -rf "$PACKAGE_DIR"
rm -f "$ZIP_FILE"
mkdir -p "$PACKAGE_DIR"

# -----------------------------------------------------------------------------
# Step 2: Install Dependencies (if not quick build)
# -----------------------------------------------------------------------------

if [ "$QUICK_BUILD" = false ]; then
    echo ""
    echo "=== Step 2: Installing Python dependencies ==="

    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$PACKAGE_DIR" --quiet --upgrade
        echo "Dependencies installed to $PACKAGE_DIR"
    else
        echo "No requirements.txt found (skipping pip install)"
    fi
else
    echo ""
    echo "=== Step 2: SKIPPED (quick build) ==="
fi

# -----------------------------------------------------------------------------
# Step 3: Copy Lambda Code
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 3: Copying Lambda code ==="

# Copy handler
cp "$SCRIPT_DIR/handler.py" "$PACKAGE_DIR/"
echo "  Copied: handler.py"

# -----------------------------------------------------------------------------
# Step 4: Create ZIP Package
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 4: Creating ZIP package ==="

cd "$PACKAGE_DIR"
zip -r "$ZIP_FILE" . -q
cd "$SCRIPT_DIR"

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "Created: $ZIP_FILE ($ZIP_SIZE)"

# -----------------------------------------------------------------------------
# Step 5: Syntax Validation
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 5: Validating syntax ==="

python3 -m py_compile "$SCRIPT_DIR/handler.py" && echo "  handler.py syntax OK"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo ""
echo "============================================="
echo "Build Complete!"
echo "============================================="
echo ""
echo "Package: $ZIP_FILE"
echo "Size: $ZIP_SIZE"
echo ""
echo "Next steps:"
echo "  1. Apply Terraform: cd infrastructure/terraform && terraform apply"
echo "  2. Or manual deploy: aws lambda update-function-code --function-name reitsheet-newsletter-signup --zip-file fileb://$ZIP_FILE"
echo ""
