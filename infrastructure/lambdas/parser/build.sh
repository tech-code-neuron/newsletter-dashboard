#!/bin/bash
# ============================================================================
# Parser Lambda Build Script
# ============================================================================
# Uses AST-based module discovery to automatically include all required modules.
# No manual lists to maintain - the code itself is the source of truth.
#
# Usage:
#   ./build.sh           # Full build
#   ./build.sh --quick   # Skip pip install (for code-only changes)
#   ./build.sh --verbose # Debug output
#
# Added: 2026-03-19

set -e  # Exit on error

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_NAME="parser"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DISCOVERY_SCRIPT="$ROOT_DIR/scripts/discover_lambda_modules.py"

PACKAGE_DIR="$SCRIPT_DIR/package"
ZIP_FILE="$SCRIPT_DIR/${LAMBDA_NAME}-with-deps.zip"
SHARED_DIR="$SCRIPT_DIR/../shared"

# Parse arguments
QUICK_BUILD=false
VERBOSE=""
for arg in "$@"; do
    case $arg in
        --quick) QUICK_BUILD=true ;;
        --verbose|-v) VERBOSE="--verbose" ;;
    esac
done

echo "============================================="
echo "Building $LAMBDA_NAME Lambda"
echo "============================================="

# -----------------------------------------------------------------------------
# Step 1: Run Module Discovery (MANDATORY)
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 1: Discovering required modules ==="

# Verify discovery script exists
if [ ! -f "$DISCOVERY_SCRIPT" ]; then
    echo "ERROR: Discovery script not found: $DISCOVERY_SCRIPT"
    echo "Run: python3 scripts/discover_lambda_modules.py (from project root)"
    exit 1
fi

# Run from project root for correct path resolution
cd "$ROOT_DIR"

# Check that all modules exist before building
python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --check-exists $VERBOSE || {
    echo ""
    echo "ERROR: Module discovery failed - fix missing imports before building"
    exit 1
}

# Get the list of local directories to include
LOCAL_DIRS=$(python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --local-dirs)
echo "Local directories: $LOCAL_DIRS"

# Get discovery output for reference
echo ""
python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --dry-run

# -----------------------------------------------------------------------------
# Step 2: Clean Previous Build
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 2: Cleaning previous build ==="

rm -rf "$PACKAGE_DIR"
rm -f "$ZIP_FILE"
mkdir -p "$PACKAGE_DIR"

# -----------------------------------------------------------------------------
# Step 3: Install Dependencies (if not quick build)
# -----------------------------------------------------------------------------

if [ "$QUICK_BUILD" = false ]; then
    echo ""
    echo "=== Step 3: Installing Python dependencies ==="

    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$PACKAGE_DIR" --quiet --upgrade
        echo "Dependencies installed to $PACKAGE_DIR"
    else
        echo "No requirements.txt found (skipping pip install)"
    fi
else
    echo ""
    echo "=== Step 3: SKIPPED (quick build) ==="
fi

# -----------------------------------------------------------------------------
# Step 4: Copy Lambda Code
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 4: Copying Lambda code ==="

# Copy handler
cp "$SCRIPT_DIR/handler.py" "$PACKAGE_DIR/"
echo "  Copied: handler.py"

# Copy all .py files in root (parser has many standalone modules)
for py_file in "$SCRIPT_DIR"/*.py; do
    if [ -f "$py_file" ] && [ "$(basename "$py_file")" != "handler.py" ]; then
        cp "$py_file" "$PACKAGE_DIR/"
        echo "  Copied: $(basename "$py_file")"
    fi
done

# Copy local directories (discovered automatically)
for dir in $LOCAL_DIRS; do
    if [ -d "$SCRIPT_DIR/$dir" ]; then
        cp -r "$SCRIPT_DIR/$dir" "$PACKAGE_DIR/"
        # Count files
        file_count=$(find "$SCRIPT_DIR/$dir" -name "*.py" | wc -l | tr -d ' ')
        echo "  Copied: $dir/ ($file_count files)"
    fi
done

# -----------------------------------------------------------------------------
# Step 5: Copy Shared Modules
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 5: Copying shared modules ==="

mkdir -p "$PACKAGE_DIR/shared"

# Copy all shared .py files (discovery will validate which ones are actually needed)
for py_file in "$SHARED_DIR"/*.py; do
    if [ -f "$py_file" ]; then
        cp "$py_file" "$PACKAGE_DIR/shared/"
        echo "  Copied: shared/$(basename "$py_file")"
    fi
done

# -----------------------------------------------------------------------------
# Step 6: Create ZIP Package
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 6: Creating ZIP package ==="

cd "$PACKAGE_DIR"
zip -r "$ZIP_FILE" . -q
cd "$SCRIPT_DIR"

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "Created: $ZIP_FILE ($ZIP_SIZE)"

# -----------------------------------------------------------------------------
# Step 7: Import Validation (Smoke Test)
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 7: Validating imports (smoke test) ==="

cd "$PACKAGE_DIR"

python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import handler
    print('  handler.py imports successfully')
except ImportError as e:
    print(f'ERROR: Import failed: {e}')
    sys.exit(1)
except NameError as e:
    print(f'ERROR: Name error: {e}')
    sys.exit(1)
" || {
    echo ""
    echo "ERROR: Smoke test failed!"
    echo "The handler has import errors that need to be fixed."
    exit 1
}

cd "$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# Step 8: Validate ZIP Against Discovery
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 8: Validating ZIP contents ==="

# Run from project root for correct path resolution
cd "$ROOT_DIR"
python3 "$DISCOVERY_SCRIPT" "$LAMBDA_NAME" --validate-zip "$ZIP_FILE" $VERBOSE || {
    echo ""
    echo "ERROR: ZIP validation failed!"
    echo "The ZIP is missing modules that the handler imports."
    exit 1
}

# -----------------------------------------------------------------------------
# Step 9: Write Lock File (Prevents Deploying Stale ZIPs)
# -----------------------------------------------------------------------------

echo ""
echo "=== Step 9: Writing lock file ==="

# Lock file records when ZIP was built and from which git commit
# deploy_lambda.py validates this to prevent deploying old ZIPs
LOCK_FILE="$ZIP_FILE.lock"
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$BUILD_TIME $GIT_COMMIT" > "$LOCK_FILE"
echo "Lock file: $LOCK_FILE"
echo "  Built at: $BUILD_TIME"
echo "  Git commit: ${GIT_COMMIT:0:12}"

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
echo "  Deploy: python3 scripts/deploy_lambda.py $LAMBDA_NAME --deploy --zip ${LAMBDA_NAME}-with-deps.zip"
echo ""
echo "IMPORTANT: Always use deploy_lambda.py - it runs health checks after deployment."
echo "           Never upload via AWS Console (bypasses validation, caused March 2026 outage)."
echo ""
