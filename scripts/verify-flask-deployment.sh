#!/bin/bash
#
# Flask Deployment Verification
# ==============================
# Verifies that files deployed to EC2 match local versions
#
# Usage: ./scripts/verify-flask-deployment.sh
#
# Returns:
#   0 = All files match
#   1 = Files differ (deployment failed)

set -e

# Use ec2-flask SSH alias (managed by update-ssh-config.sh)
EC2_HOST="ec2-flask"
REMOTE_PATH="/home/ubuntu/infrastructure/docker/flask-app"
LOCAL_PATH="infrastructure/docker/flask-app"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Verifying Flask deployment on EC2..."
echo ""

# Critical files to verify
CRITICAL_FILES=(
    "routes/review.py"
    "templates/review.html"
    "templates/login.html"
    "app.py"
    "routes/auth.py"
)

FAILURES=0

for file in "${CRITICAL_FILES[@]}"; do
    echo -n "Checking $file... "

    # Get checksums
    LOCAL_SUM=$(md5 -q "$LOCAL_PATH/$file" 2>/dev/null || echo "LOCAL_MISSING")
    REMOTE_SUM=$(ssh "$EC2_HOST" "md5sum $REMOTE_PATH/$file 2>/dev/null | awk '{print \$1}'" || echo "REMOTE_MISSING")

    if [ "$LOCAL_SUM" = "LOCAL_MISSING" ]; then
        echo -e "${RED}✗ Local file missing${NC}"
        FAILURES=$((FAILURES + 1))
    elif [ "$REMOTE_SUM" = "REMOTE_MISSING" ]; then
        echo -e "${RED}✗ Remote file missing${NC}"
        FAILURES=$((FAILURES + 1))
    elif [ "$LOCAL_SUM" != "$REMOTE_SUM" ]; then
        echo -e "${RED}✗ MISMATCH${NC}"
        echo "  Local:  $LOCAL_SUM"
        echo "  Remote: $REMOTE_SUM"
        FAILURES=$((FAILURES + 1))
    else
        echo -e "${GREEN}✓ Match${NC}"
    fi
done

echo ""

if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✅ All files verified - deployment successful${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILURES file(s) failed verification${NC}"
    echo ""
    echo "This means the deployment did NOT work properly."
    echo "Files on EC2 don't match local versions."
    echo ""
    echo "Run: ./scripts/deploy.sh --force"
    exit 1
fi
