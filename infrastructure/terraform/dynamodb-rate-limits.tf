# ============================================================================
# REIT Sheet - Rate Limiting DynamoDB Table
# ============================================================================
# Tracks email rate limits per sender domain to prevent abuse
# - Minute-level counters (10 emails/minute max)
# - Hour-level counters (100 emails/hour max)
# - Automatic cleanup via TTL
# - Pay-per-request billing (cost-effective for low volume)

resource "aws_dynamodb_table" "rate_limits" {
  name         = "${var.project_name}-rate-limits"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "limit_key"

  attribute {
    name = "limit_key"
    type = "S"
  }

  # Automatic cleanup of expired records
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(local.storage_tags, {
    Name        = "REIT-Sheet-Rate-Limits"
    Description = "Rate-limiting-counters-per-sender-domain"
    DataType    = "rate-limit-counters"
    Retention   = "auto-cleanup-via-ttl"
    Purpose     = "prevent-email-abuse"
  })
}

# Output for reference
output "rate_limits_table_name" {
  description = "Rate limits table name"
  value       = aws_dynamodb_table.rate_limits.name
}

output "rate_limits_table_arn" {
  description = "Rate limits table ARN"
  value       = aws_dynamodb_table.rate_limits.arn
}
