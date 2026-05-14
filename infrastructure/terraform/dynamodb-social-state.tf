# ============================================================================
# REIT Sheet - Social Media Pipeline State Table
# ============================================================================
# Stores global state for the social media pipeline
# - Kill switches (global, X-only, IG-only pause)
# - Monthly posting counters (X has 500/month limit)
# - Per-ticker recent post tracking for dedup

resource "aws_dynamodb_table" "social_state" {
  name         = "${var.project_name}-social-state"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "key"

  attribute {
    name = "key"
    type = "S"
  }

  tags = merge(local.database_tags, {
    Name        = "REIT-Sheet-Social-State"
    Description = "Global-state-for-social-media-pipeline-kill-switches-and-counters"
    DataType    = "configuration"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "social_state_table_name" {
  value       = aws_dynamodb_table.social_state.name
  description = "Social state table name"
}

output "social_state_table_arn" {
  value       = aws_dynamodb_table.social_state.arn
  description = "Social state table ARN"
}
