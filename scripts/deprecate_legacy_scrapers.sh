#!/bin/bash
# ============================================================================
# Deprecate Legacy Scraper Architecture
# ============================================================================
# Removes scraper-router and simple-scraper (replaced by refactored scraper)
#
# Context:
# - scraper-router and simple-scraper are legacy components from intermediate architecture
# - Both consume from SCRAPE_QUEUE, competing with main scraper (race condition)
# - simple-scraper has outdated DynamoDB schema (missing press_release_id key)
# - Only 2 invocations in 30 days, both resulted in data loss
# - Functionality fully replaced by refactored reitsheet-scraper (4-layer cascade)
#
# What this script does:
# 1. Disables SQS event source mappings (reversible)
# 2. Creates backups of Lambda configurations
# 3. Monitors for 7 days (manual check)
# 4. If no issues, removes Lambda functions + SQS queues via Terraform
#
# Generated: 2026-03-14
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/infrastructure/backups/legacy-scrapers-$(date +%Y%m%d-%H%M%S)"
REGION="us-east-1"

# Lambda functions to deprecate
SCRAPER_ROUTER="reitsheet-scraper-router"
SIMPLE_SCRAPER="reitsheet-simple-scraper"

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
create_backups() {
    log_info "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"

    log_info "Backing up Lambda configurations..."

    # Backup scraper-router
    aws lambda get-function --function-name "$SCRAPER_ROUTER" > "$BACKUP_DIR/scraper-router-config.json" || {
        log_error "Failed to backup $SCRAPER_ROUTER configuration"
        return 1
    }

    # Backup simple-scraper
    aws lambda get-function --function-name "$SIMPLE_SCRAPER" > "$BACKUP_DIR/simple-scraper-config.json" || {
        log_error "Failed to backup $SIMPLE_SCRAPER configuration"
        return 1
    }

    # Backup event source mappings
    aws lambda list-event-source-mappings --function-name "$SCRAPER_ROUTER" > "$BACKUP_DIR/scraper-router-event-sources.json"
    aws lambda list-event-source-mappings --function-name "$SIMPLE_SCRAPER" > "$BACKUP_DIR/simple-scraper-event-sources.json"

    log_success "Backups created in: $BACKUP_DIR"
}

# Disable event source mappings (reversible)
disable_event_sources() {
    log_info "Disabling event source mappings (REVERSIBLE)..."

    # Get scraper-router event source UUID
    ROUTER_UUID=$(aws lambda list-event-source-mappings \
        --function-name "$SCRAPER_ROUTER" \
        --query 'EventSourceMappings[0].UUID' \
        --output text)

    if [ "$ROUTER_UUID" != "None" ] && [ -n "$ROUTER_UUID" ]; then
        log_info "Disabling scraper-router event source: $ROUTER_UUID"
        aws lambda update-event-source-mapping \
            --uuid "$ROUTER_UUID" \
            --no-enabled \
            --output json > "$BACKUP_DIR/scraper-router-disabled.json"
        log_success "Scraper-router event source DISABLED"
    else
        log_warning "No event source found for scraper-router"
    fi

    # Get simple-scraper event source UUID
    SCRAPER_UUID=$(aws lambda list-event-source-mappings \
        --function-name "$SIMPLE_SCRAPER" \
        --query 'EventSourceMappings[0].UUID' \
        --output text)

    if [ "$SCRAPER_UUID" != "None" ] && [ -n "$SCRAPER_UUID" ]; then
        log_info "Disabling simple-scraper event source: $SCRAPER_UUID"
        aws lambda update-event-source-mapping \
            --uuid "$SCRAPER_UUID" \
            --no-enabled \
            --output json > "$BACKUP_DIR/simple-scraper-disabled.json"
        log_success "Simple-scraper event source DISABLED"
    else
        log_warning "No event source found for simple-scraper"
    fi
}

# Check current metrics
check_metrics() {
    log_info "Checking CloudWatch metrics (last 7 days)..."

    START_TIME=$(date -u -v-7d '+%Y-%m-%dT%H:%M:%S')
    END_TIME=$(date -u '+%Y-%m-%dT%H:%M:%S')

    # Scraper-router invocations
    ROUTER_INVOCATIONS=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/Lambda \
        --metric-name Invocations \
        --dimensions Name=FunctionName,Value="$SCRAPER_ROUTER" \
        --start-time "$START_TIME" \
        --end-time "$END_TIME" \
        --period 86400 \
        --statistics Sum \
        --query 'sum(Datapoints[*].Sum)' \
        --output text)

    # Simple-scraper invocations
    SCRAPER_INVOCATIONS=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/Lambda \
        --metric-name Invocations \
        --dimensions Name=FunctionName,Value="$SIMPLE_SCRAPER" \
        --start-time "$START_TIME" \
        --end-time "$END_TIME" \
        --period 86400 \
        --statistics Sum \
        --query 'sum(Datapoints[*].Sum)' \
        --output text)

    echo ""
    log_info "=== Metrics Summary (Last 7 Days) ==="
    echo "  scraper-router invocations: ${ROUTER_INVOCATIONS:-0}"
    echo "  simple-scraper invocations: ${SCRAPER_INVOCATIONS:-0}"
    echo ""

    # Save metrics to backup
    cat > "$BACKUP_DIR/metrics-summary.txt" <<EOF
Deprecation Metrics - $(date)
=================================

Last 7 Days:
- scraper-router invocations: ${ROUTER_INVOCATIONS:-0}
- simple-scraper invocations: ${SCRAPER_INVOCATIONS:-0}

Context:
- Both Lambdas consume from SCRAPE_QUEUE (race condition with main scraper)
- simple-scraper has outdated schema (missing press_release_id)
- Functionality replaced by reitsheet-scraper (refactored Mar 14)

Next Steps:
1. Monitor main scraper for 7 days
2. Check DLQ depths remain stable
3. Verify no error spikes in parser/enricher
4. If no issues, proceed with permanent deletion
EOF

    log_success "Metrics saved to: $BACKUP_DIR/metrics-summary.txt"
}

# Monitor instructions
print_monitoring_instructions() {
    cat <<EOF

${GREEN}==================================================================${NC}
${GREEN}PHASE 1 COMPLETE: Event Sources Disabled${NC}
${GREEN}==================================================================${NC}

${YELLOW}⚠️  IMPORTANT: Monitor for 7 days before permanent deletion${NC}

${BLUE}What to monitor:${NC}
1. Main scraper Lambda (reitsheet-scraper):
   - Check invocation count increased by ~2-4/week
   - Check error rate remains stable
   - Check DynamoDB write success rate

2. DLQ queues:
   - scrape-dlq depth should remain 0
   - parse-dlq depth should remain 0
   - enrich-dlq depth should remain 0

3. Parser/Enricher logs:
   - No new error patterns
   - No "routing failed" messages

${BLUE}Monitoring Commands:${NC}

# Check main scraper invocations (daily)
aws cloudwatch get-metric-statistics \\
  --namespace AWS/Lambda \\
  --metric-name Invocations \\
  --dimensions Name=FunctionName,Value=reitsheet-scraper \\
  --start-time \$(date -u -v-1d '+%Y-%m-%dT%H:%M:%S') \\
  --end-time \$(date -u '+%Y-%m-%dT%H:%M:%S') \\
  --period 3600 --statistics Sum

# Check DLQ depths
aws sqs get-queue-attributes \\
  --queue-url \$(aws sqs get-queue-url --queue-name reitsheet-scrape-dlq --output text) \\
  --attribute-names ApproximateNumberOfMessages

# Check recent scraper logs
aws logs tail /aws/lambda/reitsheet-scraper --since 1h --follow

${BLUE}Rollback (if needed):${NC}
If you notice issues, re-enable event sources:

# Re-enable scraper-router
aws lambda update-event-source-mapping \\
  --uuid \$(cat $BACKUP_DIR/scraper-router-event-sources.json | jq -r '.EventSourceMappings[0].UUID') \\
  --enabled

# Re-enable simple-scraper
aws lambda update-event-source-mapping \\
  --uuid \$(cat $BACKUP_DIR/simple-scraper-event-sources.json | jq -r '.EventSourceMappings[0].UUID') \\
  --enabled

${GREEN}After 7 days (if no issues):${NC}
Run Phase 2 to permanently delete:
  bash scripts/deprecate_legacy_scrapers_phase2.sh

${BLUE}Backups saved to:${NC}
  $BACKUP_DIR

==================================================================${NC}

EOF
}

# Main execution
main() {
    log_info "Starting deprecation of legacy scraper architecture..."
    echo ""

    # Confirm action
    echo -e "${YELLOW}This will DISABLE (not delete) the following Lambda functions:${NC}"
    echo "  - $SCRAPER_ROUTER"
    echo "  - $SIMPLE_SCRAPER"
    echo ""
    echo -e "${YELLOW}Their functionality is now handled by reitsheet-scraper.${NC}"
    echo ""
    read -p "Continue? (yes/no): " -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_warning "Deprecation cancelled by user"
        exit 0
    fi

    # Execute steps
    create_backups || {
        log_error "Backup failed, aborting"
        exit 1
    }

    check_metrics

    disable_event_sources || {
        log_error "Failed to disable event sources"
        exit 1
    }

    print_monitoring_instructions

    log_success "Phase 1 complete! Monitor for 7 days before Phase 2."
}

# Run main
main "$@"
