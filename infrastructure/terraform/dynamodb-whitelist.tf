# ============================================================================
# REIT Sheet - Domain Whitelist DynamoDB Table
# ============================================================================
# Stores whitelisted domains that bypass rate limiting
# - Trusted REIT IR email services (Q4, GCS, etc.)
# - No TTL (permanent whitelist)
# - Pay-per-request billing (low cost)

resource "aws_dynamodb_table" "domain_whitelist" {
  name         = "${var.project_name}-domain-whitelist"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "domain"

  attribute {
    name = "domain"
    type = "S"
  }

  tags = merge(local.storage_tags, {
    Name        = "REIT-Sheet-Domain-Whitelist"
    Description = "Trusted-domains-that-bypass-rate-limiting"
    DataType    = "domain-whitelist"
    Retention   = "permanent"
    Purpose     = "trust-known-reit-ir-services"
  })
}

# Output for reference
output "domain_whitelist_table_name" {
  description = "Domain whitelist table name"
  value       = aws_dynamodb_table.domain_whitelist.name
}

output "domain_whitelist_table_arn" {
  description = "Domain whitelist table ARN"
  value       = aws_dynamodb_table.domain_whitelist.arn
}
