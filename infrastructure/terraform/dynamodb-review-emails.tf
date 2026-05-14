# ============================================================================
# REIT Sheet - DynamoDB Review Emails Table
# ============================================================================
# Stores emails flagged for manual review
#
# Phase 2: Migrating from SQLite review_emails table
#
# Schema:
#   - gmail_message_id (PK): Gmail message ID for deletion
#   - subject: Email subject
#   - from_header: Full from header
#   - from_email: Sender email address
#   - from_domain: Sender domain
#   - date: Email date
#   - classification_reason: Why it needs review
#   - status: 'pending' | 'processed' | 'rejected'
#   - created_at: When added to review queue
#   - processed_at: When reviewed

resource "aws_dynamodb_table" "review_emails" {
  name         = "${var.project_name}-review-emails"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "gmail_message_id"

  attribute {
    name = "gmail_message_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  attribute {
    name = "from_domain"
    type = "S"
  }

  # GSI for querying pending emails
  global_secondary_index {
    name            = "status-created-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # GSI for querying by sender domain
  global_secondary_index {
    name            = "domain-created-index"
    hash_key        = "from_domain"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery if configured
  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-review-emails"
    Description = "Emails flagged for manual review"
    DataType    = "review-email"
  })
}

output "review_emails_table_name" {
  description = "Review emails DynamoDB table name"
  value       = aws_dynamodb_table.review_emails.name
}

output "review_emails_table_arn" {
  description = "Review emails DynamoDB table ARN"
  value       = aws_dynamodb_table.review_emails.arn
}
