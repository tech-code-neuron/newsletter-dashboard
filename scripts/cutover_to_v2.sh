#!/bin/bash
# ============================================================================
# Cutover Script: Switch Lambdas to V2 Table
# ============================================================================
# Updates Lambda environment variables to use new table
# Can be run in dry-run mode to preview changes

set -e  # Exit on error

# Configuration
OLD_TABLE="reitsheet-reit-news"
NEW_TABLE="reitsheet-reit-news-v2"
DRY_RUN="${1:-true}"  # Default to dry-run mode

# Lambda functions to update
LAMBDAS=(
    "reitsheet-enricher"
    "reitsheet-playwright-scraper"
    "reitsheet-url-testing-api-get-urls"
)

echo "========================================================================"
echo "CUTOVER TO V2 TABLE"
echo "========================================================================"
echo "Old Table: $OLD_TABLE"
echo "New Table: $NEW_TABLE"
echo "Dry Run:   $DRY_RUN"
echo ""

if [ "$DRY_RUN" = "true" ]; then
    echo "⚠️  DRY RUN MODE - No changes will be made"
    echo "   Run with: ./scripts/cutover_to_v2.sh false"
    echo ""
fi

# Function to update Lambda environment variable
update_lambda_env() {
    local function_name=$1

    echo "------------------------------------------------------------------------"
    echo "Lambda: $function_name"
    echo "------------------------------------------------------------------------"

    # Get current environment variables
    current_env=$(aws lambda get-function-configuration \
        --function-name "$function_name" \
        --query 'Environment.Variables' \
        --output json 2>/dev/null || echo "{}")

    if [ "$current_env" = "{}" ]; then
        echo "  ⚠️  No environment variables found (may not exist or no access)"
        return
    fi

    # Check if REIT_NEWS_TABLE exists
    current_table=$(echo "$current_env" | jq -r '.REIT_NEWS_TABLE // "not_set"')

    echo "  Current: REIT_NEWS_TABLE=$current_table"
    echo "  New:     REIT_NEWS_TABLE=$NEW_TABLE"

    if [ "$current_table" = "$NEW_TABLE" ]; then
        echo "  ✅ Already using V2 table"
        return
    fi

    if [ "$DRY_RUN" = "false" ]; then
        # Update environment variable
        updated_env=$(echo "$current_env" | jq --arg new_table "$NEW_TABLE" \
            '.REIT_NEWS_TABLE = $new_table')

        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --environment "Variables=$updated_env" \
            --output json > /dev/null

        echo "  ✅ Updated to V2 table"
    else
        echo "  🔍 Would update (dry-run mode)"
    fi
}

# Update each Lambda
for lambda in "${LAMBDAS[@]}"; do
    update_lambda_env "$lambda"
    echo ""
done

echo "========================================================================"
if [ "$DRY_RUN" = "true" ]; then
    echo "DRY RUN COMPLETE - No changes made"
    echo ""
    echo "To apply changes, run:"
    echo "  ./scripts/cutover_to_v2.sh false"
else
    echo "CUTOVER COMPLETE ✅"
    echo ""
    echo "Next Steps:"
    echo "  1. Test each Lambda function"
    echo "  2. Monitor CloudWatch logs for errors"
    echo "  3. Check dashboard for correct data"
    echo "  4. Wait 24-48 hours before deleting old table"
    echo ""
    echo "Rollback (if needed):"
    echo "  Update env vars back to: $OLD_TABLE"
fi
echo "========================================================================"
