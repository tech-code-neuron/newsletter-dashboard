# ============================================================================
# REIT Sheet - DynamoDB Newsletter Table
# ============================================================================
# Stores newsletter metadata and content
#
# Phase 2: Migrating from SQLite newsletters table
#
# Schema:
#   - newsletter_id (PK): Unique identifier
#   - date (SK): Newsletter date
#   - newsletter_type: 'daily' | 'weekly'
#   - status: 'draft' | 'sent'
#   - subject_line: Email subject
#   - html_content: Rendered HTML
#   - created_at: Timestamp
#   - sent_at: When email was sent

resource "aws_dynamodb_table" "newsletters" {
  name         = "${var.project_name}-newsletters"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "newsletter_id"
  range_key    = "date"

  attribute {
    name = "newsletter_id"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # GSI for querying by status (e.g., all draft newsletters)
  global_secondary_index {
    name            = "status-date-index"
    hash_key        = "status"
    range_key       = "date"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery if configured
  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-newsletters"
    Description = "Newsletter metadata and content storage"
    DataType    = "newsletter"
  })
}

output "newsletters_table_name" {
  description = "Newsletters DynamoDB table name"
  value       = aws_dynamodb_table.newsletters.name
}

output "newsletters_table_arn" {
  description = "Newsletters DynamoDB table ARN"
  value       = aws_dynamodb_table.newsletters.arn
}
