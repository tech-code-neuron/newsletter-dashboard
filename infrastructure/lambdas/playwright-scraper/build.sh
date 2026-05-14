#!/bin/bash
# ============================================================================
# Playwright Lambda Builder
# ============================================================================
# Builds deployment package for Playwright scraper Lambda
# Includes Python dependencies and Chromium browser binaries
# Uses AST-based module discovery to automatically include all required modules.
#
# NOTE: This Lambda uses Docker image deployment for production (AWS CloudShell).
# This script is for local testing/validation only.
#
# Updated: 2026-03-19 - Added discovery-based module inclusion

set -e  # Exit on error

echo "🎬 Building Playwright Lambda deployment package..."

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_NAME="playwright-scraper"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DISCOVERY_SCRIPT="$ROOT_DIR/scripts/discover_lambda_modules.py"

PACKAGE_DIR="$SCRIPT_DIR/package"
ZIP_FILE="$SCRIPT_DIR/../playwright-scraper.zip"
SHARED_DIR="$SCRIPT_DIR/../shared"

# -----------------------------------------------------------------------------
# Step 0: Run Module Discovery (MANDATORY)
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 0: Discovering required modules ==="

if [ -f "$DISCOVERY_SCRIPT" ]; then
    python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --check-exists || {
        echo ""
        echo "ERROR: Module discovery failed - fix missing imports before building"
        exit 1
    }

    # Get the list of local directories to include
    LOCAL_DIRS=$(python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --local-dirs)
    echo "Discovered directories: $LOCAL_DIRS"
else
    echo "WARNING: Discovery script not found, using hardcoded module list"
    LOCAL_DIRS="matching persistence browser"
fi

# -----------------------------------------------------------------------------
# Clean Previous Build
# -----------------------------------------------------------------------------

echo "🧹 Cleaning previous builds..."
rm -rf "$PACKAGE_DIR"
rm -f "$ZIP_FILE"

# -----------------------------------------------------------------------------
# Create Package Directory
# -----------------------------------------------------------------------------

echo "📁 Creating package directory..."
mkdir -p "$PACKAGE_DIR"

# -----------------------------------------------------------------------------
# Install Python Dependencies
# -----------------------------------------------------------------------------

echo "📦 Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$PACKAGE_DIR" --quiet

# -----------------------------------------------------------------------------
# Install Playwright Browsers
# -----------------------------------------------------------------------------

echo "🌐 Installing Playwright Chromium..."
cd "$PACKAGE_DIR"

# Install Playwright browsers
python -m playwright install chromium

# Playwright stores browsers in ~/.cache/ms-playwright
# We need to copy them into the package
PLAYWRIGHT_CACHE="$HOME/.cache/ms-playwright"
if [ -d "$PLAYWRIGHT_CACHE" ]; then
    echo "📋 Copying Playwright browsers to package..."
    mkdir -p "$PACKAGE_DIR/.cache"
    cp -r "$PLAYWRIGHT_CACHE" "$PACKAGE_DIR/.cache/"
fi

cd "$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# Create Deployment Package
# -----------------------------------------------------------------------------

echo "📦 Creating deployment ZIP..."
cd "$PACKAGE_DIR"
zip -r "$ZIP_FILE" . -q
cd "$SCRIPT_DIR"

# Add Lambda code
echo "➕ Adding Lambda code..."
zip -g "$ZIP_FILE" handler.py -q

# Add modules (discovered automatically)
echo "➕ Adding modules ($LOCAL_DIRS)..."
for dir in $LOCAL_DIRS; do
    if [ -d "$dir" ]; then
        zip -gr "$ZIP_FILE" "$dir" -q
    fi
done

# Add shared directory (ALL shared modules)
echo "➕ Adding shared modules..."
cd "$SCRIPT_DIR/../shared"
zip -g "$ZIP_FILE" *.py -q
cd "$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# Import Validation
# -----------------------------------------------------------------------------

echo "🔍 Validating imports..."
cd "$PACKAGE_DIR"

# Validate handler imports (catches NameError, ImportError)
python3 -c "
import sys
sys.path.insert(0, '.')
import handler
print('  ✓ handler.py imports successfully')
" || { echo "❌ Import validation failed!"; exit 1; }

cd "$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# Validate ZIP Against Discovery
# -----------------------------------------------------------------------------

echo ""
echo "🔍 Validating ZIP contents against discovery..."

if [ -f "$DISCOVERY_SCRIPT" ]; then
    python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --validate-zip "$ZIP_FILE" || {
        echo ""
        echo "❌ ERROR: ZIP validation failed!"
        echo "The ZIP is missing modules that the handler imports."
        exit 1
    }
fi

# -----------------------------------------------------------------------------
# Display Results
# -----------------------------------------------------------------------------

echo ""
echo "✅ Build complete!"
echo "📦 Package: $ZIP_FILE"
echo "📊 Size: $(du -h "$ZIP_FILE" | cut -f1)"
echo ""
echo "⚠️  WARNING: Package may be large (>50MB) due to Chromium binaries"
echo "   Consider using Lambda layers for production deployment"
echo ""
