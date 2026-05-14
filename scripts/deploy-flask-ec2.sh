#!/bin/bash
# ============================================================================
# Deploy Flask App to EC2
# ============================================================================
# Simple SSH-based deployment - replaces 5-minute Docker/ECS workflow
#
# Usage:
#   ./scripts/deploy-flask-ec2.sh              # Deploy from current branch
#   ./scripts/deploy-flask-ec2.sh main         # Deploy specific branch
#   ./scripts/deploy-flask-ec2.sh --status     # Check service status
#   ./scripts/deploy-flask-ec2.sh --logs       # View recent logs
#   ./scripts/deploy-flask-ec2.sh --restart    # Just restart (no git pull)

set -e

# Use ec2-flask SSH alias (configured by update-ssh-config.sh)
# Run ./scripts/update-ssh-config.sh first if SSH fails
EC2_HOST="ec2-flask"
APP_DIR="/home/ubuntu/infrastructure/docker/flask-app"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# SSH command helper
ssh_cmd() {
    ssh "$EC2_HOST" "$@"
}

# Parse arguments
ACTION="deploy"
BRANCH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --status)
            ACTION="status"
            shift
            ;;
        --logs)
            ACTION="logs"
            shift
            ;;
        --restart)
            ACTION="restart"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options] [branch]"
            echo ""
            echo "Options:"
            echo "  --status    Show service status"
            echo "  --logs      Show recent application logs"
            echo "  --restart   Restart without git pull"
            echo "  --help      Show this help"
            echo ""
            echo "Examples:"
            echo "  $0              Deploy from current branch"
            echo "  $0 main         Deploy specific branch"
            echo "  $0 --logs       View recent logs"
            exit 0
            ;;
        *)
            BRANCH="$1"
            shift
            ;;
    esac
done

# Execute action
case $ACTION in
    status)
        echo -e "${YELLOW}Checking Flask app status...${NC}"
        ssh_cmd "sudo systemctl status flask-app --no-pager"
        ;;

    logs)
        echo -e "${YELLOW}Recent Flask app logs:${NC}"
        ssh_cmd "sudo journalctl -u flask-app -n 50 --no-pager"
        ;;

    restart)
        echo -e "${YELLOW}Restarting Flask app...${NC}"
        START_TIME=$SECONDS
        ssh_cmd "sudo systemctl restart flask-app"
        echo -e "${GREEN}Restarted in $((SECONDS - START_TIME)) seconds${NC}"
        ssh_cmd "sudo systemctl status flask-app --no-pager -l"
        ;;

    deploy)
        echo -e "${YELLOW}Deploying Flask app to EC2...${NC}"
        START_TIME=$SECONDS

        # Build the git command
        if [[ -n "$BRANCH" ]]; then
            GIT_CMD="git fetch origin && git checkout $BRANCH && git pull origin $BRANCH"
        else
            GIT_CMD="git pull"
        fi

        # Deploy
        ssh_cmd "cd /home/ubuntu/infrastructure/docker/flask-app && $GIT_CMD && sudo systemctl restart flask-app"

        ELAPSED=$((SECONDS - START_TIME))
        echo ""
        echo -e "${GREEN}Deployed in ${ELAPSED} seconds${NC}"
        echo ""

        # Quick health check
        echo -e "${YELLOW}Health check:${NC}"
        sleep 2
        if ssh_cmd "curl -s 127.0.0.1:5001/health | head -c 100"; then
            echo ""
            echo -e "${GREEN}Health check passed${NC}"
        else
            echo -e "${RED}Health check failed - checking logs...${NC}"
            ssh_cmd "sudo journalctl -u flask-app -n 20 --no-pager"
        fi
        ;;
esac
