# ============================================================================
# DynamoDB Table: Press Release Audit Trail
# ============================================================================
# Purpose: Permanent, immutable audit log for all press release operations
#
# Design:
#   - Deletion-protected (like url-cache)
#   - Point-in-time recovery enabled (30-day backup)
#   - NO TTL - permanent data retention
#   - Tracks all add/edit/delete operations from dashboard
#   - Preserves original values for recovery and learning
#
# Use Cases:
#   1. Data recovery - restore deleted press releases
#   2. Learning pipeline - analyze human corrections to improve automation
#   3. Accountability - track who changed what and why
#   4. Pattern detection - identify systematic errors (e.g., truncated titles)
# ============================================================================

resource "aws_dynamodb_table" "press_release_audit" {
  name         = "reitsheet-press-release-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "audit_id"
  range_key    = "timestamp"

  # CRITICAL PROTECTION: Prevent accidental deletion
  deletion_protection_enabled = true

  # CRITICAL PROTECTION: Point-in-time recovery (30-day backup)
  point_in_time_recovery {
    enabled = true
  }

  # Primary key: UUID for each audit record
  attribute {
    name = "audit_id"
    type = "S"
  }

  # Sort key: ISO 8601 timestamp
  attribute {
    name = "timestamp"
    type = "S"
  }

  # GSI attributes
  attribute {
    name = "url"
    type = "S"
  }

  attribute {
    name = "operation"
    type = "S"
  }

  attribute {
    name = "ticker"
    type = "S"
  }

  # GSI 1: Query all operations for a specific URL
  global_secondary_index {
    name            = "url-timestamp-index"
    hash_key        = "url"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI 2: Query by operation type (analytics)
  global_secondary_index {
    name            = "operation-timestamp-index"
    hash_key        = "operation"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI 3: Query by ticker (company-specific audits)
  global_secondary_index {
    name            = "ticker-timestamp-index"
    hash_key        = "ticker"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # Server-side encryption at rest
  server_side_encryption {
    enabled = true
  }

  # NO TTL - permanent data retention for learning and recovery
  # ttl {
  #   enabled = false
  # }

  # Lifecycle policy: Never delete
  lifecycle {
    prevent_destroy = true
  }

  tags = merge(local.database_tags, {
    Name         = "reitsheet-press-release-audit"
    Purpose      = "permanent-audit-trail"
    CriticalData = "true"
    DataType     = "audit-log"
    Retention    = "permanent"
    Learning     = "enabled"
  })
}

# ============================================================================
# CloudWatch Alarms
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "audit_table_throttle" {
  alarm_name          = "reitsheet-audit-table-throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Press release audit table is being throttled"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.press_release_audit.name
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "press_release_audit_table_name" {
  value       = aws_dynamodb_table.press_release_audit.name
  description = "Name of the press release audit trail table"
}

output "press_release_audit_table_arn" {
  value       = aws_dynamodb_table.press_release_audit.arn
  description = "ARN of the press release audit trail table"
}
