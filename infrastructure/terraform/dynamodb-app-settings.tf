# ============================================================================
# REIT Sheet - DynamoDB App Settings Table
# ============================================================================
# Stores application-wide settings (newsletter styles, preferences, etc.)
#
# Schema:
#   - setting_key (PK): Unique setting identifier (e.g., 'newsletter_styles')
#   - value: Setting value (can be any DynamoDB-compatible type)
#   - updated_at: Last modification timestamp

resource "aws_dynamodb_table" "app_settings" {
  name         = "${var.project_name}-app-settings"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "setting_key"

  attribute {
    name = "setting_key"
    type = "S"
  }

  # Enable point-in-time recovery if configured
  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-app-settings"
    Description = "Application-wide settings storage"
    DataType    = "settings"
  })
}

output "app_settings_table_name" {
  description = "App Settings DynamoDB table name"
  value       = aws_dynamodb_table.app_settings.name
}

output "app_settings_table_arn" {
  description = "App Settings DynamoDB table ARN"
  value       = aws_dynamodb_table.app_settings.arn
}
