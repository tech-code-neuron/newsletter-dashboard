# ============================================================================
# REIT Sheet - Companies DynamoDB Table
# ============================================================================
# Stores company IR domain mappings for press release filtering
# Enables parser Lambda to match URLs to specific companies

resource "aws_dynamodb_table" "companies" {
  name         = "${var.project_name}-companies"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "ticker"

  attribute {
    name = "ticker"
    type = "S"
  }

  # Global Secondary Index for lookup by email domain
  attribute {
    name = "email_domain"
    type = "S"
  }

  global_secondary_index {
    name            = "email-domain-index"
    hash_key        = "email_domain"
    projection_type = "ALL"
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Companies"
    Description     = "Company-IR-domain-mappings-with-parsing-strategies"
    TableType       = "reference-data"
    KeyType         = "hash-only"
    GSICount        = "1"
    DataType        = "company-metadata"
    AccessPattern   = "read-heavy"
    QueryPatterns   = "by-ticker-and-by-email-domain"
    UpdateFrequency = "manual"
    ParseStrategies = "gcs-hosted-and-gcs-custom-domain-and-brixmor-aspx-and-direct-url"
  })
}

# Note: url_construction_method field added to items:
# - gcs_9_word_slug: GCS with standardized 9-word slug (e.g., SUI)
# - gcs_variable_slug: GCS with non-standard slugs, needs redirect validation (e.g., RHP, VNO)
# - gcs_hosted: Pure GCS hosting (domain contains gcs-web.com)
# - gcs_custom_domain: GCS-style URLs on custom domain (e.g., Digital Realty)
# - brixmor_aspx: Brixmor-specific ASPX format with case-sensitive slugs
#   Pattern: {year}/{SLUG}/default.aspx (e.g., 2026/BRIXMOR-ANNOUNCES-EARNINGS/default.aspx)
# - direct_url: Match URLs directly without construction
# - redirect_follow: Follow tracking redirects (fallback)
#
# Note: skip_url_validation field (boolean):
# - true: Skip HTTP validation for constructed URLs (standardized patterns only, e.g., SUI)
# - false: Always validate constructed URLs, follow redirects if needed (e.g., RHP, VNO)
#   RHP and VNO use GCS IR services but have non-standardized slugs requiring redirect validation
