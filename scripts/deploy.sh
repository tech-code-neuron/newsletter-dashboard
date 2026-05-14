#!/bin/bash
# One-command deploy to EC2
# Usage: ./scripts/deploy.sh
#
# IMPORTANT: This script reads deployment paths from deployment-config.json
# to ensure consistency. DO NOT hardcode paths!

set -e

# ============================================================
# MANDATORY: Run pre-commit validation before deploying
# ============================================================
echo "Running pre-commit validation..."
if ! python3 scripts/validate_pre_commit.py; then
    echo ""
    echo "❌ DEPLOYMENT BLOCKED: Pre-commit validation failed"
    echo "   Fix the issues above before deploying."
    exit 1
fi
echo ""

# ============================================================
# Load deployment configuration from JSON
# ============================================================
CONFIG_FILE="infrastructure/deployment-config.json"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ ERROR: $CONFIG_FILE not found!"
    echo "   This file is required to know where to deploy."
    exit 1
fi

# Extract deployment path from config using Python
DEPLOY_PATH=$(python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
print(config['deployment']['application']['path'])
")

RESTART_CMD=$(python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
print(config['deployment']['process_manager']['restart_command'])
")

echo "📋 Deployment Configuration:"
echo "   Target Path: $DEPLOY_PATH"
echo "   Restart: $RESTART_CMD"
echo ""

# Auto-update SSH config with current EC2 IP
./scripts/update-ssh-config.sh

echo "Deploying to EC2..."

# Sync CSS
rsync -avz --quiet \
  infrastructure/docker/flask-app/static/css/ \
  ec2-flask:$DEPLOY_PATH/static/css/

# Sync JS
rsync -avz --quiet \
  infrastructure/docker/flask-app/static/js/ \
  ec2-flask:$DEPLOY_PATH/static/js/

# Sync root static files (logo, og-image, etc.)
rsync -avz --quiet \
  infrastructure/docker/flask-app/static/*.png \
  ec2-flask:$DEPLOY_PATH/static/

# Sync templates
rsync -avz --quiet \
  infrastructure/docker/flask-app/templates/ \
  ec2-flask:$DEPLOY_PATH/templates/

# Sync routes (Python code)
rsync -avz --quiet \
  infrastructure/docker/flask-app/routes/ \
  ec2-flask:$DEPLOY_PATH/routes/

# Sync forms (Flask-WTF)
rsync -avz --quiet \
  infrastructure/docker/flask-app/forms/ \
  ec2-flask:$DEPLOY_PATH/forms/

# Sync services
rsync -avz --quiet \
  infrastructure/docker/flask-app/services/ \
  ec2-flask:$DEPLOY_PATH/services/

# Sync utils
rsync -avz --quiet \
  infrastructure/docker/flask-app/utils/ \
  ec2-flask:$DEPLOY_PATH/utils/

# Sync core
rsync -avz --quiet \
  infrastructure/docker/flask-app/core/ \
  ec2-flask:$DEPLOY_PATH/core/

# Sync config
rsync -avz --quiet \
  infrastructure/docker/flask-app/config/ \
  ec2-flask:$DEPLOY_PATH/config/

# Sync middleware (domain routing)
rsync -avz --quiet \
  infrastructure/docker/flask-app/middleware/ \
  ec2-flask:$DEPLOY_PATH/middleware/

# Sync app.py
rsync -avz --quiet \
  infrastructure/docker/flask-app/app.py \
  ec2-flask:$DEPLOY_PATH/

# Restart Flask using command from config
ssh ec2-flask "$RESTART_CMD"

echo ""
echo "Deployed successfully!"
echo ""
echo "✅ Files synced to: $DEPLOY_PATH"
echo "✅ Service restarted with: $RESTART_CMD"
echo ""

# ============================================================
# MANDATORY: Verify deployment succeeded
# ============================================================
echo "Verifying deployment..."
if ! ./scripts/verify-flask-deployment.sh; then
    echo ""
    echo "❌ DEPLOYMENT VERIFICATION FAILED"
    echo "   Files on EC2 don't match local versions!"
    echo "   This means the deployment did NOT work."
    echo ""
    exit 1
fi

echo ""
echo "🎉 Deployment verified and complete!"
