# ============================================================================
# REIT Sheet - DynamoDB Newsletter Editions Table
# ============================================================================
# Stores server-rendered newsletter editions for the publisher system
#
# Purpose: Track daily newsletter editions with their items and sections
#
# Schema:
#   - date (PK): Newsletter date in YYYY-MM-DD format (e.g., "2026-03-28")
#   - items: List of newsletter items
#   - sections: Map of section_key -> list of items
#   - published_at: ISO timestamp when published
#   - status: "published" or "draft"
#   - created_at: ISO timestamp when created
#   - item_count: Number of items in newsletter

resource "aws_dynamodb_table" "newsletter_editions" {
  name         = "${var.project_name}-newsletter-editions"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # GSI for querying by status (e.g., all published editions, all drafts)
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
    Name        = "${var.project_name}-newsletter-editions"
    Description = "Server-rendered newsletter editions for publisher system"
    DataType    = "newsletter-edition"
    KeyType     = "hash-only"
    GSICount    = "1"
  })
}

output "newsletter_editions_table_name" {
  description = "Newsletter editions DynamoDB table name"
  value       = aws_dynamodb_table.newsletter_editions.name
}

output "newsletter_editions_table_arn" {
  description = "Newsletter editions DynamoDB table ARN"
  value       = aws_dynamodb_table.newsletter_editions.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - date (String, Partition Key): YYYY-MM-DD format (e.g., "2026-03-28")
#
# Attributes:
#   - date: Newsletter date, partition key
#   - items: List of newsletter item objects
#   - sections: Map of section_key to list of items for organized display
#   - published_at: ISO 8601 timestamp when edition was published
#   - status: "published" or "draft"
#   - created_at: ISO 8601 timestamp when edition was created
#   - item_count: Total number of items in the newsletter
#
# Global Secondary Index:
#   - status-date-index: Query editions by status with date ordering
#     - Use case: Get all published editions, get all drafts
#     - Access pattern: Query(status="published", SK > "2026-03-01")
#
# Access Patterns:
#   1. Get edition by date: GetItem(date="2026-03-28")
#   2. List published editions: Query(status-date-index, status="published")
#   3. List recent drafts: Query(status-date-index, status="draft", ScanIndexForward=False)
#
# Item Format Example:
#   {
#     "date": "2026-03-28",
#     "status": "published",
#     "published_at": "2026-03-28T14:30:00+00:00",
#     "created_at": "2026-03-28T10:00:00+00:00",
#     "item_count": 15,
#     "items": [...],
#     "sections": {
#       "acquisitions": [...],
#       "earnings": [...],
#       "dividends": [...]
#     }
#   }
#
# ============================================================================
