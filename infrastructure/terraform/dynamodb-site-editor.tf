# ============================================================================
# REIT Sheet - DynamoDB Site Editor Tables
# ============================================================================
# Stores site editor configuration overrides and version history.
#
# Tables:
#   - site-editor-config: Active/draft config overrides (PK: state, SK: config_key)
#   - site-editor-versions: Version history for rollback (PK: version_id)

resource "aws_dynamodb_table" "site_editor_config" {
  name         = "${var.project_name}-site-editor-config"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "state"
  range_key    = "config_key"

  attribute {
    name = "state"
    type = "S"
  }

  attribute {
    name = "config_key"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-site-editor-config"
    Description = "Site editor configuration overrides"
    DataType    = "config"
  })
}

resource "aws_dynamodb_table" "site_editor_versions" {
  name         = "${var.project_name}-site-editor-versions"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "version_id"

  attribute {
    name = "version_id"
    type = "N"
  }

  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-site-editor-versions"
    Description = "Site editor version history"
    DataType    = "versions"
  })
}

output "site_editor_config_table_name" {
  description = "Site Editor Config DynamoDB table name"
  value       = aws_dynamodb_table.site_editor_config.name
}

output "site_editor_config_table_arn" {
  description = "Site Editor Config DynamoDB table ARN"
  value       = aws_dynamodb_table.site_editor_config.arn
}

output "site_editor_versions_table_name" {
  description = "Site Editor Versions DynamoDB table name"
  value       = aws_dynamodb_table.site_editor_versions.name
}

output "site_editor_versions_table_arn" {
  description = "Site Editor Versions DynamoDB table ARN"
  value       = aws_dynamodb_table.site_editor_versions.arn
}
