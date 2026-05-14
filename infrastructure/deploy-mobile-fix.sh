#!/bin/bash
#
# Emergency Mobile Fix - EC2 Deployment Script
#
# Deploys the mobile responsive CSS and OAuth fixes to EC2 production
#

set -e  # Exit on error

echo "============================================================"
echo "Emergency Mobile Fix - EC2 Deployment"
echo "============================================================"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Step 1: Pulling latest code from GitHub...${NC}"
git pull origin main

echo ""
echo -e "${BLUE}Step 2: Navigating to Flask app directory...${NC}"
cd infrastructure/docker/flask-app

echo ""
echo -e "${BLUE}Step 3: Checking for new dependencies...${NC}"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓ Dependencies up to date${NC}"
else
    echo -e "${YELLOW}⚠ No venv found, skipping dependency check${NC}"
fi

echo ""
echo -e "${BLUE}Step 4: Restarting Flask service...${NC}"
sudo systemctl restart flask-app

echo ""
echo -e "${BLUE}Step 5: Waiting for service to start...${NC}"
sleep 2

echo ""
echo -e "${BLUE}Step 6: Checking service status...${NC}"
if sudo systemctl is-active --quiet flask-app; then
    echo -e "${GREEN}✓ Flask service is running${NC}"
else
    echo -e "${YELLOW}⚠ Service may not be running, check logs${NC}"
    sudo systemctl status flask-app
    exit 1
fi

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Service Status:"
sudo systemctl status flask-app --no-pager | head -10

echo ""
echo "Recent Logs:"
sudo journalctl -u flask-app --no-pager --lines=10

echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. Visit https://app.reitsheet.co"
echo "2. Verify no green background"
echo "3. Test mobile view (DevTools → iPhone 12)"
echo "4. Test OAuth login"
echo "5. Check Companies tab"
echo ""
echo -e "${BLUE}To view live logs:${NC}"
echo "sudo journalctl -u flask-app -f"
echo ""
