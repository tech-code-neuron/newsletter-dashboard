# ============================================================================
# REIT Sheet - DynamoDB Relevance Decisions Table
# ============================================================================
# Tracks relevance decisions for machine learning
#
# Phase 2: Migrating from SQLite relevance_decisions table
#
# Schema:
#   - decision_id (PK): Unique identifier
#   - press_release_url: URL of the press release
#   - ticker: Company ticker
#   - decision: 'relevant' | 'not_relevant'
#   - decided_at: Timestamp
#   - decided_by: 'user' | 'ml_model' | 'rule'

resource "aws_dynamodb_table" "relevance_decisions" {
  name         = "${var.project_name}-relevance-decisions"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "decision_id"

  attribute {
    name = "decision_id"
    type = "S"
  }

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "decided_at"
    type = "S"
  }

  attribute {
    name = "decision"
    type = "S"
  }

  # GSI for querying decisions by ticker
  global_secondary_index {
    name            = "ticker-decided-index"
    hash_key        = "ticker"
    range_key       = "decided_at"
    projection_type = "ALL"
  }

  # GSI for querying by decision type (for ML training data)
  global_secondary_index {
    name            = "decision-decided-index"
    hash_key        = "decision"
    range_key       = "decided_at"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery if configured
  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-relevance-decisions"
    Description = "Relevance decisions for ML training"
    DataType    = "ml-training-data"
  })
}

output "relevance_decisions_table_name" {
  description = "Relevance decisions DynamoDB table name"
  value       = aws_dynamodb_table.relevance_decisions.name
}

output "relevance_decisions_table_arn" {
  description = "Relevance decisions DynamoDB table ARN"
  value       = aws_dynamodb_table.relevance_decisions.arn
}
