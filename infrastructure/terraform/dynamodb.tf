# ============================================================================
# REIT Sheet - DynamoDB Table Configuration
# ============================================================================
# NoSQL database tables for data persistence
# - Inbound Log: Idempotency and duplicate detection
# - REIT News: Deduplicated press release storage

# -----------------------------------------------------------------------------
# Inbound Log Table
# -----------------------------------------------------------------------------
# Prevents duplicate processing of the same email
# Uses SHA256 hash of bucket:key:etag as idempotency key
# TTL automatically deletes records after 30 days

resource "aws_dynamodb_table" "inbound_log" {
  name         = local.inbound_log_table
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.database_tags, {
    Name             = "REIT-Sheet-Inbound-Log"
    Description      = "Idempotency-table---prevents-duplicate-email-processing"
    TableType        = "log"
    KeyType          = "hash-only"
    TTLEnabled       = "true"
    TTLDays          = var.idempotency_ttl_days
    DataType         = "processing-metadata"
    AccessPattern    = "write-heavy"
    RetentionPurpose = "duplicate-detection"
  })
}

# -----------------------------------------------------------------------------
# REIT News Table V1 - REMOVED (Migrated to V2)
# -----------------------------------------------------------------------------
# V1 table has been deleted. All references now point to V2:
# - Table: reitsheet-reit-news-v2 (defined in dynamodb-reit-news-v2.tf)
# - Schema: url (primary key), no press_release_id
# - Migration Date: 2026-03-13
#
# V1 was deleted on 2026-03-13 after successful V2 migration
