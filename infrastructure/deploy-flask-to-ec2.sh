#!/bin/bash
# Deploy Flask App to EC2 - Security Hardening
# Run this script ON the EC2 instance

set -e

echo "🚀 Deploying Flask security updates to EC2..."

# Navigate to app directory
cd /home/ubuntu/infrastructure/docker/flask-app

# Pull latest changes
echo "📥 Pulling latest code..."
cd /home/ubuntu/infrastructure/docker/flask-app
git pull origin main

# Return to app directory
cd infrastructure/docker/flask-app

# Activate virtual environment
source venv/bin/activate

# Install new dependencies
echo "📦 Installing new dependencies..."
pip install Flask-WTF==1.2.1 Flask-Limiter==3.5.0 bleach==6.1.0

# Restart Flask service
echo "🔄 Restarting Flask app..."
sudo systemctl restart flask-app

# Check status
echo "✅ Checking Flask app status..."
sudo systemctl status flask-app --no-pager

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🔍 Verify with:"
echo "  curl -I https://app.reitsheet.co | grep -E 'X-Frame|CSP|HSTS'"
