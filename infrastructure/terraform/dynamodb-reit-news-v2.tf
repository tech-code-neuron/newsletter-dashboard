# ============================================================================
# REIT Sheet - DynamoDB Table Configuration V2
# ============================================================================
# NEW SCHEMA: URL-based primary key for natural deduplication
# Migrates from composite key (press_release_id + first_seen_at) to simple hash (url)
#
# WHY THIS CHANGE:
# - Composite key allowed duplicates (same press_release_id, different first_seen_at)
# - URL is the natural unique identifier for a press release
# - DynamoDB enforces uniqueness automatically (no application-level deduplication)
# - Eliminates race conditions in duplicate detection
# - Simpler, faster inserts (no pre-check query needed)

# -----------------------------------------------------------------------------
# REIT News Table V2 (New Schema)
# -----------------------------------------------------------------------------
# Stores deduplicated press releases from all REITs
# Primary key: url (unique press release URL)
# GSI 1: ticker + press_release_date (for ticker queries sorted by PR date)
# GSI 2: ticker + first_seen_at (for ticker queries sorted by when we saw it)

resource "aws_dynamodb_table" "reit_news_v2" {
  name         = "${local.reit_news_table}-v2"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "url" # Simple hash key - URL is naturally unique

  # Primary Key Attribute
  attribute {
    name = "url"
    type = "S"
  }

  # GSI Attributes
  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "press_release_date"
    type = "S"
  }

  attribute {
    name = "first_seen_at"
    type = "S"
  }

  attribute {
    name = "social_status"
    type = "S"
  }

  # Global Secondary Index 1: Query by ticker, sorted by press release date
  # Use case: "Get all press releases for ticker O, newest first"
  # Example: Dashboard queries, ticker-specific timelines
  global_secondary_index {
    name            = "ticker-date-index"
    hash_key        = "ticker"
    range_key       = "press_release_date"
    projection_type = "ALL"
  }

  # Global Secondary Index 2: Query by ticker, sorted by when we first saw it
  # Use case: "Get all press releases for ticker O, in order we ingested them"
  # Example: Processing logs, ingestion timeline
  global_secondary_index {
    name            = "ticker-firstseen-index"
    hash_key        = "ticker"
    range_key       = "first_seen_at"
    projection_type = "ALL"
  }

  # Global Secondary Index 3: Query by social media status
  # Use case: "Get all pending releases ready for social posting"
  # Example: Social media approval queue, posting pipeline
  global_secondary_index {
    name            = "social_status-first_seen_at-index"
    hash_key        = "social_status"
    range_key       = "first_seen_at"
    projection_type = "ALL"
  }

  tags = merge(local.database_tags, {
    Name          = "REIT-Sheet-Press-Releases-V2"
    Description   = "URL-based-primary-key-for-natural-deduplication"
    TableType     = "primary-data"
    KeyType       = "hash-only"
    GSICount      = "3"
    DataType      = "press-release-metadata"
    AccessPattern = "read-heavy"
    QueryPatterns = "by-url-and-by-ticker-date"
    IndexUsage    = "ticker-timeline-queries"
    SchemaVersion = "2"
    MigratedFrom  = local.reit_news_table
    MigrationDate = "2026-03-13"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "reit_news_v2_table_name" {
  description = "Name of the new REIT News table (V2 schema)"
  value       = aws_dynamodb_table.reit_news_v2.name
}

output "reit_news_v2_table_arn" {
  description = "ARN of the new REIT News table (V2 schema)"
  value       = aws_dynamodb_table.reit_news_v2.arn
}

# -----------------------------------------------------------------------------
# Migration Notes
# -----------------------------------------------------------------------------
#
# MIGRATION STEPS:
# 1. Apply this Terraform: terraform apply -target=aws_dynamodb_table.reit_news_v2
# 2. Run migration script: python3 scripts/migrate_reit_news_to_v2.py
# 3. Verify data: python3 scripts/verify_migration.py
# 4. Update Lambda env vars: REIT_NEWS_TABLE=reitsheet-reit-news-v2
# 5. Deploy updated Lambdas
# 6. Monitor for 24-48 hours
# 7. Delete old table: terraform destroy -target=aws_dynamodb_table.reit_news
#
# ROLLBACK PLAN:
# - Keep old table for 7 days
# - Can switch back by updating Lambda env vars
# - Migration script is idempotent (can re-run)
