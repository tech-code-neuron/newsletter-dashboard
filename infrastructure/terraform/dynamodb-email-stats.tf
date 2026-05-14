# ============================================================================
# Email Statistics DynamoDB Table
# ============================================================================
# Stores daily email processing statistics for summary reports
#
# Schema:
#   - date (PK): YYYY-MM-DD
#   - total_count: Total emails received
#   - forwarded_company_count: Company IR/PR emails forwarded
#   - forwarded_8k_count: 8-K filings forwarded
#   - filtered_<type>_count: Filtered SEC filings by type (10-Q, 10-K, Form 4, etc.)
#   - spam_count: Spam emails rejected
#
# SOLID Principles:
#   - Single Responsibility: Only stores email statistics
#   - Open/Closed: Easy to add new counters via atomic updates
#   - No Hardcoded Values: TTL and billing mode in variables

resource "aws_dynamodb_table" "email_stats" {
  name         = "${var.project_name}-email-stats"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing (no capacity planning needed)
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S" # String: YYYY-MM-DD format
  }

  # Auto-delete old statistics after 90 days (save storage costs)
  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "REIT-Sheet-Email-Stats"
    Description = "Daily email processing statistics for summary reports"
    DataType    = "statistics"
    Retention   = "90-days"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "email_stats_table_name" {
  description = "Email statistics DynamoDB table name"
  value       = aws_dynamodb_table.email_stats.name
}

output "email_stats_table_arn" {
  description = "Email statistics DynamoDB table ARN"
  value       = aws_dynamodb_table.email_stats.arn
}
