#!/bin/bash
# Auto-update SSH config with current EC2 IP
# Usage: ./scripts/update-ssh-config.sh

set -e

echo "Fetching current EC2 IP from AWS..."

# Get current EC2 IP
CURRENT_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=reitsheet-flask-app" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

if [ "$CURRENT_IP" == "None" ] || [ -z "$CURRENT_IP" ]; then
  echo "ERROR: Could not find running EC2 instance"
  exit 1
fi

echo "Current EC2 IP: $CURRENT_IP"

# Check if SSH config has ec2-flask entry
SSH_CONFIG="$HOME/.ssh/config"

if ! grep -q "Host ec2-flask" "$SSH_CONFIG" 2>/dev/null; then
  echo "Adding ec2-flask to SSH config..."
  cat >> "$SSH_CONFIG" << EOF

Host ec2-flask
  HostName $CURRENT_IP
  User ubuntu
  IdentityFile ~/.ssh/reitsheet-flask.pem
  StrictHostKeyChecking no
EOF
  echo "✅ Added ec2-flask to $SSH_CONFIG"
else
  # Update existing entry
  echo "Updating ec2-flask IP in SSH config..."

  # Use sed to update HostName
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "/Host ec2-flask/,/^Host / s/HostName .*/HostName $CURRENT_IP/" "$SSH_CONFIG"
  else
    # Linux
    sed -i "/Host ec2-flask/,/^Host / s/HostName .*/HostName $CURRENT_IP/" "$SSH_CONFIG"
  fi

  echo "✅ Updated ec2-flask IP to $CURRENT_IP in $SSH_CONFIG"
fi

echo ""
echo "You can now deploy with: ./scripts/deploy.sh"
