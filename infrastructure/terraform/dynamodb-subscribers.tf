# ============================================================================
# REIT Sheet - Newsletter Subscribers DynamoDB Table
# ============================================================================
# Stores newsletter subscriber information for email campaigns
#
# Primary Key: email (partition key)
# GSI: status-subscribed_at-index (for querying verified subscribers)
#
# Subscriber States:
#   - pending: Initial signup, awaiting email verification
#   - verified: Email verified, actively subscribed
#   - unsubscribed: User opted out via unsubscribe link
#
# SOLID Principles:
#   - Single Responsibility: One table for subscriber data
#   - Open/Closed: GSI allows adding new query patterns without table changes

resource "aws_dynamodb_table" "subscribers" {
  name         = "${var.project_name}-subscribers"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "email"

  # Primary key: email (partition key)
  attribute {
    name = "email"
    type = "S"
  }

  # GSI attribute: status (for querying by subscription status)
  attribute {
    name = "status"
    type = "S"
  }

  # GSI attribute: subscribed_at (for sorting by signup date)
  attribute {
    name = "subscribed_at"
    type = "S"
  }

  # GSI: Query verified subscribers sorted by subscription date
  # Use case: Send newsletter to all verified subscribers
  global_secondary_index {
    name            = "status-subscribed_at-index"
    hash_key        = "status"
    range_key       = "subscribed_at"
    projection_type = "ALL"
    read_capacity   = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    write_capacity  = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
  }

  # Enable point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  # No TTL - subscribers remain in table until explicitly removed
  ttl {
    enabled        = false
    attribute_name = ""
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Newsletter-Subscribers"
    Description     = "Newsletter-subscriber-data-with-verification-status"
    TableType       = "user-data"
    KeyType         = "hash-only"
    GSICount        = "1"
    DataType        = "subscriber-metadata"
    AccessPattern   = "by-email-by-status"
    UpdateFrequency = "on-demand"
    PIIData         = "true"
  })
}

# Output table information
output "subscribers_table_name" {
  description = "Newsletter subscribers table name"
  value       = aws_dynamodb_table.subscribers.name
}

output "subscribers_table_arn" {
  description = "Newsletter subscribers table ARN"
  value       = aws_dynamodb_table.subscribers.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - email (String, Partition Key)
#
# Attributes:
#   - email: Subscriber email address (unique identifier)
#   - status: Subscription status (pending, verified, unsubscribed)
#   - subscribed_at: ISO 8601 timestamp when user first signed up
#   - verified_at: ISO 8601 timestamp when email was verified (null if pending)
#   - verification_token: UUID for email verification link (cleared after verification)
#   - unsubscribe_token: UUID for unsubscribe link (permanent, for one-click unsubscribe)
#   - source: Where the signup came from (website, api, manual)
#   - ip_address: Client IP at signup (for abuse prevention)
#   - user_agent: Client user agent at signup (for analytics)
#
# Global Secondary Indexes:
#   1. status-subscribed_at-index: Query subscribers by status, sorted by signup date
#
# Access Patterns:
#   1. Get subscriber by email: GetItem(email)
#   2. Find subscriber by verification token: Scan with filter (infrequent)
#   3. Find subscriber by unsubscribe token: Scan with filter (infrequent)
#   4. Get all verified subscribers: Query(status-subscribed_at-index, status='verified')
#   5. Get recent signups: Query(status-subscribed_at-index, status='pending')
#
# Security Notes:
#   - Contains PII (email addresses) - handle with care
#   - verification_token cleared after successful verification
#   - unsubscribe_token is permanent (allows one-click unsubscribe)
#   - Consider encryption at rest for compliance
#
# ============================================================================
