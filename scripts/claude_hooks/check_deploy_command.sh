#!/bin/bash
#
# Claude Code Hook: Validate Lambda Deployment Commands
#
# Purpose: Block unvalidated Lambda deployments
# Prevents: Deploying wrong ZIP (like 2026-03-13 incident - 83KB vs 1.9MB)
#
# This hook runs BEFORE Bash tool execution and checks if the command
# is an AWS Lambda deployment. If so, it ensures validation was done.

# Read tool input from stdin
TOOL_INPUT=$(cat)

# Extract the command from JSON input
COMMAND=$(echo "$TOOL_INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"command"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//')

# Check if this is a Lambda deployment command
if echo "$COMMAND" | grep -q "aws lambda update-function-code"; then
    # Block deployments without validation
    if ! echo "$COMMAND" | grep -q "deploy_lambda.py"; then
        echo "WARN: Direct AWS Lambda deployment detected!"
        echo ""
        echo "RECOMMENDED: Use the deployment script with validation:"
        echo "  python3 scripts/deploy_lambda.py <name> --validate --zip <zip-name>"
        echo "  python3 scripts/deploy_lambda.py <name> --deploy --zip <zip-name>"
        echo ""
        echo "This ensures:"
        echo "  - ZIP size is within expected range (prevents wrong ZIP)"
        echo "  - Critical imports are present (prevents missing dependencies)"
        echo "  - Rollback ZIP exists (enables quick recovery)"
        echo ""
        echo "2026-03-13 incident: Parser deployed with 83KB ZIP instead of 1.9MB"
        echo "  - Missing 'requests' module broke ALL email processing"
        echo "  - Hours of downtime before detection"
        echo ""
        # Exit 0 to allow (warning only) - exit 1 would block
        exit 0
    fi
fi

# Check for force push to main
if echo "$COMMAND" | grep -qE "git push.*--force.*main|git push.*-f.*main"; then
    echo "BLOCKED: Force push to main branch detected!"
    echo ""
    echo "Force pushing to main can destroy work and break CI/CD."
    echo "Consider creating a new branch or using non-destructive approaches."
    exit 1
fi

# Check for git push --force without branch
if echo "$COMMAND" | grep -qE "git push\s+--force|git push\s+-f"; then
    echo "WARN: Force push detected!"
    echo ""
    echo "Are you sure you want to force push?"
    echo "This can overwrite work on the remote branch."
    exit 0  # Warning only
fi

# All other commands pass through
exit 0
