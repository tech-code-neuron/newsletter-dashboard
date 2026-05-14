# ============================================================================
# DynamoDB Table: URL Cache (Immutable Log)
# ============================================================================
# Purpose: Permanent record of all scraped URLs
# CRITICAL: This table should NEVER be deleted - it prevents re-scraping
#
# Design:
#   - Stores ONLY URLs, timestamps, and scrape metadata
#   - NO content (content in reitsheet-reit-news table)
#   - Point-in-time recovery enabled (30-day backup)
#   - Deletion protection enabled
#   - If reitsheet-reit-news gets cleared, this table preserves scrape history
#
# Use Cases:
#   1. Check if URL already scraped before making HTTP request
#   2. Audit trail of all scraping activity
#   3. Recover from accidental content deletion
#   4. Rate limiting / politeness (avoid re-scraping same URL too frequently)
# ============================================================================

resource "aws_dynamodb_table" "url_cache" {
  name         = "reitsheet-url-cache"
  billing_mode = "PAY_PER_REQUEST" # Auto-scaling
  hash_key     = "url_hash"        # Partition key: SHA256(url)
  range_key    = "scraped_at"      # Sort key: ISO timestamp

  # CRITICAL PROTECTION: Prevent accidental deletion
  deletion_protection_enabled = true

  # CRITICAL PROTECTION: Point-in-time recovery (30-day backup window)
  point_in_time_recovery {
    enabled = true
  }

  # Partition key: SHA256 hash of URL for O(1) lookups
  attribute {
    name = "url_hash"
    type = "S" # String
  }

  # Sort key: Timestamp for chronological ordering
  attribute {
    name = "scraped_at"
    type = "S" # ISO 8601 timestamp
  }

  # GSI: Query by company ticker
  attribute {
    name = "ticker"
    type = "S"
  }

  # GSI: Query by scrape status
  attribute {
    name = "scrape_status"
    type = "S" # success|failed|error
  }

  # Global Secondary Index: Query all URLs by ticker
  global_secondary_index {
    name            = "ticker-index"
    hash_key        = "ticker"
    range_key       = "scraped_at"
    projection_type = "ALL"
  }

  # Global Secondary Index: Query by scrape status
  global_secondary_index {
    name            = "status-index"
    hash_key        = "scrape_status"
    range_key       = "scraped_at"
    projection_type = "ALL"
  }

  # Server-side encryption at rest
  server_side_encryption {
    enabled = true
  }

  # Time-to-live: DISABLED - we want to keep this data forever
  # ttl {
  #   attribute_name = "expires_at"
  #   enabled        = false
  # }

  # Lifecycle policy: Never delete
  lifecycle {
    prevent_destroy = true # Terraform will refuse to destroy this table
  }

  tags = merge(local.database_tags, {
    Name         = "reitsheet-url-cache"
    Purpose      = "immutable-url-log"
    CriticalData = "true"
    DataType     = "url-metadata"
    Retention    = "permanent"
  })
}

# ============================================================================
# CloudWatch Alarms: Monitor URL cache
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "url_cache_throttle" {
  alarm_name          = "reitsheet-url-cache-throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "URL cache table is being throttled"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.url_cache.name
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "url_cache_table_name" {
  value       = aws_dynamodb_table.url_cache.name
  description = "Name of the URL cache table (immutable log)"
}

output "url_cache_table_arn" {
  value       = aws_dynamodb_table.url_cache.arn
  description = "ARN of the URL cache table"
}
