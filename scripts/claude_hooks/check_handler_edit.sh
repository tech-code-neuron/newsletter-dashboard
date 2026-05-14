#!/bin/bash
#
# Claude Code Hook: Warn on Lambda Handler Edits
#
# Purpose: Remind to check deployment state when editing handlers
# Prevents: Editing already-deployed code without awareness
#
# This hook runs BEFORE Edit tool execution and warns when modifying
# Lambda handler files.

# Read tool input from stdin
TOOL_INPUT=$(cat)

# Extract the file_path from JSON input
FILE_PATH=$(echo "$TOOL_INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//')

# Check if editing a Lambda handler
if echo "$FILE_PATH" | grep -q "infrastructure/lambdas/.*/handler\.py"; then
    # Extract Lambda name from path
    LAMBDA_NAME=$(echo "$FILE_PATH" | sed -E 's|.*/lambdas/([^/]+)/handler\.py|\1|')

    echo "INFO: Editing Lambda handler: $LAMBDA_NAME"
    echo ""
    echo "Reminders:"
    echo "  1. Check infrastructure/DEPLOYED_STATE.md for current deployment status"
    echo "  2. After editing, remember to build and deploy:"
    echo "     python3 scripts/deploy_lambda.py $LAMBDA_NAME --validate --zip <name>.zip"
    echo "     python3 scripts/deploy_lambda.py $LAMBDA_NAME --deploy --zip <name>.zip"
    echo "  3. Update DEPLOYED_STATE.md after deployment"
    echo ""
    # Always allow - this is informational only
    exit 0
fi

# All other files pass through
exit 0
