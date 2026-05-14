#!/bin/bash
set -e

echo "============================================="
echo "Building rss-scheduler Lambda"
echo "============================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Clean
rm -rf package rss-scheduler.zip

# Install dependencies
echo "Installing dependencies..."
pip3 install -r requirements.txt -t package --quiet

# Copy handler
cp handler.py package/

# Create ZIP
echo "Creating ZIP..."
cd package
zip -r ../rss-scheduler.zip . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*"
cd ..

# Report
ZIP_SIZE=$(du -h rss-scheduler.zip | cut -f1)
echo ""
echo "============================================="
echo "Build complete: rss-scheduler.zip ($ZIP_SIZE)"
echo "============================================="
echo ""
echo "Deploy with: terraform apply"
